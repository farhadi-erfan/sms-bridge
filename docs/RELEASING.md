# Public releases

The repository is intended to be public with a clean, generic history. Do not import a private
deployment's Git history, data directory, secrets, signing key or old APKs.

## Signing setup

Generate a **dedicated** PKCS#12 key with a generic certificate identity. Keep a private backup.
For example, after setting a random password in `APK_KEYSTORE_PASSWORD` in your shell:

```sh
mkdir -p android/.signing
keytool -genkeypair -keystore android/.signing/release.p12 -storetype PKCS12 \
  -storepass:env APK_KEYSTORE_PASSWORD -keypass:env APK_KEYSTORE_PASSWORD \
  -alias sms-bridge -keyalg RSA -keysize 3072 -validity 10000 \
  -dname 'CN=SMS Bridge, OU=Public Release, O=SMS Bridge, C=US'
```

Store the base64-encoded keystore as GitHub Actions secret `APK_KEYSTORE_BASE64` and the
password as `APK_KEYSTORE_PASSWORD`. Use the GitHub UI or CLI via standard input; do not put
secret values in shell arguments, logs or commits. The workflow restores the keystore only
inside the runner. It never receives upload credentials, a bot token, personal account details,
an inbox database or a production `.env`. Forks must configure their own signing secrets.

## Release gates

1. Update the Android version code/name and release notes in `docs/RELEASE.md`.
2. Run Python tests, the source privacy audit and JavaScript syntax checks.
3. Run **Checks** and **Public release** manually to verify the Android build, unit tests, lint,
   container build, APK signature and source/APK audit before publishing a tag.
4. Check the installable APK on a physical phone and verify both your chosen delivery path
   and pause/resume. Do not attach production SMS or credentials to bug reports.
5. Push a version tag such as `v1.0.0`. The release workflow publishes only after every build
   check succeeds. A manual workflow run builds artifacts without publishing a release.

Assets are `SMS-Bridge.apk`, `sms-bridge-source.zip`, `APK-SIGNATURE.txt` and `SHA256SUMS`.
The source ZIP includes both applications, tools and deployment instructions. GitHub also
generates its normal tagged-source downloads. Compare checksums and the signing certificate
fingerprint before installing updates. Public signing certificates are expected; private
signing keys are never included.

The built-in privacy audit scans tracked source and unpacked ZIP/APK content for common
credential formats. For a private pre-publication check, pass `--private-patterns` pointing
to an external JSON array of known private strings. Do not commit that private list. Automated
pattern checks complement a manual review; they cannot prove the absence of every secret.
