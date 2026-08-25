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

- **A weekly targets tile on the dashboard.** Two progress bars for run and bike
  distance, and a row of discipline chips that light up once you log an activity
  of that kind — a plan for the week rather than a tally, so each chip is either
  done or not. Targets live in `user_settings` (`weekly_run_km`,
  `weekly_bike_km`, `weekly_disciplines`) and are set in Settings → Weekly
  Training Plan; distances are stored in km and converted for display, so
  switching between mi and km cannot move the goalposts. A target left blank
  renders no bar at all, rather than a goal of zero you are permanently short of.
- **`lib/utils/disciplines.ts`** — one answer to "what kind of training was
  that?", shared rather than re-derived per call site. The dashboard previously
  matched run and bike by name inline, and nothing could recognise the rest.
  Evidence is weighted: name first (the only signal that survives hand entry,
  and Garmin puts the discipline in it), then `icon`, then `activity_type` —
  which has two values and so can only ever be a fallback. An unrecognised
  cardio activity stays unclassified rather than being guessed as a run, since a
  guess lights the wrong slot in the plan.

### Fixed

- **Garmin gave yoga and pilates no icon**, and files both under `strength`, so
  a stretching session was indistinguishable from a lifting one. They now map to
  a `stretch` icon.
- **A trail run counted as a hike.** `trail_running` mapped to the `mountain`
  icon, which is also what `hiking` maps to, so nothing downstream could tell
  them apart. It maps to `footprints` now, like every other kind of running.

## [1.1.2] - 2026-08-25

Alembic head: `add_daily_log_sources`

### Fixed

- **`garmin_sync.py --dry-run` wrote everything and said it hadn't.**
  `sync_user` owns the transaction and commits at the end of its own body; the
  script then called `db.rollback()`, which by that point is a no-op on an
  already-committed transaction. So a dry run performed a full sync and printed
  "DRY RUN — rolled back." The flag existed to make a first sync safe to try,
  and it did the one thing it promised not to.
  `dry_run` is now a parameter of `sync_user`, next to the commit it has to
  suppress — a caller cannot undo that commit from outside, so it cannot be the
  caller's decision. No data was ever lost by this, only written earlier than
  intended: the fill-blanks and dedupe rules mean a sync is the same operation
  whenever it runs.

## [1.1.1] - 2026-08-25

Alembic head: `add_daily_log_sources`

### Fixed

- **v1.1.0 could not be built.** `garminconnect` requires Python >= 3.12 from
  0.3.3 onward, and the Dockerfile pinned `python:3.11-slim`, so
  `pip install -r requirements.txt` failed on the server. The image is now
  `python:3.12-slim`, matching `backend/venv` — the skew between the two is the
  whole reason this got through, since every pre-release check runs against the
  venv. Pinning `garminconnect` back to 0.3.2 was the alternative and was
  rejected: it means an older client of a library that already tracks a moving
  target. Nothing was ever deployed with the broken build; `deploy.sh` failed
  closed and left v1.0.0 running.
- **`scripts/release.sh` now builds the Docker image** and runs the import and
  migration smoke tests inside it. Deploying *is* `docker compose build`, so
  every earlier check — all of which ran against the venv — could pass while
  the deployable artifact was broken. That is exactly what happened, and a tag
  is the expensive place to discover it, releases being immutable.

## [1.1.0] - 2026-08-24

Alembic head: `add_daily_log_sources`

### Added

