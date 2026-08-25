# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Askesis is a personal fitness/health tracker (daily log, nutrition, activities,
measurements, progress photos) for a handful of accounts. It is Tier 1 in the
`ai_codespace` portfolio — see the workspace `CLAUDE.md` for the cross-app conventions this
repo is expected to follow (offline-first, PWA, real auth).

## Commands

```bash
./run-dev.sh                 # both halves: venv + migrations + uvicorn :8000 + vite :5173
```

`run-dev.sh` copies `backend/.env.example` → `backend/.env` on first run, which sets
`DEV_MODE=true`. Vite proxies `/api` and `/auth` to `:8000`, so the frontend is same-origin
in dev. API docs at `:8000/docs`.

**Two compose files, and they never run on the same machine.** `docker-compose.yml` is
the production stack and runs only on the home server, driven by `deploy.sh`; it requires real
secrets and will not load anywhere else. `docker-compose.dev.yml` is the frontend
toolchain and runs only on a dev machine. Nothing in the dev file is deployed or touches
the production database.

**The frontend toolchain is containerised** in `docker-compose.dev.yml`, so a machine
with Docker but no Node can still develop:

```bash
docker compose -f docker-compose.dev.yml run --rm npm run check
docker compose -f docker-compose.dev.yml up vite          # dev server on :5173
```

`frontend/npm.sh` wraps that — it execs the real `npm` when one is on PATH and otherwise
forwards to the `npm`/`vite` service, so there is one definition of the toolchain rather
than two. `run-dev.sh` goes through it. Four things those files exist to get right, each
of which is a comment where it matters:

- **It is a separate compose file.** `docker-compose.yml` is the production tailnet deploy
  and declares `POSTGRES_PASSWORD`/`TS_AUTHKEY` as required (`${VAR:?}`). Compose
  interpolates the whole file before running anything, so a dev service living there
  would refuse to start on any machine without the production secrets. `profiles:` does
  not help — it gates startup, not interpolation. The dev file pins
  `name: askesisapp-dev` so it cannot land in the production stack's namespace.
- **The repo root is mounted**, not `frontend/` — `vite.config.ts` reads `../VERSION`, and
  a narrower mount fails as a confusing svelte-check error about a missing `/VERSION`.
- **It runs as the calling uid** (`DOCKER_UID`/`DOCKER_GID`, exported by `npm.sh`), or
  `build/` and `.svelte-kit/` come back root-owned and block the next native build.
- **`vite` uses `network_mode: host`**, because the dev proxy targets
  `http://localhost:8000`, which inside a bridged container is the container itself. That
  makes the dev server Linux-only. `npm.sh` also names that container and traps its own
  exit to remove it: `docker compose run` does *not* stop its container when the client is
  killed (unlike `docker run`), and `run-dev.sh` kills by PID on Ctrl-C — without the trap
  vite survives and holds `:5173` against the next run.

**Pre-commit checks**:

```bash
cd backend  && ruff check . && ruff format --check .
cd frontend && ./npm.sh run check && ./npm.sh run build   # svelte-check, then vite build
```

There is no test suite in this repo. `npm run check` + `npm run build` is the only frontend
safety net, so run both.

CI (`.github/workflows/ci.yml`) runs two backend checks that lint can't stand in for, and
both catch failures that only appear at container boot. Run them locally after deleting a
module or adding a migration:

```bash
cd backend
python -c "import app.main"                       # ruff doesn't resolve imports; a dangling
                                                  # importer passes lint and crash-loops
python -m alembic upgrade head && python -m alembic downgrade base   # every migration must
                                                  # be reversible, and this catches SQLite
                                                  # batch_alter_table mistakes before Postgres
```

CI also guards releases: a `vX.Y.Z` tag must match `VERSION`, and a `VERSION` change must
touch `CHANGELOG.md`. Both only fire on hand edits — `scripts/release.sh` does it right.

**Migrations** (`backend/db.sh` wraps Alembic; details in `backend/MIGRATIONS.md`):

```bash
cd backend
./db.sh new add_user_avatar   # autogenerate after editing app/models.py
./db.sh migrate               # alembic upgrade head
./db.sh status
./db.sh fresh                 # DESTRUCTIVE — dev only
```

**Releasing** (`RELEASING.md` is the full process):

