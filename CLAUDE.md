# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Askesis is a personal fitness/health tracker (daily log, nutrition, activities,
measurements, progress photos) for a small allowlisted set of users. It is Tier 1 in the
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

**Deploy**: `./deploy.sh` (git pull → `docker compose down` → `up -d --build`).
Read `SELF_HOSTING.md` first — it covers the Tailscale sidecar, the `ENCRYPTION_KEY`
constraint, and why the app gets its own tailnet hostname.

## One client

The SvelteKit PWA in `frontend/` is the only client. It stores to Dexie (IndexedDB) and talks
to the FastAPI backend same-origin over cookie auth.

The native Kotlin app (`android-native/`) and the Capacitor wrapper (`frontend/android/`) were
both deleted at tag `v0.1.0-pre-simplify`, along with Railway support. Check out that tag if
you need any of it. **This repo is mid-simplification** — see
`~/.claude/plans/lots-of-changes-in-eager-hinton.md` for the phased plan (Google Drive/Sheets
and OAuth are still present but are being removed).

## Backend (`backend/`)

FastAPI + SQLAlchemy 2.0 (`Mapped[...]` style) + Alembic. Postgres in production, SQLite for
local dev. `app/main.py` mounts every router under `/api/<domain>` (plus `/auth`) and, if
`backend/static/` exists, serves the built SPA from the same process with an index.html
fallback — that's how the single-container/Railway deploy works.

Key modules:

- `app/models.py` — the whole schema. Sync-relevant rows carry `updated_at` and
  `deleted_at` (soft delete).
- `app/routers/auth.py` — `get_current_user` is the dependency everything uses.
- `app/routers/sync.py` — the offline-sync protocol (below).
- `app/units.py` — **everything is stored canonical metric** (kg, km, cm, ml). Conversion to
  the user's preferred unit happens at the API boundary. Never persist an imperial value.
- `app/google_drive.py` / `app/google_sheets.py` — photos, meal photos and DB backups live
  in the *user's own* Drive, not on the server. Sheets export is a separate feature.
- `app/encryption.py` — Fernet-encrypts Google refresh tokens at rest, keyed by
  `ENCRYPTION_KEY` (falls back to `SECRET_KEY`). Changing the key orphans every stored token.
- `app/scheduler.py` — APScheduler background jobs (Drive backup, Sheets auto-sync). Note the
  scheduled DB backup only handles SQLite.

### Auth

Three modes share one `get_current_user`:

- **`DEV_MODE=true`** short-circuits auth entirely and returns a synthetic `dev@askesis.local`
  user. It also disables secure cookies. Anything gated on real identity can't be exercised
  in dev mode.
- **Web**: Google OAuth → `access_token` cookie. `allowed_emails` is an allowlist; anyone
  else is rejected at callback.
- **Native**: `/auth/mobile/login` → `/auth/mobile/callback` redirects to
  `app.askesis.app://auth/callback#token=<jwt>`. A `Bearer` header takes precedence over the
  cookie.

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

- **Photos never live on the server.** They go to the user's Google Drive; the DB stores
  `drive_file_id`. A user who hasn't linked Drive has no working photo feature, and the
  service worker caches `/api/photos/file/*` for 90 days.
- **The native Kotlin app is not a client of this repo's sync protocol.** It has its own
  reconciliation (`android-native/.../data/sync/`, `SyncBackend` with two implementations)
  where a push *rewrites a whole Sheets tab*. Changes to `/api/sync/*` need a matching change
  in `ServerSyncEngine.kt`.
- `analysis/` is a separate `pip install -e .` package for offline notebook analysis of an
  exported `.db` file. It is not part of the app or CI.
- Adding a router means touching both `app/routers/` and the `include_router` block in
  `app/main.py`.
