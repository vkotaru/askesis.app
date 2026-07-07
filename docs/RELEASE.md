# Release & Play Store Setup (native Android app)

This covers the one-time setup needed before
[`.github/workflows/android-release.yml`](../.github/workflows/android-release.yml)
can ship a tagged build of the **native Kotlin app** (`android-native/`,
applicationId **`app.askesis.app`**) to Google Play. Most steps need accounts or
credentials that aren't in this repo, so an agent can't automate them.

> **Which app:** the release pipeline builds the native app in `android-native/`.
> The older Capacitor wrapper (`frontend/android/`) is retired as the shipping
> artifact — the native app takes over the `app.askesis.app` listing.

> **Backend:** the native app is backend-agnostic. The user picks a Tailscale
> server URL or a Google Sheet at runtime in **Settings**, so nothing backend-
> specific is baked into the build. §1–§2 below only matter if you want the
> in-app **"Sign in to server"** flow to work against your self-hosted server.

Once §1–§6 are done, releasing is just:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds, signs, attaches the `.aab` to a GitHub release, and uploads
to the Play **internal** track. Promote to production from the Console.

---

## 1. Google Cloud OAuth client (only for server sign-in)

The native app's "Sign in to server" opens the system browser at
`<server>/auth/mobile/login`; the server runs the Google OAuth dance and
redirects back to `app.askesis.app://auth/callback#token=<jwt>`, which the OS
routes to the app via the intent filter in
[`AndroidManifest.xml`](../android-native/app/src/main/AndroidManifest.xml).

So Google only needs the **server's** callback as an authorized redirect URI:

1. [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials),
   pick the existing OAuth 2.0 Client ID (the same one the web app uses).
2. **Authorized redirect URIs** → add your self-hosted server's callback, e.g.
   `https://askesis.<tailnet>.ts.net/auth/mobile/callback`
   (Tailscale serves a real cert, so an `https` ts.net URI is accepted.)
3. Save. No Android-specific OAuth client is required — the app never talks to
   Google directly for server auth; it only handles the final deep link.

## 2. Server env vars (self-hosted `.env` on the home server)

For the server sign-in flow to work against your self-host:

| Variable              | Value                                             |
| --------------------- | ------------------------------------------------- |
| `MOBILE_REDIRECT_URI` | `app.askesis.app://auth/callback` (this is already the default) |
| `DEV_MODE`            | `false` — the committed `.env` ships `true`, which disables auth entirely |
| `ALLOWED_EMAILS`      | include the Google account you'll sign in with    |

CORS does not apply — the native app is not a browser, so `CORS_ORIGINS` is
irrelevant to it.

## 3. Google Play Console — first-time setup

Google won't let the Play Developer API create the listing; do this once by hand.

