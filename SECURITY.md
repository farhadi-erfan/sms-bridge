# Security and privacy

The public repository and downloads contain generic source and an unconfigured APK. They do
not contain deployment accounts, inbox data, upload keys, bot credentials or private signing keys.

- The Android app starts collecting only after explicit enablement and SMS permission.
- The upload key is encrypted using Android Keystore. Android backups and cleartext traffic are disabled.
- The device key authenticates ingestion/heartbeat only; it cannot read or delete the web inbox.
- Browser sessions use hashed random tokens, expiry, HttpOnly/SameSite cookies and server-side logout.
  Secure cookies are the default. Login attempts are rate-limited and passwords use scrypt hashes.
- Mutating browser requests require JSON and an allowed origin. Private content uses no-store responses.
  The UI displays uploaded text as text, with no HTML interpretation or third-party assets.
- Server SMS and session data are stored in SQLite. The volume is not encrypted by the application;
  protect server access, backups and disks. Avoid placing the database on a shared filesystem.
- Telegram sends to one configured chat and retries durably. Bot chats are not end-to-end encrypted.
  Content protection is a Telegram feature, not a guarantee against recipient capture or access.
- Do not expose the application port directly. Use HTTPS, maintain the host and restrict `.env` access.
  The sample proxy shares a login rate-limit bucket because forwarded client IP headers are untrusted.

Before sharing a log or screenshot, remove message text, senders, contacts, domains, credentials,
chat IDs and other identifying details. Rotate any disclosed device or bot token. To invalidate
all browser sessions, stop the service and delete rows from the `sessions` table in your private database.

Report vulnerabilities using the repository's **Security → Report a vulnerability** feature
when available. Do not put live credentials, SMS content or exploit details in public issues.