- **`docker-compose.dev.yml`** — the frontend toolchain as compose services, so
  a machine with Docker but no Node can run the dev server and the pre-commit
  checks: `docker compose -f docker-compose.dev.yml run --rm npm run check`, and
  `... up vite` for the dev server. `frontend/npm.sh` wraps it (execing the real
  `npm` when one exists, so it is a no-op where Node is installed) and
  `run-dev.sh` goes through that, keeping one definition of the toolchain rather
  than two that drift.
  A separate file rather than a service in `docker-compose.yml`, because that
  one is the production deploy and declares `POSTGRES_PASSWORD`/`TS_AUTHKEY` as
  required — Compose interpolates the whole file before running anything, so a
  dev service there would refuse to start on any machine without the production
  secrets, and `profiles:` gates startup rather than interpolation. It pins
  `name: askesisapp-dev` so it cannot share the production stack's namespace,
  and Compose does not auto-merge a `.dev.yml`, so `deploy.sh` is unaffected.
  Three details worth keeping: the *repo root* is mounted rather than
  `frontend/`, since `vite.config.ts` reads `../VERSION`; the container runs as
  the calling uid, or `build/` and `.svelte-kit/` come back root-owned; and the
  dev server needs `network_mode: host` because the vite proxy targets
  `http://localhost:8000`, which inside a bridged container is the container
  itself — which makes that one service Linux-only.
- **`scripts/release.sh` runs its frontend checks through `frontend/npm.sh`**, so
  a release can be cut from a machine that has Docker but no Node. It called
  `npm` directly, which simply is not there on such a box.
- **A Garmin panel in Settings**, and the two endpoints behind it
  (`GET/POST /api/integrations/garmin/{status,sync}`). The import had no UI at
  all: no way to tell whether it was alive, when it last ran, what it filled, or
  whether a value came from the watch or from you. It now reports all four and
  gives you a **Sync now** button.
  It diagnoses but does not connect — logging in stays the one-time
  `scripts/garmin_sync.py --login`, because that needs an interactive MFA code
  and would otherwise mean this app handling a Garmin password. When the cached
  session dies the panel says so and shows the command to run. A 429 is reported
  as its own state, deliberately distinct: telling someone to log in again while
  Garmin is rate-limiting them is how a short block becomes a long one.
  The manual trigger runs on a thread and shares a lock with the scheduled job,
  so a hand-pressed sync can never land on top of the nightly one — two
  concurrent Garmin sessions is precisely the 429 trap the module warns about.
  Run state is held in memory and lost on restart, which the panel reports as
  "not since the server started" rather than as "never".
- **Per-field provenance on daily logs** (`daily_logs.sources`,
  `app/provenance.py`), surfaced as a small watch icon next to any value your
  device filled in. Comma-separated `field:owner` pairs, matching how `feelings`
  is already stored. An absent entry means *unknown*, which is every row
  predating the column and which behaves exactly as before, so the migration
  changes the meaning of no stored data.
  The badge is the visible half. The half that matters is that Garmin can now
  correct **its own** values: fill-blanks-only was the only safe rule without
  provenance, and it froze whatever first landed in a NULL column forever. The
  rule is now "fill a blank, or update a value I wrote myself", and the
  never-overwrite-a-person guarantee gets *stricter* — a field you deliberately
  cleared is marked `manual` on a NULL and is left blank rather than refilled.
  `sources` is server-owned: it is stripped from anything the client pushes
  back, so a cached row round-tripping through the sync queue can't relabel the
  watch's numbers as your own.
- **Nightly Garmin sync** (`app/scheduler.py`, APScheduler — the same library
  `briefing-bot` uses). Off unless `GARMIN_SYNC_ENABLED=true`. Once enabled the
  integration needs no shell at all: the cached session refreshes itself on
  every run and writes the renewed token back, so a schedule that runs keeps
  itself logged in indefinitely.
  The job never raises — a failed night logs and waits for tomorrow — and it
  refuses to guess which account the watch belongs to when more than one exists.
  Started from a FastAPI lifespan rather than at import, so `import app.main`
  still spins up no threads and touches no network.
- **`GARMIN_EMAIL` / `GARMIN_PASSWORD` as unattended recovery.** Consulted only
  when the cached token is missing or rejected — a lost volume, a changed
  password — so recovery doesn't need a terminal. Unset by default: a password
  in `.env` is readable through `docker inspect`, and it cannot help an account
  with 2FA. A 429 is never escalated into a credential login, because answering
  a rate limit with a fresh login is how a short block becomes a long one.
