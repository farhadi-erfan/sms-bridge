"""Generate private, deployment-specific configuration without embedding it in builds."""
import getpass
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
from app import password_hash


def main():
    target = Path(__file__).resolve().parents[1] / '.env'
    if target.exists():
        raise SystemExit('.env already exists; edit it privately instead of overwriting it.')
    origin = input('Public HTTPS origin (for example https://sms.example.com): ').strip().rstrip('/')
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname or url.path or url.query or url.fragment or url.username or not re.fullmatch(r'https://[A-Za-z0-9.:-]+', origin):
        raise SystemExit('Enter an HTTPS origin without a path or credentials.')
    mode = input('Delivery mode [web/both/telegram] (default web): ').strip() or 'web'
    if mode not in ('web', 'both', 'telegram'):
        raise SystemExit('Choose web, both or telegram.')
    values = {'PUBLIC_ORIGIN': origin, 'DELIVERY_MODE': mode, 'LOCAL_HTTP': '0',
              'DEVICE_TOKEN': secrets.token_urlsafe(48), 'DASHBOARD_EMAIL': '', 'DASHBOARD_PASSWORD_HASH': '',
              'APP_NAME': 'SMS Bridge', 'TELEGRAM_BOT_TOKEN': '', 'TELEGRAM_CHAT_ID': '', 'TELEGRAM_RETENTION_DAYS': '7'}
    if mode in ('web', 'both'):
        email = input('Inbox login email: ').strip().lower()
        if not re.fullmatch(r'[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', email):
            raise SystemExit('Enter a valid email address.')
        password = getpass.getpass('Inbox password (12+ characters): ')
        if len(password) < 12 or password != getpass.getpass('Confirm password: '):
            raise SystemExit('Passwords must match and have at least 12 characters.')
        values.update(DASHBOARD_EMAIL=email, DASHBOARD_PASSWORD_HASH=password_hash(password))
    if mode in ('both', 'telegram'):
        token = getpass.getpass('Telegram bot token from BotFather (hidden): ').strip()
        chat = input('Destination numeric Telegram chat ID: ').strip()
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token) or not re.fullmatch(r'-?[0-9]+', chat):
            raise SystemExit('Invalid Telegram token or numeric chat ID.')
        values.update(TELEGRAM_BOT_TOKEN=token, TELEGRAM_CHAT_ID=chat)
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
        file.write(''.join(f"{key}='{value}'\n" for key, value in values.items()))
    print('Private .env created with owner-only permissions. Never commit or publish it.')
    print('Copy DEVICE_TOKEN privately from .env into the Android app; use the public origin above.')


if __name__ == '__main__':
    main()