1. Sign in to [Play Console](https://play.google.com/console/) (one-time $25 fee).
2. **Create app**: name `Askesis`, English (US), App, Free, accept declarations.
3. **App content** — complete every required item:
   - Privacy policy URL (Google **requires** one for any health-data app — host a
     simple page and link it).
   - App access (the app has a login-walled server-sync flow; describe it, or note
     that core tracking works offline with no account).
   - Ads (no), Content rating questionnaire, Target audience, News app (no).
   - Data safety form (what you collect, why, encryption in transit/at rest —
     honest and public-facing).
4. **Store listing**: short desc (≤80 chars), full desc (≤4000), 512×512 icon,
   1024×500 feature graphic, ≥2 phone screenshots.
5. **Build the first AAB locally** (§ below) and upload it manually via
   **Production → Create new release → Upload** (or Internal testing first). This
   first manual upload is required; later ones go through the workflow.
6. **Production → App signing**: opt in to **Play App Signing**. Google then holds
   the production key; your local keystore becomes the **upload key**.

Build the first AAB:

```bash
cd android-native
./gradlew :app:bundleRelease
# → app/build/outputs/bundle/release/app-release.aab
# Sign it with your upload key before the manual upload (Play verifies the upload key):
jarsigner -sigalg SHA256withRSA -digestalg SHA-256 \
  -keystore ../askesis-release.keystore \
  app/build/outputs/bundle/release/app-release.aab askesis-key
```

## 4. Generate the signing (upload) keystore

**Lose it and you can't publish updates — Google won't reset it.** Back it up
offline immediately.

```bash
# From the repo root. Store the passwords somewhere safe (1Password).
keytool -genkey -v \
  -keystore askesis-release.keystore \
  -alias askesis-key \
  -keyalg RSA -keysize 2048 \
  -validity 10000
```

Then base64-encode it for GitHub:

```bash
base64 -w 0 askesis-release.keystore > askesis-release.keystore.b64
```

The `.b64` contents go into the `ANDROID_KEYSTORE_BASE64` secret. Keep the
original `.keystore` safe; never commit either (the root `.gitignore` covers
`*.keystore`, but double-check before pushing).

## 5. Play Developer service account

GitHub Actions authenticates to the Play API with a service account, not your
personal login.

1. Google Cloud Console → **IAM & Admin → Service Accounts → Create**
   (`askesis-play-publisher`, no Cloud-level roles) → **Keys → Add key → JSON**.
2. Play Console → **Users and permissions → Invite new user** → the
   service-account email → app-specific access to Askesis with **Release
   manager**. It auto-accepts.
3. Paste the full JSON blob into the `PLAY_SERVICE_ACCOUNT_JSON` secret.

## 6. GitHub repository secrets

Settings → Secrets and variables → Actions:

| Secret                      | Source                                              |
| --------------------------- | --------------------------------------------------- |
| `ANDROID_KEYSTORE_BASE64`   | Contents of `askesis-release.keystore.b64` (§4)     |
| `KEYSTORE_PASSWORD`         | Keystore password from §4                           |
| `KEY_ALIAS`                 | `askesis-key` (or whatever you used in §4)          |
| `KEY_PASSWORD`              | Key password from §4                                |
| `PLAY_SERVICE_ACCOUNT_JSON` | Full JSON blob from §5                              |

(The native app bakes no backend URL, so **no `VITE_API_BASE` secret is needed**,
unlike the old Capacitor pipeline.)

After these are set, `git tag v1.0.1 && git push --tags` triggers build → sign →
GitHub release → Play upload on the **internal** track.

## 7. First release smoke test

Before tagging `v1.0.0` to production, tag something like `v0.9.0` for **internal
testing** only:

1. Add yourself as an internal tester in the Console.
2. Wait for the workflow to succeed; install via the opt-in link.
3. Log a meal offline, kill the app, reopen — confirm it persisted.
4. In Settings, set your server URL, "Sign in to server", "Sync now" — confirm
   the meal reaches the server (check the web app), and a change made on the web
   pulls back to the phone.
5. If happy: **Internal testing → Promote release → Production**.

## 8. Troubleshooting

- **`redirect_uri_mismatch` during server sign-in**: the server's
  `/auth/mobile/callback` isn't in the OAuth client's authorized redirect URIs. §1.
- **Sign-in succeeds in the browser but the app doesn't reopen**: the
  `app.askesis.app://auth/callback` intent filter isn't on the installed build
  (old APK) — rebuild + reinstall. The scheme must match the server's
  `MOBILE_REDIRECT_URI`.
- **"Not signed in to the server" / 401 after signing in**: the deep link's
  `#token=` wasn't captured, or the server is on `DEV_MODE=true` (no real JWT).
  Confirm §2 and that MainActivity received the callback intent.
- **Play upload fails "Package not found"**: the listing in §3 must be created for
  `app.askesis.app` (matches `android-native/app/build.gradle.kts`).
- **Play upload fails "Version code already exists"**: the tag's derived
  versionCode (MAJOR*10000+MINOR*100+PATCH) collides with a prior upload. Bump the
  tag.
