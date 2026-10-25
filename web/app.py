"""Standalone SMS Bridge API and private web inbox."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import parse_qs

ROOT = Path(__file__).parent
DB = os.environ.get('DATABASE_PATH', str(ROOT / 'data/inbox.sqlite'))


def delivery_mode():
    value = os.environ.get('DELIVERY_MODE', 'web')
    if value not in ('web', 'both', 'telegram'):
        raise ValueError('DELIVERY_MODE must be web, both, or telegram')
    return value


@contextmanager
def connect():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, sender TEXT NOT NULL,
      body TEXT NOT NULL, received_at INTEGER NOT NULL, uploaded_at INTEGER NOT NULL,
      device TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS messages_time ON messages(received_at DESC, id DESC);
    CREATE TABLE IF NOT EXISTS telegram_outbox (
      message_id INTEGER PRIMARY KEY, next_part INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
      retry_at INTEGER NOT NULL DEFAULT 0, delivered_at INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS deleted_events (event_id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS attempts (address TEXT PRIMARY KEY, count INTEGER, expires INTEGER);
    CREATE TABLE IF NOT EXISTS sms_sync_state (id INTEGER PRIMARY KEY CHECK(id=1), last_saved_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS device_diagnostics (name TEXT PRIMARY KEY, payload TEXT NOT NULL, reported_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS devices (name TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
    ''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(messages)')}
    if 'contact_name' not in columns:
        try:
            db.execute("ALTER TABLE messages ADD COLUMN contact_name TEXT NOT NULL DEFAULT ''")
            db.commit()
        except sqlite3.OperationalError:
            if 'contact_name' not in {row[1] for row in db.execute('PRAGMA table_info(messages)')}:
                raise
    db.execute('INSERT OR IGNORE INTO sms_sync_state SELECT 1, COALESCE(MAX(uploaded_at),0) FROM messages')
    db.commit()
    try:
        with db:
            yield db
    finally:
        db.close()


def equal(a, b):
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def check_password(value):
    stored = os.environ.get('DASHBOARD_PASSWORD_HASH', '')
    if ':' not in stored:
        return False
    try:
        return equal(password_hash(value, stored.split(':')[0]), stored)
    except (ValueError, TypeError):
        return False


def application(env, start_response):
    def reply(code, data, extra=(), content_type='application/json; charset=utf-8'):
        raw = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith('application/json') else data
        headers = [('Content-Type', content_type), ('Content-Length', str(len(raw))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                   ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY'),
                   ('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
        start_response(code, headers + list(extra))
        return [raw]

    path, method = env.get('PATH_INFO', '/'), env['REQUEST_METHOD']
    if path == '/health':
        with connect() as db:
            db.execute('SELECT 1').fetchone()
        return reply('200 OK', {'ok': True})
    if path == '/' and method == 'GET':
        return reply('302 Found', b'', [('Location', '/dashboard/')], content_type='text/plain')
    if path in ('/dashboard', '/dashboard/', '/dashboard/app.js', '/dashboard/style.css') and method == 'GET':
        if delivery_mode() == 'telegram':
            return reply('404 Not Found', {'error': 'Web inbox is disabled'})
        name, mime = {'/dashboard/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/dashboard/style.css': ('style.css', 'text/css; charset=utf-8')}.get(path, ('index.html', 'text/html; charset=utf-8'))
        return reply('200 OK', (ROOT / 'static' / name).read_bytes(), content_type=mime)
    if not path.startswith('/dashboard/api/'):
        return reply('404 Not Found', {'error': 'Not found'})
    # Mutating browser requests must be JSON and same-origin. Device clients have no Origin.
    if method in ('POST', 'DELETE', 'PATCH'):
        origin = env.get('HTTP_ORIGIN')
        allowed = [os.environ.get('PUBLIC_ORIGIN', 'http://127.0.0.1:8765')]
        if (origin and origin not in allowed) or env.get('HTTP_SEC_FETCH_SITE') == 'cross-site':
            return reply('403 Forbidden', {'error': 'Origin rejected'})
    data = {}
    if method in ('POST', 'PATCH'):
        try:
            size = int(env.get('CONTENT_LENGTH') or 0)
            if size > 262144 or size < 0:
                return reply('413 Payload Too Large', {'error': 'Request too large'})
            if not env.get('CONTENT_TYPE', '').startswith('application/json'):
                return reply('415 Unsupported Media Type', {'error': 'JSON required'})
            data = json.loads(env['wsgi.input'].read(size))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            return reply('400 Bad Request', {'error': 'Invalid JSON'})
    if path == '/dashboard/api/config' and method == 'GET' and delivery_mode() != 'telegram':
        return reply('200 OK', {'app_name': os.environ.get('APP_NAME', 'SMS Bridge')[:80]})
    now = int(time.time())
    with connect() as db:
        if path in ('/dashboard/api/ingest', '/dashboard/api/heartbeat') and method == 'POST':
            key = os.environ.get('DEVICE_TOKEN', '')
            if len(key) < 32 or not equal(env.get('HTTP_AUTHORIZATION', ''), 'Bearer ' + key):
                return reply('401 Unauthorized', {'error': 'Invalid device key'})
            device = data.get('device', 'Android phone')
            if not isinstance(device, str) or not 1 <= len(device) <= 100:
                return reply('400 Bad Request', {'error': 'Invalid device'})
            if path.endswith('/heartbeat') and 'diagnostics' in data:
                diagnostic = data['diagnostics']
                if not isinstance(diagnostic, dict):
                    return reply('400 Bad Request', {'error': 'Invalid diagnostics'})
                clean = {}
                for field in ('queue_count', 'blocked_count', 'last_capture', 'last_upload'):
                    value = diagnostic.get(field, 0)
                    if type(value) is not int or not 0 <= value <= 9223372036854775807:
                        return reply('400 Bad Request', {'error': 'Invalid diagnostics'})
                    clean[field] = value
                for field in ('sms_permission', 'forwarding_enabled'):
                    if type(diagnostic.get(field)) is not bool:
                        return reply('400 Bad Request', {'error': 'Invalid diagnostics'})
                    clean[field] = diagnostic[field]
                for field in ('app_version', 'upload_error', 'capture_error'):
                    value = diagnostic.get(field, '')
                    if not isinstance(value, str) or len(value) > 300:
                        return reply('400 Bad Request', {'error': 'Invalid diagnostics'})
                    clean[field] = value
                db.execute('INSERT OR REPLACE INTO device_diagnostics VALUES (?,?,?)', (device, json.dumps(clean), now))
            if path.endswith('/ingest'):
                try:
                    event, sender, body, stamp = (data[k] for k in ('event_id', 'sender', 'body', 'received_at'))
                    if not all(isinstance(x, str) for x in (event, sender, body)):
                        raise ValueError()
                    if not (1 <= len(event) <= 128 and 1 <= len(sender) <= 256 and len(body) <= 65536):
                        raise ValueError()
                    if type(stamp) is not int or not 0 <= stamp <= (now + 86400) * 1000:
                        raise ValueError()
                except (KeyError, ValueError):
                    return reply('400 Bad Request', {'error': 'Invalid message'})
                if db.execute('SELECT 1 FROM deleted_events WHERE event_id=?', (event,)).fetchone():
                    return reply('200 OK', {'ok': True, 'inserted': False, 'discarded': True})
                contact = data.get('contact_name', '')
                if not isinstance(contact, str) or len(contact) > 256:
                    return reply('400 Bad Request', {'error': 'Invalid contact name'})
                if stamp < int(os.environ.get('MIN_SMS_RECEIVED_AT', '0')):
                    return reply('200 OK', {'ok': True, 'inserted': False, 'discarded': True})
                cursor = db.execute('''INSERT OR IGNORE INTO messages
                    (event_id,sender,body,received_at,uploaded_at,device,contact_name)
                    VALUES (?,?,?,?,?,?,?)''', (event, sender, body, stamp, now, device, contact))
                inserted = cursor.rowcount > 0
                if inserted and delivery_mode() in ('both', 'telegram'):
                    db.execute('INSERT INTO telegram_outbox (message_id) VALUES (?)', (cursor.lastrowid,))
                if inserted:
                    db.execute('UPDATE sms_sync_state SET last_saved_at=MAX(last_saved_at,?) WHERE id=1', (now,))
            db.execute('INSERT INTO devices VALUES (?,?) ON CONFLICT(name) DO UPDATE SET seen_at=excluded.seen_at', (device, now))
            return reply('200 OK', {'ok': True, 'inserted': inserted} if path.endswith('/ingest') else {'ok': True})
        if delivery_mode() == 'telegram':
            return reply('404 Not Found', {'error': 'Web inbox is disabled'})
        if path == '/dashboard/api/login' and method == 'POST':
            address = env.get('REMOTE_ADDR', 'unknown')
            attempt = db.execute('SELECT * FROM attempts WHERE address=?', (address,)).fetchone()
            if attempt and attempt['expires'] > now and attempt['count'] >= 10:
                return reply('429 Too Many Requests', {'error': 'Too many attempts. Try again in 15 minutes.'})
            password = data.get('password', '')
            email = data.get('email', '')
            expected_email = os.environ.get('DASHBOARD_EMAIL', '')
            valid_email = bool(expected_email) and isinstance(email, str) and equal(email.strip().lower(), expected_email.lower())
            if not valid_email or not isinstance(password, str) or len(password) > 1024 or not check_password(password):
                count = attempt['count'] + 1 if attempt and attempt['expires'] > now else 1
                db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (address, count, now + 900))
                return reply('401 Unauthorized', {'error': 'Incorrect email or password'})
            db.execute('DELETE FROM attempts WHERE address=?', (address,))
            db.execute('DELETE FROM sessions WHERE expires < ?', (now,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(), now + 604800))
            secure = '' if os.environ.get('LOCAL_HTTP') == '1' else '; Secure'
            return reply('200 OK', {'ok': True}, [('Set-Cookie', f'session={token}; HttpOnly; SameSite=Strict; Path=/dashboard; Max-Age=604800{secure}')])
        cookies = dict(part.strip().split('=', 1) for part in env.get('HTTP_COOKIE', '').split(';') if '=' in part)
        token = hashlib.sha256(cookies.get('session', '').encode()).hexdigest()
        session = db.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?', (token, now)).fetchone()
        if not session:
            return reply('401 Unauthorized', {'error': 'Please sign in'})
        if path == '/dashboard/api/logout' and method == 'POST':
            db.execute('DELETE FROM sessions WHERE token=?', (token,))
            return reply('200 OK', {'ok': True}, [('Set-Cookie', 'session=; Path=/dashboard; Max-Age=0; HttpOnly; SameSite=Strict; Secure')])
        if path == '/dashboard/api/status' and method == 'GET':
            counts = dict(db.execute('SELECT COUNT(*) total, COALESCE(SUM(1-is_read),0) unread FROM messages').fetchone())
            devices = []
            for row in db.execute('SELECT * FROM devices'):
                device = dict(row)
                diagnostic = db.execute('SELECT payload,reported_at FROM device_diagnostics WHERE name=?', (device['name'],)).fetchone()
                if diagnostic:
                    device['diagnostics'] = json.loads(diagnostic['payload'])
                    device['diagnostics_at'] = diagnostic['reported_at']
                devices.append(device)
            counts.update(devices=devices,
                          last_sms_uploaded_at=db.execute('SELECT last_saved_at FROM sms_sync_state WHERE id=1').fetchone()[0])
            return reply('200 OK', counts)
        if path == '/dashboard/api/messages' and method == 'GET':
            query = parse_qs(env.get('QUERY_STRING', ''))
            search = query.get('q', [''])[0][:200]
            try:
                before = int(query.get('before', ['9223372036854775807'])[0])
                offset = max(0, min(10000000, int(query.get('offset', ['0'])[0])))
            except ValueError:
                return reply('400 Bad Request', {'error': 'Invalid pagination'})
            where = 'id < ?'
            params = [before]
            if search:
                where += ' AND (instr(lower(sender),lower(?))>0 OR instr(lower(body),lower(?))>0 OR instr(lower(contact_name),lower(?))>0)'
                params += [search, search, search]
            if query.get('unread') == ['1']:
                where += ' AND is_read=0'
            rows = db.execute(f'''SELECT id,sender,body,received_at,uploaded_at,device,is_read,contact_name
                FROM messages WHERE {where} ORDER BY received_at DESC,id DESC LIMIT 101 OFFSET ?''', params + [offset]).fetchall()
            return reply('200 OK', {'messages': [dict(r) for r in rows[:100]], 'has_more': len(rows) > 100})
        if path == '/dashboard/api/delete' and method == 'POST':
            ids = data.get('ids', [])
            if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or not all(type(i) is int and i > 0 for i in ids):
                return reply('400 Bad Request', {'error': 'Invalid message IDs'})
            placeholders = ','.join('?' for _ in ids)
            db.execute(f'INSERT OR IGNORE INTO deleted_events SELECT event_id FROM messages WHERE id IN ({placeholders})', ids)
            db.execute(f'DELETE FROM telegram_outbox WHERE message_id IN ({placeholders})', ids)
            cursor = db.execute(f'DELETE FROM messages WHERE id IN ({placeholders})', ids)
            return reply('200 OK', {'ok': True, 'deleted': cursor.rowcount})
        if path == '/dashboard/api/read' and method == 'POST':
            ids = data.get('ids', [])
            if not isinstance(ids, list) or len(ids) > 100 or not all(type(i) is int and i > 0 for i in ids):
                return reply('400 Bad Request', {'error': 'Invalid message IDs'})
            if ids:
                db.execute(f'UPDATE messages SET is_read=1 WHERE id IN ({",".join("?" for _ in ids)})', ids)
            return reply('200 OK', {'ok': True})
    return reply('404 Not Found', {'error': 'Not found'})


if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    print('Dashboard: http://127.0.0.1:8765/dashboard/')
    make_server('127.0.0.1', 8765, application).serve_forever()