```bash
./scripts/release.sh 0.3.0   # guards + CI checks, writes VERSION, rolls CHANGELOG,
                             # commits, annotated tag v0.3.0 — does NOT push
```

`VERSION` at the repo root is the single source of truth (backend reads it, Vite inlines
it). Release tags are plain `vX.Y.Z`; `v0.1.0-pre-simplify` and `v0.2.0-simplified` are
historical checkpoints, not releases. Write notes under `## [Unreleased]` in
`CHANGELOG.md` as you go — `release.sh` refuses to run with an empty section, and CI
fails any change to `VERSION` that doesn't touch `CHANGELOG.md`. Each released entry
records the Alembic head it shipped with, because that's what a rollback needs.

**Deploy**: `./deploy.sh` deploys the **latest `vX.Y.Z` tag** (fetch → `checkout
--detach` → `docker compose down` → `up -d --build`), not the tip of main.
`./deploy.sh v0.2.0` pins/rolls back; `./deploy.sh main` deploys unreleased work
explicitly. It exports `GIT_SHA`/`GIT_REF` as build args so the container can report
itself via `GET /api/version`, which is what the sidebar label reads at runtime.
Read `SELF_HOSTING.md` first — it covers the Tailscale sidecar, the photo-uploads bind
mount, and why the app gets its own tailnet hostname. **Rolling the container back does
not roll the database back** (`alembic upgrade head` runs on every start) — see
`RELEASING.md`.

## One client

The SvelteKit PWA in `frontend/` is the only client. It stores to Dexie (IndexedDB) and talks
to the FastAPI backend same-origin over cookie auth.

The native Kotlin app (`android-native/`) and the Capacitor wrapper (`frontend/android/`) were
both deleted at tag `v0.1.0-pre-simplify`, along with Railway support. Check out that tag if
you need any of it. The simplification is **done** as of v1.0.0 — Google Drive, Sheets, OAuth
and the local-profile mode are all gone (`~/.claude/plans/lots-of-changes-in-eager-hinton.md`
is the plan that was executed, kept for rationale). What remains of that work is data, not
code: the dead Google columns below, and the Drive photo export (`backend/scripts/adopt_photos.py`).

## Backend (`backend/`)

FastAPI + SQLAlchemy 2.0 (`Mapped[...]` style) + Alembic. Postgres in production, SQLite for
local dev. `app/main.py` mounts every router under `/api/<domain>` (plus `/auth`) and, if
`backend/static/` exists, serves the built SPA from the same process with an index.html
fallback — that's how the single-container Docker deploy works.

Key modules:

- `app/models.py` — the whole schema. Sync-relevant rows carry `updated_at` and
  `deleted_at` (soft delete).
- `app/routers/auth.py` — `get_current_user` is the dependency everything uses.
- `app/routers/sync.py` — the offline-sync protocol (below).
- `app/units.py` — **everything is stored canonical metric** (kg, km, cm, ml). Conversion to
  the user's preferred unit happens at the API boundary. Never persist an imperial value.
- `app/storage.py` — resolves every stored media path against `UPLOADS_DIR`. Progress and
  meal photos are written to the server's own disk; the DB stores a path relative to that dir.
- `app/security.py` — bcrypt hashing for password auth, with a constant-time miss path.
- `app/food_search.py` — falls back to USDA FoodData Central + Open Food Facts when the local
  `foods` table has few hits. `USDA_API_KEY` is optional (Open Food Facts needs no key); with
  it unset that half is simply skipped.
- `app/routers/training.py` — race-plan generation (`RACE_DISTANCES` bounds each distance's
  plan length); `TrainingPlan`/`PlannedWorkout` rows, matched against logged `Activity` rows.
- `app/routers/nutrition.py` — meal CRUD plus optional Gemini meal-photo analysis
  (`gemini-1.5-flash`). Without `GEMINI_API_KEY`, `/api/nutrition/analyze-photo` returns 503
  and nothing else changes. This is the only LLM call in the app.
- `app/routers/settings.py` — `POST /api/settings/backup` streams **the caller's own rows**
  back as portable JSON (same format on SQLite and Postgres); `POST /api/settings/restore`
  puts one back. Both are governed by `_BACKUP_SPEC`, a per-table allow-list with the
  column set taken from SQLAlchemy metadata. `users`, `report_tokens` and `data_shares`
  are never read or written — password hashes and share grants are out of the format by
  construction. Restore overwrites `user_id` with the caller's, so an uploaded file can
  never grant cross-user access, and it builds statements from `Table` objects rather than
  interpolating any name from the file. A whole-DB snapshot is an operator task
  (`pg_dump` on the box) — see `SELF_HOSTING.md`.

