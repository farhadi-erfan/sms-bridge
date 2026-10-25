"""Read only recent chat metadata from your own bot; never prints tokens or SMS bodies."""
import getpass
import json
import re
import urllib.request


def main():
    token = getpass.getpass('Your bot token (hidden): ').strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token):
        raise SystemExit('Invalid token format.')
    try:
        request = urllib.request.Request(f'https://api.telegram.org/bot{token}/getUpdates',
                                         b'{"timeout":0,"limit":100}', {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read(1048576))
        chats = {}
        for update in result.get('result', []):
            chat = (update.get('message') or update.get('channel_post') or {}).get('chat', {})
            if 'id' in chat: chats[chat['id']] = chat.get('type', 'unknown')
    except Exception:
        raise SystemExit('Could not read bot updates. Check the token, connection and whether another consumer or webhook is active.') from None
    if not chats:
        print('No chats found. Send /start to your bot, then run this helper again.')
    for chat_id, kind in chats.items(): print(f'Chat ID: {chat_id} ({kind})')


if __name__ == '__main__': main()
