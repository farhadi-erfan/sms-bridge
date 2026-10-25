import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import telegram_worker as worker


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB = self.temp.name + '/inbox.sqlite'
        self.environment = patch.dict(os.environ, {'DELIVERY_MODE': 'both', 'DEVICE_TOKEN': 'a' * 40,
            'TELEGRAM_BOT_TOKEN': '123456:' + 'x' * 30, 'TELEGRAM_CHAT_ID': '123456789'}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def request(self, path='ingest', payload=None):
        data = payload or {'event_id': 'test-event', 'sender': 'Example sender', 'body': 'A synthetic message',
                          'received_at': int(time.time() * 1000), 'device': 'Example phone'}
        raw = json.dumps(data).encode()
        env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/dashboard/api/' + path, 'CONTENT_TYPE': 'application/json',
               'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw), 'HTTP_AUTHORIZATION': 'Bearer ' + 'a' * 40}
        result = {}
        def start(status, headers): result.update(status=status)
        result['body'] = json.loads(b''.join(app.application(env, start)))
        return result

    def test_retry_idempotency_and_success(self):
        self.request(); self.request()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM telegram_outbox').fetchone()[0], 1)
        with patch.object(worker, 'send', side_effect=worker.DeliveryError(120)):
            self.assertTrue(worker.deliver_one(now=1000))
        with patch.object(worker, 'send') as send:
            self.assertFalse(worker.deliver_one(now=1119))
            self.assertTrue(worker.deliver_one(now=1120))
            self.assertFalse(worker.deliver_one(now=1121))
            send.assert_called_once()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT delivered_at FROM telegram_outbox').fetchone()[0], 1120)

    def test_long_unicode_and_resume_at_failed_part(self):
        self.request(payload={'event_id': 'long', 'sender': '<b>not HTML</b>', 'body': '😀' * 6000,
                              'received_at': 1000, 'device': 'Example phone'})
        with app.connect() as db: row = db.execute('SELECT * FROM messages').fetchone()
        parts = worker.message_parts(row)
        self.assertGreater(len(parts), 2)
        self.assertTrue(all(len(part.encode('utf-16-le')) // 2 <= 4000 for part in parts))
        with patch.object(worker, 'send', side_effect=[None, worker.DeliveryError()]): worker.deliver_one(now=1000)
        with patch.object(worker, 'send') as send:
            worker.deliver_one(now=2000)
            self.assertEqual([call.args[0] for call in send.call_args_list], parts[1:])

    def test_web_mode_does_not_enqueue(self):
        os.environ['DELIVERY_MODE'] = 'web'
        self.request()
        with app.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM telegram_outbox').fetchone()[0], 0)

    def test_telegram_only_disables_browser_but_accepts_phone(self):
        os.environ['DELIVERY_MODE'] = 'telegram'
        self.assertEqual(self.request()['status'], '200 OK')
        self.assertEqual(self.request('login', {'email': 'owner@example.com', 'password': 'example'})['status'], '404 Not Found')
        result = {}
        app.application({'PATH_INFO': '/dashboard/', 'REQUEST_METHOD': 'GET'}, lambda status, headers: result.update(status=status))
        self.assertEqual(result['status'], '404 Not Found')

    def test_retention_prunes_delivered_only_and_prevents_reupload(self):
        os.environ.update(DELIVERY_MODE='telegram', TELEGRAM_RETENTION_DAYS='0')
        self.request()
        with patch.object(worker, 'send'): worker.deliver_one(now=1000)
        worker.prune(now=1001)
        with app.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)
        self.assertTrue(self.request()['body']['discarded'])
        self.request(payload={'event_id': 'pending', 'sender': 'Example', 'body': 'Pending', 'received_at': 0})
        worker.prune(now=9999999999)
        with app.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 1)

    def test_send_has_fixed_destination_plain_text_and_no_preview(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        with patch.object(worker.urllib.request, 'urlopen', return_value=response) as send:
            worker.send('<script>plain text</script>')
            payload = json.loads(send.call_args.args[0].data)
            self.assertEqual(payload['chat_id'], '123456789')
            self.assertNotIn('parse_mode', payload)
            self.assertTrue(payload['protect_content'])
            self.assertTrue(payload['link_preview_options']['is_disabled'])

    def test_rate_limit_redacts_token_and_body(self):
        error = urllib.error.HTTPError('https://sensitive.invalid', 429, 'private body', {},
                                      io.BytesIO(b'{"parameters":{"retry_after":180}}'))
        with patch.object(worker.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(worker.DeliveryError) as caught: worker.send('private message')
        self.assertEqual(caught.exception.retry_after, 180)
        self.assertNotIn('private', str(caught.exception))
        self.assertNotIn(os.environ['TELEGRAM_BOT_TOKEN'], str(caught.exception))


if __name__ == '__main__':
    unittest.main()