**Three data-movement paths, easy to confuse.** They are not interchangeable:

| Path | Endpoints | Format | For |
|---|---|---|---|
| Backup/restore | `POST /api/settings/backup`, `/restore` | JSON, `_BACKUP_SPEC` allow-list | the caller's own rows, round-trippable |
| Export/import DB | `GET /api/export/sqlite`, `POST /api/export/import-db` | a `.db` file | handing a snapshot to `analysis/` |
| CSV import | `POST /api/import/{preview,activities,daily-logs,measurements,meals}` | CSV | pulling in data from another tracker |

`backend/scripts/` holds the operator-side counterparts: `manage_users.py` (the only way to
create an account), `restore_backup.py` (restore a backup JSON from the shell), and
`adopt_photos.py` (match hand-copied photo files in `<uploads>/_inbox/` to their DB rows;
dry-run by default, `--apply` to commit).

### Auth

Username + password, and nothing else. `POST /auth/login` verifies a bcrypt hash and sets an
httponly `access_token` cookie; the cookie is the only session mechanism (no bearer headers).
`POST /auth/refresh` re-issues it, accepting a token that expired within a 7-day grace window.

There is **no self-signup**. Accounts are created on the server:

```bash
cd backend            # required — config is read relative to the working dir
python scripts/manage_users.py create --username u --email u@x --name "U"
python scripts/manage_users.py set-password --username u
```

Run it from `backend/`, not the repo root: `Settings.Config.env_file = ".env"` resolves
against the cwd, so from the root it finds no `.env` and exits on the placeholder
`SECRET_KEY` guard. In the container the same rule applies — `WORKDIR` is `/app/backend`,
so it is `docker compose exec app python scripts/manage_users.py`, without a `backend/`
prefix.

`DEV_MODE=true` short-circuits auth entirely and returns a synthetic `dev@askesis.local`
user, and disables secure cookies. Anything gated on real identity can't be exercised in dev
mode.

`get_settings()` calls `validate_production()` and **`sys.exit(1)`** if `SECRET_KEY` is still
the placeholder while `DEV_MODE` is false.

### Sharing and public reports

Two separate mechanisms, easy to confuse:

- `DataShare` + `check_view_permission(user_id, category, ...)` — a user grants another user
  read access to specific categories. Any router that accepts a `user_id` query param must go
  through `check_view_permission`, not `get_current_user` alone. The frontend side is
  `stores/viewContext.ts` (the "viewing as" mode) and `UserSwitcher.svelte`.
- `ReportToken` + `/api/report` + the `/report/[token]` route — an unauthenticated public
  link. `+layout.svelte` special-cases `/report/` as a public route that bypasses the auth
  gate; keep that in sync if more public routes appear.

## Frontend (`frontend/`)

