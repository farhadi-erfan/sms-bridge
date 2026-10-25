First standalone public release of SMS Bridge.

- Generic Android 8+ app with manual HTTPS server, upload-key and device-label setup.
- Private responsive web inbox with search, read status, deletion and phone diagnostics.
- Optional Telegram bot forwarding: web-only, Telegram-only or both destinations.
- Persistent phone and Telegram queues, safe retry handling and long Unicode message splitting.
- Docker deployment, private setup helper, customization guide and MIT license.
- Dedicated generic APK signing identity, signature report and SHA-256 checksums.

All deployment credentials are supplied by the installer. The public APK and sources have
no preconfigured account, phone number, personal server address, upload key or bot token.

Download `SMS-Bridge.apk` for Android and `sms-bridge-source.zip` for the complete server,
web interface and Android source. Follow README setup instructions before enabling forwarding.

Validation includes automated API, authentication, queue, Telegram retry and retention tests,
Android unit tests/lint, APK signature verification and source/APK privacy scans. Real-device
SMS reception and live Telegram delivery require verification in your own configured deployment.