- **Garmin Connect import** (`app/garmin.py`, `scripts/garmin_sync.py`). Pulls
  steps, sleep and activities into `DailyLog` and `Activity`. Two rules make it
  safe to re-run on an overlapping window, which is the intended mode:
  activities dedupe on `(user_id, source, external_id)` via the new unique
  constraint, and daily logs **only fill blank fields** — a hand-entered step
  count or sleep figure is never overwritten by the watch.
  Garmin rate-limits logins by IP, so the session token is cached on disk and
  reused: an operator runs `--login` once, interactively, answering MFA at the
  prompt. **No Garmin password is stored** in `.env` or the database, which
  keeps the reversible-secret mechanism removed in v1.0.0 removed.
  Units convert at the boundary as everywhere else — Garmin's metres and float
  seconds become km and minutes — and the activity date comes from
  `startTimeLocal`, the device's own wall clock, so an evening workout stays on
  the day it happened.

### Fixed

- **Garmin wrote the in-progress day as if it were finished.** `sync_user`
  always included today, and steps and hydration are running totals — so a pull
  at midday recorded a lunchtime figure. Because daily logs only ever fill NULL
  columns, that partial number was then frozen: no later sync could correct it,
  and the day stayed wrong until you noticed and retyped it. Day totals are now
  skipped for a day still in progress and picked up once it closes. Sleep is
  still written for the current day — under the wake-up-day convention the night
  ending this morning is already complete.
- **A zero step count from Garmin was permanent.** `sleep_hours_from` and
  `water_ml_from` both guard against a falsy reading; the steps path did not, so
  a `0` for a day Garmin had no data on was written into the blank and locked
  there. Same guard now applies.
- **The Garmin schedule ran on the container's clock, not yours.** The image
  runs UTC, so both the cron hour and the day boundary were UTC — for anyone
  west of Greenwich the "nightly" pull fired in the evening and closed a day
  that had not ended. New `GARMIN_SYNC_TZ` (an IANA zone) drives both; with it
  set, `GARMIN_SYNC_HOUR=3` means 03:17 local everywhere. `tzdata` is now a
  dependency — a pure-Python wheel `zoneinfo` falls back to, so the image needs
  no system timezone database and no `TZ` plumbing.
- **Operator docs pointed `pg_dump` at a service that doesn't exist.**
  `SELF_HOSTING.md` said `docker compose exec -T postgres`; the Compose service is
  `db`, so the documented backup command failed outright.
- **The documented volume migration could silently do nothing.** The one-time copy
  out of the old `uploads` named volume hardcoded `askesis_uploads`, but Compose
  derives the project name from the directory (`askesis.app` → `askesisapp`), so
  the real name is `askesisapp_uploads`. `docker run -v <name>:/from` *creates* a
  missing volume rather than failing, and the command swallowed errors with
  `2>/dev/null || true`, so a wrong name copied nothing and read as "nothing to
  migrate". Now it confirms the name first and fails loudly.

### Changed

- **Database dumps are written to `~/.askesis/backups/`**, not into the checkout.
  Both docs used a bare redirect, which put a file containing every health record
  and the `users` bcrypt hash inside the git working tree. `*.sql` is now
  gitignored as well, so a stray dump can't be committed.

## [1.0.0] - 2026-08-12

Alembic head: `add_password_changed_at`

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

[Unreleased]: https://github.com/vkotaru/askesis.app/compare/v1.1.2...HEAD
[1.1.2]: https://github.com/vkotaru/askesis.app/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/vkotaru/askesis.app/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/vkotaru/askesis.app/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/vkotaru/askesis.app/compare/v0.2.0-simplified...v1.0.0
[0.2.0]: https://github.com/vkotaru/askesis.app/compare/v0.1.0-pre-simplify...v0.2.0-simplified
[0.1.0]: https://github.com/vkotaru/askesis.app/releases/tag/v0.1.0-pre-simplify
