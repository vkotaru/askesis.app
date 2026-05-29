# Release & Play Store Setup

This document covers the one-time setup that has to happen by hand before
[`.github/workflows/android-release.yml`](../.github/workflows/android-release.yml)
can ship a tagged build to the Play Store. Most of these steps need accounts
or credentials that aren't in this repo, so they can't be automated by an
agent.

Once everything in §1–§5 is done, releasing a new version is just:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow does the rest.

---

## 1. Google Cloud OAuth client

You already have an OAuth client used for the web sign-in. Reuse it for the
Capacitor app — both the web and native flows redirect to the same backend.

1. Open the [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   and pick the existing OAuth 2.0 Client ID.
2. Under **Authorized redirect URIs**, add:
   - `https://askesisapp-production.up.railway.app/auth/mobile/callback`
3. Save.

No mobile-specific OAuth client is needed. The Capacitor app opens the system
browser (Chrome / Custom Tab), authenticates against this single web client,
and the backend redirects to `app.askesis.app://auth/callback#token=<jwt>`,
which the OS routes back to the app via the intent filter in
[`AndroidManifest.xml`](../frontend/android/app/src/main/AndroidManifest.xml).

## 2. Backend env vars on Railway

Add (or confirm) these on the production service:

| Variable               | Value                                                         |
| ---------------------- | ------------------------------------------------------------- |
| `MOBILE_REDIRECT_URI`  | `app.askesis.app://auth/callback`                             |
| `CORS_ORIGINS`         | `https://askesisapp-production.up.railway.app,https://localhost,capacitor://localhost` |

CORS defaults in `backend/app/config.py` already include the two Capacitor
origins, so this only matters if you've overridden `CORS_ORIGINS` per-env —
make sure both the web host and the two native origins are present.

## 3. Google Play Console — first-time setup

Google does not allow the Play Developer API to create the app listing. You
have to do this once by hand.

1. Sign in to [Google Play Console](https://play.google.com/console/) (one-time
   $25 developer fee).
2. **Create app**:
   - App name: `Askesis`
   - Default language: English (United States)
   - App or game: App
   - Free or paid: Free
   - Confirm guideline declarations.
3. **App content** — work through every required item:
   - Privacy policy URL (Google **requires** one for any app touching health
     data — host a simple page and link to it here).
   - App access (any login-walled features? Yes → tell Google what to expect).
   - Ads (no).
   - Content rating questionnaire.
   - Target audience and content.
   - News app (no).
   - Data safety form (describe what you collect, why, and whether it's
     encrypted in transit/at rest — be honest, this is publicly visible).
4. **Store listing**:
   - Short description (≤80 chars).
   - Full description (≤4000 chars).
   - App icon (512×512 PNG).
   - Feature graphic (1024×500 PNG).
   - At least 2 phone screenshots (16:9 to 9:16, between 320–3840 px on each
     side).
5. **Build the first AAB locally** with `./build-release.sh` and upload it
   manually through **Production → Create new release → Upload**. Promote to
   "Internal testing" (or "Production" if you're confident). This first manual
   upload is required — subsequent ones go via the workflow.
6. **Production → App signing**: after Play receives the first AAB, opt in to
   **Play App Signing** if you haven't already. From this point Google holds
   the production signing key; your local keystore becomes the "upload key"
   used only to authenticate to Play.

## 4. Generate the signing keystore

The keystore signs the AAB before upload. **Lose it and you can never publish
updates to this listing — Google will not reset it.** Back it up offline as
soon as you create it.

```bash
# Run from the repo root. Pick passwords you'll remember (or store in 1Password).
keytool -genkey -v \
  -keystore askesis-release.keystore \
  -alias askesis-key \
  -keyalg RSA -keysize 2048 \
  -validity 10000
```

You'll be prompted for:

- Keystore password (used as `KEYSTORE_PASSWORD` below).
- Distinguished Name fields (name, org, location). These show up in the cert
  but no user sees them; use reasonable values.
- Key password (used as `KEY_PASSWORD`). You can press Enter to reuse the
  keystore password; the workflow handles both cases.

Then base64-encode it for GitHub:

```bash
base64 -w 0 askesis-release.keystore > askesis-release.keystore.b64
```

The contents of that `.b64` file is what goes into the `ANDROID_KEYSTORE_BASE64`
secret. After confirming the workflow runs, you can delete the `.b64`
intermediate; keep the original `.keystore` file in a safe place. Do not
commit either to the repo (the root `.gitignore` covers the keystore by name
pattern, but double-check before pushing).

## 5. Play Developer service account

GitHub Actions uses a service account (not your personal Google login) to
authenticate to the Play API.

1. In the Google Cloud Console:
   - **IAM & Admin → Service Accounts → Create**.
   - Name: `askesis-play-publisher`. No roles needed at the Cloud level.
   - Done → open the new account → **Keys → Add key → JSON**. Download.
2. In the Play Console:
   - **Users and permissions → Invite new user** → paste the service-account
     email (looks like `askesis-play-publisher@<project>.iam.gserviceaccount.com`).
   - Permissions: app-specific access to Askesis only, with **Release manager**
     role (View app information, Manage testing tracks, Release to production).
   - Send invite. The service account auto-accepts.
3. Copy the **entire JSON file contents** (it's the multi-line `{ "type":
   "service_account", ... }` blob). Paste it into the `PLAY_SERVICE_ACCOUNT_JSON`
   secret on GitHub.

## 6. GitHub repository secrets

Settings → Secrets and variables → Actions → New repository secret:

| Secret                       | Source                                             |
| ---------------------------- | -------------------------------------------------- |
| `VITE_API_BASE`              | Optional. Defaults to the Railway prod URL. Override for staging. |
| `ANDROID_KEYSTORE_BASE64`    | Contents of `askesis-release.keystore.b64` from §4 |
| `KEYSTORE_PASSWORD`          | The keystore password you picked in §4             |
| `KEY_ALIAS`                  | `askesis-key` (or whatever you used in §4)         |
| `KEY_PASSWORD`               | The key password from §4                           |
| `PLAY_SERVICE_ACCOUNT_JSON`  | The full JSON blob from §5                         |

After these are all set, the next `git tag v1.0.1 && git push --tags` push
will trigger an end-to-end build, sign, GitHub release, and Play upload to
the **internal** test track.

## 7. First release smoke test

Before tagging `v1.0.0` to the production track, do a tag like `v0.9.0` and
let it go to **internal testing** only. Manually:

1. Add yourself as an internal tester in the Play Console.
2. Wait for the workflow to report success.
3. Install via the opt-in link Play emails to internal testers.
4. Sign in, log a meal offline, kill the app, reopen — confirm it's still
   there. Reconnect Wi-Fi, hit the web app — confirm the meal appears.
5. If happy, promote in the Play Console: **Internal testing → Releases →
   Promote release → Production**.

After that, each subsequent `vX.Y.Z` tag publishes straight to internal, and
you promote from the Console when ready.

## 8. Troubleshooting

- **`redirect_uri_mismatch` during mobile sign-in**: the
  `/auth/mobile/callback` URI is missing from the OAuth client. §1.
- **Sign-in succeeds in the browser but the app doesn't reopen**: the intent
  filter in `AndroidManifest.xml` isn't registered on the installed APK
  (you're running an old build). Rebuild + reinstall.
- **API calls 401 immediately after sign-in**: bearer token isn't being
  attached. Check `Capacitor.isNativePlatform()` returns true; check
  `@capacitor/preferences` is actually installed (not just in `package.json`).
- **CORS blocked on `capacitor://localhost`**: `CORS_ORIGINS` on Railway needs
  to include that origin. §2.
- **Play upload step fails with "Package not found"**: the package name in
  `frontend/android/app/build.gradle` (`app.askesis.app`) must exactly match
  the listing created in §3.
- **Play upload step fails with "Version code already exists"**: the tag's
  derived versionCode collides with a prior upload. Bump the tag.
