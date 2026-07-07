# Askesis — Native Android (Kotlin)

A fully native Kotlin rewrite of the Askesis tracker. **No web view, no FastAPI backend.**
The database lives on the phone (Room/SQLite) and works fully offline; data syncs
directly to a Google Sheet you own.

- **UI:** Jetpack Compose (Material 3)
- **Local DB:** Room — every write is instant and offline-first
- **Sync:** Google Sheets REST API (one tab per entity), last-write-wins by `updatedAt`
- **Auth:** Google Sign-In + OAuth token for the Sheets scope
- **Background:** WorkManager periodic sync (every ~3 h on network)

## What's in the app

Full feature parity with the web app's data model:

| Screen | Data |
|--------|------|
| Today | dashboard — weight, calories, steps, water, sleep, caffeine, macro totals, recent activity, latest measurements, latest photo. Pull-to-refresh triggers a sync. |
| Log | daily log — weight, sleep, steps, water, caffeine, feeling, ate-outside, notes |
| Body | measurements — 14 sites + notes |
| Train | activities — cardio/strength, duration, distance, calories, notes, **per-set strength editor** (sets × reps × weight) |
| Food | meals (per day) with a **food-library picker** (quantities → computed macros) + a food library with macros |
| Photos | progress photos by view (front/side/back), **camera + gallery capture**, stored locally and synced to Google Drive |
| Settings | Google sign-in, Sheet ID, manual sync, **export & share report**, theme/color |

Branding matches the web/PWA app: the original Askesis launcher icon and the
**Space Grotesk** typeface throughout.

A sync-status indicator lives in the top bar on every screen (idle / syncing /
synced / error), backed by a single serialized `SyncController`.

## Project layout

```
app/src/main/java/app/askesis/
  AskesisApp.kt          Application + manual DI container + WorkManager scheduling
  MainActivity.kt        Compose entry, applies theme from settings
  auth/GoogleAuthManager Google Sign-In + OAuth access token
  data/local/            Room: Entities.kt, Daos.kt, AppDatabase.kt
  data/prefs/            DataStore settings (sheet id, account, units, theme)
  data/sync/             SheetsApi.kt (REST), SyncEngine.kt (pull-merge-push), SyncWorker.kt
  data/repo/             AskesisRepository — the single API the UI calls
  ui/                    Compose theme, nav, screens, view-models
```

## How sync works

Each entity is one tab (`DailyLogs`, `Measurements`, `Activities`, `Meals`, `Foods`).
Every row carries a `uid` (stable identity, column A), `updatedAt` (epoch millis) and a
`deleted` tombstone. On each sync, per tab:

1. **Pull** the whole tab.
2. **Merge** into Room — a remote row wins only if its `updatedAt` is newer than local.
3. **Push** the merged local state back, rewriting the tab.

Date-keyed records (daily log, measurements) are unique per date and reuse their row's
`uid`, so editing the same day updates one sheet row rather than appending.

> Trade-off: because a push rewrites the whole tab, a concurrent edit on another device
> made *between* this device's read and write can be overwritten. Fine for personal,
> single-user use. A future version could switch to ranged appends + per-row updates.

## One-time setup (required for sync)

Sign-in works out of the box, but pulling an OAuth token for the **Sheets** scope needs a
Google Cloud project:

1. **Create / pick a Google Cloud project** at <https://console.cloud.google.com>.
2. **Enable APIs:** Google Sheets API (and Google Drive API for the future photos feature).
3. **OAuth consent screen:** External, add yourself as a Test user. Add scopes
   `.../auth/spreadsheets` and `.../auth/drive.file`.
4. **Create an OAuth client ID → Android.** Package name `app.askesis.native`, and the
   SHA-1 of your signing key:
   ```bash
   # debug key
   keytool -list -v -keystore ~/.android/debug.keystore \
     -alias androiddebugkey -storepass android -keypass android | grep SHA1
   ```
   Register that SHA-1. (For Play releases, also register your upload/app-signing SHA-1.)
5. **Create the spreadsheet** in your Drive, copy its ID from the URL
   (`docs.google.com/spreadsheets/d/`**`<THIS>`**`/edit`), and make sure it's owned by /
   shared with the account you sign in with (edit access). The app auto-creates the tabs.

Then in the app: **Settings → Sign in with Google → paste the Sheet ID → Sync now.**

> Note: no `google-services.json` / Firebase is required — auth uses the OAuth client
> registered above, matched by package name + SHA-1.

## Build & install

```bash
cd android-native
echo "sdk.dir=$HOME/Android/Sdk" > local.properties   # if not present
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Requirements: JDK 17+, Android SDK with platform 35. minSdk 26.

## Known follow-ups

- Migrate the legacy `GoogleSignIn` API (deprecated) to Credential Manager + the
  AuthorizationClient for scopes.
- Photos sync rewrites the `Photos` metadata tab wholesale like the other tabs; the
  image bytes upload to Drive once and are fetched on demand. A future optimization
  could batch Drive operations.
