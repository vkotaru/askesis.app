# Changelog

All notable changes to Askesis are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each released entry records the **Alembic head** it shipped with. `deploy.sh` runs
`alembic upgrade head` on every start, so rolling the container back to an older tag
does not roll the database back — that head is what you would need to
`alembic downgrade` to. See `RELEASING.md`.

`VERSION` at the repo root is the single source of truth for the version number;
`./scripts/release.sh X.Y.Z` is what moves it.

## [Unreleased]

### Added

- **Self-service first password.** Accounts created under the old Google sign-in
  carry `password_hash = NULL` and could not log in at all; the only fix was
  `manage_users.py set-password` on the server. Now `POST /auth/login` answers
  `409 {"code": "password_not_set"}` for such an account and the login screen turns
  into "set your password", which calls the new `POST /auth/set-initial-password`
  and signs the browser straight in.
  The endpoint is gated on `password_hash IS NULL`, so it closes permanently once
  an account has a password — it is a claim, not a reset, and cannot be used to
  take over an account that already has one. Every claim is logged at INFO.
  The trade-off: it does reveal that an unclaimed account exists for an identifier,
  and anyone who can reach the app can claim one. Accounts that already have a
  password keep the byte-identical generic 401. See `SELF_HOSTING.md` — claim your
  accounts promptly.
- `manage_users.py list` marks passwordless accounts `CLAIMABLE` and warns about
  them on stderr.
- A real release process. `./scripts/release.sh X.Y.Z` guards (semver, increasing,
  clean `main` in sync with origin, unused tag, non-empty `[Unreleased]`), runs the
  CI-equivalent checks, writes `VERSION`, rolls this changelog, commits and creates
  an annotated `vX.Y.Z` tag — then prints the push commands rather than pushing.
- `RELEASING.md`: cut, deploy, roll back, and what the version in the UI means —
  including the rollback caveat that the database does not roll back with the
  container.
- `GET /api/version` now returns `{version, commit, ref}`. The commit and ref are
  passed into the image as build args (`GIT_SHA`, `GIT_REF`) by `deploy.sh`, since
  `.dockerignore` excludes `.git/` and the container cannot work them out itself.
- The version under the sidebar logo is fetched from `/api/version` at runtime.
  A clean release reads `v0.2.0`; anything else reads `v0.2.0 (main@e4230a8)`, so a
  build from `main` can never be mistaken for a release. It degrades to the
  build-time version when the endpoint is unreachable (offline PWA).
- CI guards against version drift: a `vX.Y.Z` tag build fails unless `VERSION`
  matches the tag, and a change to `VERSION` fails unless `CHANGELOG.md` changed too.
- This changelog, seeded from the git history.

### Changed

- **`deploy.sh` now deploys the latest `vX.Y.Z` release tag by default**, not the tip
  of `main`. `./deploy.sh v0.2.0` pins or rolls back to a specific release;
  `./deploy.sh main` deploys unreleased work, explicitly. Tag resolution uses git's
  version sort, so `v0.10.0` beats `v0.9.0`.
- `deploy.sh` fetches and `git checkout --detach`es instead of `git pull --ff-only`
  (which cannot work from the detached HEAD a tag deploy leaves behind), refuses to
  run against a dirty working tree, and prints the target ref/commit alongside what
  is currently deployed before it touches anything.

### Security

- **`POST /api/settings/backup` handed every logged-in user the whole database.**
  It dumped every table for every user behind a bare `get_current_user`, bypassing
  `check_view_permission` entirely — so one household member could download the
  other's complete health data. Once password auth landed (0.2.0) that dump also
  carried `users.password_hash`, a bcrypt hash to crack offline and take the
  account over. It is now a **per-user** export: portable JSON, the caller's own
  rows only, driven by an explicit table allow-list (`_BACKUP_SPEC`) whose column
  set comes from SQLAlchemy metadata. `users`, `report_tokens` and `data_shares`
  are outside the format by construction, so no credential can be in a backup even
  if a future column is added. A whole-database snapshot is now an operator task
  (`pg_dump` on the box, see `SELF_HOSTING.md`); the app has no admin role and
  inventing one for two people was the wrong lever.
- **`POST /api/settings/restore` was an arbitrary-row-insert primitive.** It built
  `INSERT INTO "<table>" (<cols>)` from the uploaded file with no allow-list, so any
  authenticated user could insert a `data_shares` row granting themselves the other
  person's data, or a `users` row with a password hash of their choosing — and a
  table or column name containing `"` broke out of the quoting into raw SQL. Restore
  now validates every table and column against SQLAlchemy's metadata *before* it
  writes anything, builds statements from the `Table` object (no identifier from the
  file ever reaches SQL) with bound parameters for values, overwrites `user_id` with
  the caller's id, and skips rows whose parent meal/activity/plan is not theirs.
  `users`, `data_shares`, `report_tokens` and `alembic_version` are never written —
  an old v1 backup naming them is reported as skipped rather than failing.
- Both endpoints keep working for what they were for: back up your data, restore it.
  Value coercion is now driven by column type instead of guessing from the string's
  shape, so a note that looks like a date is no longer parsed into one.

## [0.2.0] - 2026-08-09

Alembic head: `normalize_photo_paths`

The self-hosting simplification. Everything that existed to support a hosted
deployment and native clients is gone; what is left is one PWA, one container, one
box on the tailnet.

### Removed

- Google Drive, Google Sheets and Google OAuth, along with `google_drive.py`,
  `google_sheets.py`, `encryption.py` and `scheduler.py`. Google sign-in is gone;
  username/password is the only way in.
