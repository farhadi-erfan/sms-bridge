import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB = self.temp.name + '/inbox.sqlite'
        os.environ['DEVICE_TOKEN'] = 'a' * 40
        os.environ['DASHBOARD_PASSWORD_HASH'] = app.password_hash('correct horse battery staple')
        os.environ['PUBLIC_ORIGIN'] = 'https://sms.example.com'
        self.cookie = ''
        os.environ['MIN_SMS_RECEIVED_AT'] = '0'
        os.environ['DASHBOARD_EMAIL'] = 'owner@example.com'
        os.environ['DELIVERY_MODE'] = 'web'

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, data=None, auth=None, origin=None, query=''):
        raw = json.dumps(data).encode() if data is not None else b''
        env = {'PATH_INFO':'/dashboard/api/' + path, 'REQUEST_METHOD':'POST' if data is not None else 'GET',
               'CONTENT_TYPE':'application/json', 'CONTENT_LENGTH':str(len(raw)), 'wsgi.input':io.BytesIO(raw),
               'REMOTE_ADDR':'127.0.0.1', 'HTTP_COOKIE':self.cookie, 'QUERY_STRING':query}
        if auth: env['HTTP_AUTHORIZATION'] = auth
        if origin: env['HTTP_ORIGIN'] = origin
        response = {}
        def start(status, headers): response.update(status=status, headers=dict(headers))
        body = b''.join(app.application(env, start))
        response['body'] = json.loads(body)
        return response

    def login(self):
        response = self.request('login', {'email':'owner@example.com', 'password':'correct horse battery staple'})
        self.assertEqual(response['status'], '200 OK')
        self.cookie = response['headers']['Set-Cookie'].split(';')[0]
        self.assertIn('Secure', response['headers']['Set-Cookie'])
        self.assertIn('HttpOnly', response['headers']['Set-Cookie'])

    def message(self, **overrides):
        data = {'event_id':'abc123', 'sender':'Example sender', 'body':'سلام <script>alert(1)</script>', 'received_at':int(time.time()*1000)}
        data.update(overrides)
        return self.request('ingest', data, auth='Bearer ' + 'a' * 40)

    def test_upload_key_cannot_read_inbox(self):
        self.assertEqual(self.request('messages', auth='Bearer ' + 'a' * 40)['status'], '401 Unauthorized')
        self.assertEqual(self.request('ingest', {})['status'], '401 Unauthorized')

    def test_durable_idempotent_upload_and_read(self):
        self.assertTrue(self.message()['body']['inserted'])
        self.assertFalse(self.message()['body']['inserted'])
        self.login()
        self.assertEqual(self.request('status')['body']['total'], 1)
        message = self.request('messages')['body']['messages'][0]
        self.assertIn('سلام', message['body'])
        self.assertEqual(self.request('read', {'ids':[message['id']]})['status'], '200 OK')
        self.assertEqual(self.request('status')['body']['unread'], 0)
        self.assertEqual(self.request('messages', query='unread=1')['body']['messages'], [])

    def test_bad_message_and_origin(self):
        self.assertEqual(self.message(received_at=-1)['status'], '400 Bad Request')
        self.assertEqual(self.message(sender=123)['status'], '400 Bad Request')
        self.assertEqual(self.request('login', {'email':'owner@example.com', 'password':'correct horse battery staple'}, origin='https://evil.example')['status'], '403 Forbidden')

    def test_contact_name_and_queue_cutoff(self):
        self.assertEqual(self.message(contact_name='Home')['status'], '200 OK')
        self.login()
        self.assertEqual(self.request('messages', query='q=Home')['body']['messages'][0]['contact_name'], 'Home')
        os.environ['MIN_SMS_RECEIVED_AT'] = str(int(time.time()*1000))
        response = self.message(event_id='stale', received_at=1)
        self.assertTrue(response['body']['discarded'])
        self.assertEqual(self.request('status')['body']['total'], 1)

    def test_delete_requires_login_and_prevents_reupload(self):
        self.message()
        self.assertEqual(self.request('delete', {'ids':[1]}, auth='Bearer ' + 'a'*40)['status'], '401 Unauthorized')
        self.login()
        self.assertEqual(self.request('delete', {'ids':[]})['status'], '400 Bad Request')
        self.assertEqual(self.request('delete', {'ids':[True]})['status'], '400 Bad Request')
        message = self.request('messages')['body']['messages'][0]
        self.assertEqual(self.request('delete', {'ids':[message['id']]})['body']['deleted'], 1)
        self.assertEqual(self.request('messages')['body']['messages'], [])
        self.assertEqual(self.request('status')['body']['total'], 0)
        self.assertTrue(self.message()['body']['discarded'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)

    def test_bulk_delete_only_selected_messages(self):
        for i in range(4): self.message(event_id='bulk-' + str(i))
        self.login()
        rows = self.request('messages')['body']['messages']
        ids = [rows[0]['id'], rows[2]['id']]
        self.assertEqual(self.request('delete', {'ids':ids})['body']['deleted'], 2)
        remaining = self.request('messages')['body']['messages']
        self.assertEqual(len(remaining), 2)
        self.assertTrue(all(row['id'] not in ids for row in remaining))
        self.assertEqual(self.request('status')['body']['unread'], 2)
        self.assertEqual(self.request('delete', {'ids':ids})['body']['deleted'], 0)

    def test_saved_status_survives_delete_and_heartbeat(self):
        self.message()
        self.login()
        saved = self.request('status')['body']['last_sms_uploaded_at']
        self.assertGreater(saved, 0)
        message = self.request('messages')['body']['messages'][0]
        self.request('delete', {'ids':[message['id']]})
        self.request('heartbeat', {'device':'Test phone'}, auth='Bearer ' + 'a'*40)
        status = self.request('status')['body']
        self.assertEqual(status['total'], 0)
        self.assertEqual(status['last_sms_uploaded_at'], saved)

    def test_phone_diagnostics_authenticated_and_backward_compatible(self):
        diagnostic = dict(queue_count=3, blocked_count=1, last_capture=1234, last_upload=1000,
                          sms_permission=True, forwarding_enabled=True, app_version='1.3.0', upload_error='HTTP 400', capture_error='')
        self.assertEqual(self.request('heartbeat', {'diagnostics':diagnostic})['status'], '401 Unauthorized')
        self.assertEqual(self.request('heartbeat', {'diagnostics':diagnostic}, auth='Bearer '+'a'*40)['status'], '200 OK')
        self.assertEqual(self.request('heartbeat', {}, auth='Bearer '+'a'*40)['status'], '200 OK')
        self.login()
        saved = self.request('status')['body']['devices'][0]['diagnostics']
        self.assertEqual(saved['queue_count'],3)
        self.assertEqual(saved['last_capture'],1234)
        diagnostic['queue_count'] = -1
        self.assertEqual(self.request('heartbeat', {'diagnostics':diagnostic}, auth='Bearer '+'a'*40)['status'], '400 Bad Request')

    def test_wrong_email_rejected(self):
        response = self.request('login', {'email':'other@example.com', 'password':'correct horse battery staple'})
        self.assertEqual(response['status'], '401 Unauthorized')

    def test_logout_invalidates_session(self):
        self.login()
        self.request('logout', {})
        self.assertEqual(self.request('status')['status'], '401 Unauthorized')

    def test_rate_limit_and_search(self):
        for _ in range(10): self.request('login', {'email':'owner@example.com', 'password':'wrong'})
        self.assertEqual(self.request('login', {'email':'owner@example.com', 'password':'wrong'})['status'], '429 Too Many Requests')
        with app.connect() as db: db.execute('DELETE FROM attempts')
        self.message(body='hello 100% _ literal')
        self.login()
        self.assertEqual(len(self.request('messages', query='q=%25')['body']['messages']), 1)
        self.assertEqual(self.request('messages', query='q=missing')['body']['messages'], [])

    def test_pagination_preserves_timestamp_order(self):
        stamp = int(time.time()*1000)
        for i in range(103): self.message(event_id=str(i), received_at=stamp-i*1000)
        self.login()
        first = self.request('messages')['body']
        second = self.request('messages', query='offset=100')['body']
        self.assertEqual(len(first['messages']),100)
        self.assertEqual(len(second['messages']),3)
        self.assertTrue(first['has_more'])
        ids = [m['id'] for m in first['messages'] + second['messages']]
        self.assertEqual(len(set(ids)),103)


if __name__ == '__main__': unittest.main()
