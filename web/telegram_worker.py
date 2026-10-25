"""Private, persistent Telegram delivery. Run one worker per database."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

import app


def chunks(text, limit=4000):
    """Count UTF-16 units, staying below Telegram's 4096-character limit."""
    result, part, size = [], [], 0
    for character in text:
        units = 2 if ord(character) > 0xFFFF else 1
        if size + units > limit:
            result.append(''.join(part))
            part, size = [], 0
        part.append(character)
        size += units
    if part:
        result.append(''.join(part))
    return result


def message_parts(row):
    stamp = datetime.fromtimestamp(row['received_at'] / 1000, timezone.utc).isoformat()
    name = row['contact_name'] or row['sender']
    return chunks(f"SMS · {row['device']}\nFrom: {name}\nSender: {row['sender']}\nReceived: {stamp}\n\n{row['body']}")


def credentials():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token) or not re.fullmatch(r'-?[0-9]+', chat):
        raise ValueError('Configure TELEGRAM_BOT_TOKEN and numeric TELEGRAM_CHAT_ID privately')
    return token, chat


class DeliveryError(Exception):
    def __init__(self, retry_after=60):
        super().__init__('Telegram delivery pending; retry scheduled')
        self.retry_after = retry_after


def send(text):
    token, chat = credentials()
    payload = json.dumps({'chat_id': chat, 'text': text, 'protect_content': True,
                          'link_preview_options': {'is_disabled': True}}).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',
                                     payload, {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read(65536))
        if not result.get('ok'):
            raise DeliveryError()
    except urllib.error.HTTPError as error:
        delay = 60
        if error.code == 429:
            try:
                delay = max(1, min(86400, int(json.loads(error.read(65536)).get('parameters', {}).get('retry_after', 60))))
            except (ValueError, TypeError, AttributeError):
                pass
        raise DeliveryError(delay) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Never include request URLs or remote bodies: they may contain credentials or SMS.
        raise DeliveryError() from None


def deliver_one(now=None):
    now = int(time.time()) if now is None else now
    with app.connect() as db:
        row = db.execute('''SELECT m.*, o.next_part, o.attempts FROM telegram_outbox o
            JOIN messages m ON m.id=o.message_id
            WHERE o.delivered_at=0 AND o.retry_at<=? ORDER BY m.id LIMIT 1''', (now,)).fetchone()
    if row is None:
        return False
    parts = message_parts(row)
    for index in range(row['next_part'], len(parts)):
        try:
            send(parts[index])
        except DeliveryError as error:
            delay = max(error.retry_after, min(3600, 30 * 2 ** min(row['attempts'], 7)))
            with app.connect() as db:
                db.execute('UPDATE telegram_outbox SET attempts=attempts+1,retry_at=? WHERE message_id=?',
                           (now + delay, row['id']))
            print('Telegram delivery pending; retry scheduled.', flush=True)
            return True
        with app.connect() as db:
            db.execute('UPDATE telegram_outbox SET next_part=? WHERE message_id=?', (index + 1, row['id']))
    with app.connect() as db:
        db.execute('UPDATE telegram_outbox SET delivered_at=? WHERE message_id=?', (now, row['id']))
    return True


def prune(now=None):
    """Telegram-only mode retains acknowledged SMS temporarily; pending SMS are never pruned."""
    if app.delivery_mode() != 'telegram':
        return
    days = max(0, int(os.environ.get('TELEGRAM_RETENTION_DAYS', '7')))
    cutoff = (int(time.time()) if now is None else now) - days * 86400
    with app.connect() as db:
        eligible = 'SELECT message_id FROM telegram_outbox WHERE delivered_at>0 AND delivered_at<=?'
        db.execute(f'INSERT OR IGNORE INTO deleted_events SELECT event_id FROM messages WHERE id IN ({eligible})', (cutoff,))
        db.execute(f'DELETE FROM messages WHERE id IN ({eligible})', (cutoff,))
        db.execute('DELETE FROM telegram_outbox WHERE delivered_at>0 AND delivered_at<=?', (cutoff,))


def main():
    lock_path = Path(app.DB).with_suffix('.telegram.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A Telegram worker is already running for this database')
        while True:
            if app.delivery_mode() in ('telegram', 'both'):
                try:
                    credentials()
                except ValueError as error:
                    raise SystemExit(str(error)) from None
                if deliver_one():
                    time.sleep(1.1)
                    continue
                prune()
            time.sleep(5)


if __name__ == '__main__':
    main()
