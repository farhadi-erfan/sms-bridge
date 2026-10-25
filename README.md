# SMS Bridge

A self-hosted bridge from your Android phone to a private web inbox, a Telegram bot, or both.
The Android app captures new incoming SMS only after you enable forwarding. The server stores
messages durably and acknowledges retries without creating duplicate records.

**Android 8+ · Web inbox · Optional Telegram · Docker · MIT license**

## What is included

- **Android app:** visible forwarding status, pause/resume, encrypted upload-key storage,
  durable local queue, optional contact names, background retries and connection diagnostics.
- **Web inbox:** password login, search, unread filter, read status, bulk deletion,
  pagination, phone diagnostics and responsive light/dark appearance.
- **Telegram:** private, fixed-destination bot forwarding, persistent retries, long-message
  splitting and recovery from interrupted multipart delivery. No incoming bot commands or webhooks.
- **Public release automation:** signed generic APK, complete source ZIP, signature information
  and SHA-256 checksums. The APK has no preset server, upload key, bot token or personal account.

## Quick start

1. Download the APK and source bundle from this repository's **Releases** page, or clone the repository.
2. Install Docker with the Compose plugin and Python 3.10+ on your server.
3. From the repository root, generate your own private settings:

   ```sh
   python3 tools/setup.py
   docker compose up -d --build
   ```

4. Put an HTTPS reverse proxy in front of `127.0.0.1:8765`. Adapt
   [deploy/Caddyfile](deploy/Caddyfile) to your domain. Point your domain's DNS to the server;
   Caddy needs ports 80 and 443. The Android app requires a trusted HTTPS certificate.
5. In the Android app, enter your server **origin** (for example `https://sms.example.com`),
   your private `DEVICE_TOKEN` from `.env`, and a device label. Tap **Enable forwarding**,
   grant SMS access, then **Test connection / Sync now**.
6. Send a test SMS to that phone. Open `https://sms.example.com/dashboard/` or your configured
   Telegram chat, depending on your delivery mode.

There are no default credentials. The setup tool generates a unique upload key and stores
only a password hash. `.env` is private, ignored by Git and excluded from container builds.
Data lives in the `inbox` Docker volume, not in the repository or image. Back up that volume
and `.env` privately; do not use `docker compose down -v` unless you intend to erase the inbox.

## Choose your destination

| `DELIVERY_MODE` | Behavior |
| --- | --- |
| `web` | Private browser inbox only; no Telegram requests. Default. |
| `both` | Browser inbox and Telegram forwarding for each newly uploaded SMS. |
| `telegram` | Telegram forwarding; browser UI, login and inbox APIs are disabled. |

### Telegram setup

1. Create a bot using Telegram's official **@BotFather** and keep its token private.
2. Open your new bot and send `/start`. For a private group, add the bot, allow it to send
   messages, and send a command addressed to it.
3. Run `python3 tools/telegram-chat.py`. It asks for the token without echoing it and lists
   numeric chat IDs from recent updates. Use a bot dedicated to this deployment; the helper
   cannot read updates if another application is polling it or a webhook is configured.
4. Choose `both` or `telegram` during setup, then supply that token and the numeric chat ID.
   You can also edit `DELIVERY_MODE`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
   and run `docker compose up -d --force-recreate`.

Only the configured chat receives SMS. The destination cannot be overridden by an uploaded
message. Content is sent as plain text, previews are disabled and Telegram content protection
is requested. Telegram receives the sender, text, time, device label and optional contact name;
bot chats are **not end-to-end encrypted**. Use web-only mode to keep content off Telegram.

The worker uses an at-least-once queue. Rate limits and outages retain messages for retry.
A crash after Telegram accepts a part but before the local acknowledgement can duplicate that
part. Already acknowledged parts are skipped on retry. Persistent invalid tokens or blocked
bots require fixing the configuration; undelivered messages remain queued. The public release
does not contain a working bot or contact any recipient until you configure and run it.

In Telegram-only mode, acknowledged SMS bodies are kept on the server for seven days by default;
`TELEGRAM_RETENTION_DAYS=0` removes them on the next cleanup. Pending messages are never pruned.
Deletion tombstones keep event IDs to prevent old phone retries from restoring deleted content.
In `both` mode, inbox retention is manual. Switching modes affects **new** uploads; existing web
messages are not automatically sent to Telegram. Pending bot deliveries resume when bot delivery
is enabled again. Stop the stack before rotating a bot or destination and review pending deliveries.

## Customize

- **Web title:** set `APP_NAME` in `.env`; no rebuild required.
- **Web look:** edit CSS variables in `web/static/style.css` and rebuild the container.
- **Phone identity:** change the device label in the Android app.
- **Android app name/package:** see [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md).
- **Server, password and destinations:** private environment settings, never baked into the APK.

## Build and test

```sh
python3 -m unittest discover -s web/tests -v
python3 tools/audit.py
node --check web/static/app.js
```

Android Studio can open `android/`. Command-line builds use JDK 17, Gradle 8.9 and Android SDK 35:

```sh
gradle -p android testDebugUnitTest assembleDebug lintDebug
```

Downloadable public APKs use a dedicated release signing identity. Forks should generate their
own signing key. See [docs/RELEASING.md](docs/RELEASING.md) for signing secrets and tag-based releases.
Do not distribute debug builds or reuse a private deployment's preconfigured APK.

For loopback-only development, set `DATABASE_PATH`, `DASHBOARD_EMAIL`, `DASHBOARD_PASSWORD_HASH`,
`DEVICE_TOKEN`, `PUBLIC_ORIGIN=http://127.0.0.1:8765` and `LOCAL_HTTP=1` in your shell, then run
`python3 web/app.py`. The script does not automatically load `.env`; Docker Compose does.
Keep `LOCAL_HTTP=0` in production. Device upload credentials cannot read the inbox.

## Android behavior and limits

SMS forwarding is visible and opt-in. You can pause it in the app. Queued SMS stay locally
until the server returns a valid JSON acknowledgement. A request already in flight can finish
after pausing. Keys use Android Keystore; backups and cleartext HTTP are disabled.

Only new incoming SMS are supported: no old-inbox import, outgoing SMS, MMS, RCS or other apps.
SMS can contain verification codes. The app does not send texts, delete phone messages, hide
its icon or bypass Android permission controls. Contact access is optional. After a reboot,
unlock once. Allow background activity and remove the app from battery sleeping lists where
applicable. Force-stopping prevents background work until you reopen it. Periodic jobs are
approximate; phone-specific restrictions may delay delivery.

The public app has a distinct package and signing identity. It is a separate installation;
it cannot upgrade a differently packaged or signed private build. Pause the old forwarding app
before enabling this one to avoid duplicate uploads. Physical-device reception and real bot
delivery must be verified in your own deployment.

## Project layout

```text
android/           Android application and queue policy tests
web/               API, web interface, Telegram worker and regression tests
tools/             Private setup, chat-ID lookup and release privacy checks
deploy/            HTTPS proxy example
.github/workflows/ Checks and signed public release automation
```

See [SECURITY.md](SECURITY.md) for the security model and private vulnerability reporting.
