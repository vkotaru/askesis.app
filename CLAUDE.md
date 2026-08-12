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

**Pre-commit checks** (these are exactly what CI runs — `.github/workflows/ci.yml`):

```bash
cd backend  && ruff check . && ruff format --check .
cd frontend && npm run check && npm run build     # svelte-check, then vite build
```

There is no test suite in this repo. `npm run check` + `npm run build` is the only frontend
safety net, so run both.

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
you need any of it. **This repo is mid-simplification** — see
`~/.claude/plans/lots-of-changes-in-eager-hinton.md` for the phased plan. Google Drive,
Sheets and OAuth are gone; the local-profile mode is the last piece still to go.

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
- `app/routers/settings.py` — `POST /api/settings/backup` streams a DB snapshot back as a
  download (SQLite via the online `backup()` API, so it is WAL-safe; Postgres as JSON).

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

SvelteKit 4 with `adapter-static` in **pure SPA mode** — `+layout.ts` sets
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
- The local-only profile (`askesis_local_user` in localStorage) disables sync entirely.
  `migrateLocalToCloud()` re-targets those rows at a real user; photos are counted but
  deliberately not migrated (they need a real upload, not a queue entry).

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
