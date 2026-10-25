# Customization

Deployment settings belong in private `.env` files. Never put credentials into source code,
GitHub Actions variables, APK resources, README examples, screenshots or release attachments.

## Web

Set `APP_NAME` to your preferred inbox title. The server exposes only that title through
`/dashboard/api/config`; credentials and chat IDs are never included. Edit `--accent`, `--bg`,
`--paper`, `--ink` and the dark-mode variables in `web/static/style.css` to change the theme.
Rebuild with `docker compose up -d --build` after changing source files.

Set `PUBLIC_ORIGIN` to your exact HTTPS origin without a trailing slash or path. Keep the
server bound to loopback behind an HTTPS proxy. One upload-only `DEVICE_TOKEN` is supported
per deployment; devices can use different labels but share that credential. Deploy separate
instances for separate trust boundaries.

## Android

```sh
gradle -p android assembleDebug -PbridgeAppName='My SMS Inbox' -PbridgeApplicationId=org.example.myinbox
```

The Java namespace remains `org.smsbridge.app`; the installable application ID can differ.
Replace `android/app/src/main/res/drawable/ic_bridge.xml` for a custom vector icon. Keep the
application ID and release signing key stable across updates. A different signing identity
requires a separate package or uninstalling the previous app, which erases its local queue.

Every build uses manual server/key setup. There is no build-time device-token or preset-server
option. Private upload keys are saved only by the user on the device and encrypted by Keystore.

## Telegram

Set `DELIVERY_MODE=telegram` to disable browser access or `both` to retain the web inbox.
`TELEGRAM_CHAT_ID` must be the numeric destination you control. A negative ID is supported for
groups. Use one dedicated bot per deployment. Message text cannot choose a chat or issue bot
commands. There is no inbound bot command handler and no public Telegram webhook endpoint.

If you customize `message_parts()` in `web/telegram_worker.py`, keep plain-text output, bounded
chunks and the persistent part progress. Never log Telegram request URLs, tokens or SMS bodies.