SvelteKit 2 (on Svelte 4) with `adapter-static` in **pure SPA mode** — `+layout.ts` sets
`ssr = false, prerender = false`. There are no server routes; don't add `+page.server.ts`.
Tailwind, `lucide-svelte`, `layerchart`. `vite-plugin-pwa` with `registerType: 'prompt'`
(the `SWUpdatePrompt.svelte` component is what guarantees new JS lands before Dexie opens, so
migrations run — don't remove it).

Three layers, and the distinction matters:

1. `lib/api/client.ts` — thin `fetch` wrapper + all server-shaped types. Network only.
2. `lib/db.ts` — Dexie schema. **Versions are append-only**; add `version(N+1)` with an
   `.upgrade()` rather than editing an existing block. Rows carry `localId` (client identity),
   `serverId` (null until first sync) and `updatedAt`.
3. `lib/stores/data.ts` (`offlineApi`) — the offline-aware layer components should call.
   Writes hit Dexie first, then queue into `pendingSync`.

Plus one file that exists only to hold an invariant: `lib/merge-lock.ts` (`serializeMerge`).
Read its header before touching either merge path.

`lib/config.ts` is just an `apiUrl()` passthrough (every request is same-origin) and
`lib/auth.ts` is only `tryRefreshToken()` — auth rides on the `access_token` cookie, so every
fetch just needs `credentials: 'include'`.

### The sync protocol

```
write:  component → offlineApi → Dexie (instant) → pendingSync queue → POST /api/sync/push
read:   component ← Dexie ← GET /api/sync/changes?since=<cursor>
```

- `push` returns a per-change `{index, ok, serverId, error}` array. `lib/sync.ts` deletes
  **only** the queue entries the server confirmed `ok`, so a partial failure retries the rest.
- A `TypeError` from `fetch` is treated as "offline" (queue stays intact); a 404 means the
  server predates the sync endpoints and is a silent no-op.
- `changes` returns rows where `updated_at > since` **or** `deleted_at > since`, scoped to
  `current_user`. Client-side `mergeServerRecord` matches on `serverId`, falling back to
  `date` to avoid duplicating a locally-created row.
- `_EXCLUDE_FIELDS` in `sync.py` strips client-only fields (`localId`, `userId`, …) before
  they touch a model — extend it when adding client-side bookkeeping fields.
- `collapseQueue` folds the queue before pushing, so a create-then-delete of a row the server
  never saw doesn't insert it and then delete it — it pushes nothing.
- `applyServerIds` writes each server-assigned id back onto its local row **and** onto the
  queue entries still referencing it. Skipping that sends a local id to the server as if it
  were a server id.
- Local-profile mode is **gone**. What's left is a one-time rescue: a browser that used it
  still holds those rows in IndexedDB and nowhere else, so `countLocalProfileData()` /
  `migrateLocalToCloud()` behind `MigrateLocalDataBanner.svelte` offer to re-target them at
  the logged-in user. Photos are counted but deliberately not migrated (they need a real
  upload, not a queue entry). "Not now" hides the banner for the session only — those rows
  are the single copy of that data.

**Invariants that no single file makes obvious:**

*Every server→Dexie merge runs under `serializeMerge` (`lib/merge-lock.ts`).* Two independent
paths write server data into Dexie — `hydrateFromServer` → `mergeServerRows` (cold start, bulk)
and `pullFromServer` → `mergeServerRecord` (the incremental feed). Both are read-then-write
over `await`s, so unserialized they interleave and a fresh browser imports the whole dataset
twice. Ordering the calls at startup does not fix it; both are reachable independently
afterwards. Any new merge path must take the same lock.

*Rows are owned, and the cache is one account's alone.* This is a household app on shared
browsers, so every cached read filters `userId === currentUserId()` and every cached write
stamps it. Consequences: a row with no `userId` is served to nobody until a server merge
confirms its owner; signed out, nothing is served from Dexie at all; and reads scoped to
another user (the "shared with me" path, `_userId` truthy) bypass Dexie in **both**
directions — never served from it, never written to it.

Duplicate resolution is shared, not per-call-site: `preferRow` / `pickCanonicalRow` /
`findDuplicateDateIds` / `findDuplicateServerIds` in `db.ts` are the single tie-break, used by
both `sync.ts` and `data.ts`. Match with `pickCanonicalRow`, never `.first()` — two local rows
can claim the same server row. Dexie is at **version 5**; v3, v4 and v5 exist only to run
dedupe/ownership `.upgrade()` sweeps over the same stores.

Reads revalidate in the background and bump the `dataVersion` store only when a merge actually
changed something. Components re-read on it:
`$: if ($dataVersion !== seen) { seen = $dataVersion; reload(); }`.

## Gotchas

- **Photos live on the server's disk**, under `UPLOADS_DIR` (`./data/uploads` bind-mounted
  into the container). The DB stores a path relative to that dir, so the mount is as much
  part of the data as the database is — back both up. The service worker caches
  `/api/photos/file/*` for 90 days.
- **The Google columns are still in the database** (`users.google_refresh_token`,
  `users.picture`, five Drive/Sheets columns on `user_settings`, `drive_file_id` on
  `progress_photos` and `meals`) even though no model maps them. They are the last row→file
  mapping into the operator's Drive export and get dropped in a later, separate migration.
  SQLAlchemy ignores unmapped columns, so nothing reads them today.
- `analysis/` is a separate `pip install -e .` package for offline notebook analysis of an
  exported `.db` file. It is not part of the app or CI.
- Adding a router means touching both `app/routers/` and the `include_router` block in
  `app/main.py`.