- The native Kotlin Android app (`android-native/`), the Capacitor wrapper and its
  build scripts, and Railway support (`railway.json`, `nixpacks.toml`). Recoverable
  from tag `v0.1.0-pre-simplify`.
- Bearer-token auth. The deleted native apps were its only consumers; the httponly
  `access_token` cookie is now the single session mechanism.
- Local-profile mode (`askesis_local_user`), which existed so a native client could
  run without an account and cost four silent sync kill-switches. Stranded rows get a
  dismissible in-page migration offer after login.

### Added

- Username + password auth (bcrypt, constant-time miss path), with accounts created
  server-side via `backend/scripts/manage_users.py`. There is no self-signup.
- Photos are stored on the server's own disk under `UPLOADS_DIR`, bind-mounted at
  `./data/uploads`. `app/storage.py` owns the root with atomic writes and containment
  checked on the *resolved* path. `scripts/adopt_photos.py` links a hand-copied Drive
  export to existing rows (dry run by default; `--apply` to write).
- Self-hosted fonts (23 woff2). `fonts.googleapis.com` was the last external host and
  a cold load on a Tailscale-only box blocked on reaching Google.
- CI: an `import app.main` smoke test (ruff does not resolve imports, so deleting a
  module while an importer remains would otherwise pass lint and crash-loop the
  container) and an Alembic `upgrade head` / `downgrade base` round-trip, which
  catches `batch_alter_table` mistakes on SQLite and proves every migration reverses.
- `VERSION` at the repo root as the single source of truth, read by both the backend
  (OpenAPI version, `GET /api/version`) and the frontend (inlined by Vite).

### Fixed

- **Offline nutrition edits were silently discarded.** `getDailyNutrition` /
  `saveDailyNutrition` never touched Dexie at all, so an offline save returned a
  fabricated `{id: 0}` and the user's macros were lost. Daily nutrition now has a
  Dexie table and queues like everything else, with matching backend support in
  `sync.py`'s `TABLE_MAP`.
- **Sync clobbered unrelated rows that shared a date.** `mergeServerRecord` matched an
  incoming row by `serverId` and then fell back to *any* local row with the same date
  — for tables that legitimately hold several rows per date, an arbitrary other row.
  A pull could overwrite one activity with another, and the tombstone branch could
  hard-delete a local-only row. The date fallback now applies only to tables with a
  unique `(user_id, date)` constraint and only adopts rows the server has never seen.
- **Sign-out did not clear the session cookie.** It was a bare
  `<a href="/auth/logout">`: SvelteKit's router intercepted the click and the request
  never reached the server, and when it did the service worker could answer it from
  the cached shell. Sign-out is now a `POST /auth/logout` via `fetch`, `/auth/` is on
  the `navigateFallbackDenylist`, and `clear_auth_cookie` mirrors the flags
  `set_auth_cookie` sets instead of emitting a bare `SameSite=lax`.
- **The SQLite backup was WAL-unsafe.** `POST /api/settings/backup` read the database
  file raw, which can silently omit pages still sitting in the `-wal` file. It now
  uses the online `sqlite3.backup()` API.
- The offline read path was inverted: six list reads awaited the network and only fell
  back to Dexie on failure, so every page load blocked on a round-trip before
  painting. Reads now return Dexie immediately and revalidate in the background.
- All queued mutations failed on SQLite — `_handle_create` passed the client's
  `"YYYY-MM-DD"` string into a `Date` column, which SQLite rejects. Invisible on
  Postgres, which casts the literal.
- `/settings` minted a public report token on every page view; it now GETs the
  existing one and only mints on an explicit action.
- Unknown `/api/*` and `/auth/*` paths returned the SPA shell with HTTP 200 instead of
  a JSON 404, turning "this endpoint doesn't exist" into "HTML where JSON expected".
- Soft-deleted photos stayed fetchable by ID — `get_photo_file` ignored `deleted_at`
  while `get_photos` filtered on it.
- `sync.py`'s `_handle_delete` would `AttributeError` on `DailyNutrition`, the one
  synced table with no soft-delete column.
- Duplicate rows in Dexie survived the one-shot cleanup, which only covered daily logs
  and measurements and only matched by date. Dexie `version(4)` dedupes by `serverId`
  across every synced table, never touching rows the server has not seen.
- At narrow heights the mobile drawer's "Sign out" button overlapped the "Settings"
  nav row by 20px, so a mis-tap on Settings hit Sign out.

### Notes

- No schema change accompanied the Google removal. The nine Google columns
  (`users.google_refresh_token`, `users.picture`, five Drive/Sheets columns on
  `user_settings`, `drive_file_id` on `progress_photos` and `meals`) are still in the
  database: `drive_file_id` is the only remaining row→file mapping until the
  operator's photo export is verified. Dropping them is a separate, later migration.

## [0.1.0] - 2026-08-04

Alembic head: `p4q5r6s7t8u9` (`add_drive_askesis_folder_id`)

The pre-simplification baseline, tagged `v0.1.0-pre-simplify`. Google OAuth sign-in,
Google Drive photo storage and Google Sheets export sync; three clients (the SvelteKit
PWA, a native Kotlin Android app and a Capacitor wrapper); deployable to Railway.

Check out that tag to recover anything 0.2.0 removed.

[Unreleased]: https://github.com/vkotaru/askesis.app/compare/v0.2.0-simplified...HEAD
[0.2.0]: https://github.com/vkotaru/askesis.app/compare/v0.1.0-pre-simplify...v0.2.0-simplified
[0.1.0]: https://github.com/vkotaru/askesis.app/releases/tag/v0.1.0-pre-simplify
