# Journal

Working memory for askesis.app: what we did, what we tried that **didn't** work, and the traps
worth remembering. Git says what changed; this says why, and what we already ruled out.

**Reading protocol** — entries are newest-first, so the top of the file is the recent past.
- Normal session: read the top 1–2 entries for context, then get to work.
- Designing or reworking a feature: read the **whole** journal first. The dead ends are the point —
  they are cheaper to read than to rediscover.

**Writing protocol** — add an entry when something is worth carrying forward: a non-obvious fix, an
approach abandoned and why, a constraint discovered the hard way, a decision with a rationale that
won't survive in the diff. Not every commit earns an entry; routine work does not.

Format: `## YYYY-MM-DD — Title`, newest at the top, with whichever of these sections apply:
**What changed** · **What didn't work** · **Watch out**. Keep entries short — they are read often.

Same format as `jobly.app/JOURNAL.md`, deliberately. Started 2026-09-24; everything before that
date is written from the tail end of the work rather than live, so it records the outcome and the
dead ends we still remembered, not every step.

---

## 2026-09-24 — MCP connector, stage 4: the container and its blast radius

**What changed**
- `Dockerfile` gained an `AS mcp` stage: own locked requirement set, and only the
  **six** `app/` modules `mcp_server` actually imports. The routers, `app/main.py`,
  the migrations, `backend/scripts/` and the SPA are absent — `/auth/*` and the
  Gemini call do not exist in that image, they are not merely unrouted. 305MB vs
  the app's 515MB. The stage **fails the build** if `import fastapi` or
  `import app.main` ever starts succeeding.
- `requirements-mcp.lock` — `pip-compile --generate-hashes`, 34 packages, 661
  hashes. The packages that parse untrusted bytes (starlette, h11,
  python-multipart, jsonschema) arrive transitively and were unpinned.
- `backend/scripts/mcp_db_role.sql` — least-privilege Postgres role (**H1**).
- `docker-compose.yml` — `tailscale-mcp` + `mcp` services, and an explicit
  network split: `default` (app side) / `mcpnet` (internet side), with `db` the
  only member of both.
- `tailscale/serve-mcp.json` with `AllowFunnel`. The app's `serve.json` has none
  and must never have one.

**What didn't work**
- **`${MCP_TOKEN_SECRET:?}` in compose would have broken app deploys.** Compose
  interpolates the *entire* file before running anything, so a required-var on an
  unused service makes `docker compose up` fail for the **app** on any box that
  has not configured the connector. `profiles:` does not save you — it gates
  startup, not interpolation. This repo already documents that exact trap for
  `docker-compose.dev.yml` and I walked into it anyway. Fix: `:-` defaults, so an
  empty value reaches the container and `mcp_server/config.py` fails closed with a
  readable reason, plus `profiles: ["mcp"]` to keep it out of the stack.
- **Adding a third Dockerfile stage broke `docker build` with no `--target`.**
  BuildKit builds the LAST stage, which is now `mcp` — so `release.sh` produced
  the MCP image and then failed `import app.main`, and `docker compose build`
  would have handed the **app container the MCP image**: no routers, no SPA, no
  `app.main`. Both now pass `--target` explicitly (`target: app` in compose).
  Caught only because release.sh builds and imports; nothing else would have
  noticed until the app 404'd everything.
- **`DO $$ ... :mcp_password ... $$` in the role SQL failed** with `syntax error at
  or near ":"`. psql does not substitute `:vars` inside dollar-quoted bodies. Use
  `SELECT format(...) \gexec`. Only found by running it against a real Postgres.
- **`.gitignore` has a blanket `*.sql`** (there to stop a stray `pg_dump` — which
  holds every row plus bcrypt hashes — being committable). `mcp_db_role.sql` was
  therefore silently absent from `git status`, and would have been missing on the
  server at the exact step `SELF_HOSTING.md` tells you to run. Fixed with a narrow
  `!backend/scripts/*.sql`; dumps never live there.

**Watch out**
- **`food_items` must be granted SELECT** even though no `mcp_server` module
  imports it by name — meals reach it via `selectinload(MealFoodItem.food_item)`.
  Omitting it fails only at runtime, only on a meal query.
- `users` gets **table-level** SELECT, not column-level: the ORM emits every
  mapped column, so a column grant would break the service the next time
  `models.py` gains a field. The property that matters — no write path to
  `password_hash` — comes from granting no INSERT/UPDATE/DELETE, which is not
  fragile. Verified by attacking it: all three are `permission denied`.
- No `ALTER DEFAULT PRIVILEGES`. A table added by a future migration is unreadable
  to the MCP role until someone grants it, deliberately.
- The rate limiter reads `X-Forwarded-For` **off the raw request**, bypassing
  uvicorn's middleware — so its sanitisation comes from Tailscale Serve `Set`ing
  that header, *not* from `--forwarded-allow-ips` as its docstring implies. Still
  **unverified whether Funnel supplies a real client address**; if it does not the
  per-IP bucket becomes one global bucket, which is why the login limiter also
  keys on the identifier.

## 2026-09-24 — Port 8000 closed for real: the app has no TCP listener (v2.0.0)

**What changed**
- uvicorn binds a **Unix socket** (`APP_SOCKET=/run/askesis/app.sock`) on a `./data/run` bind
  mount shared with the sidecar; `tailscale/serve.json` dials `unix:` that path. No TCP port
  exists in the deployment. Verified: 13-port scan went from `443, 8000` to `443` only.
- `deploy.sh` now smoke-tests after `up -d` — polls `$PUBLIC_URL/api/version` for the deployed
  commit, then asserts `:8000` is refused.
- Sidecar pinned to `tailscale/tailscale:v1.102.4`.

**What didn't work**
- **v1.2.5's fix — changing the bind from `0.0.0.0` to `127.0.0.1` — did nothing.** In userspace
  mode tailscaled's netstack rewrites *every* inbound tailnet connection to `127.0.0.1` with the
  port unchanged and **no allowlist** (`netstack.go`, `acceptTCP`/`forwardTCP`). Loopback is
  precisely where it delivers. **No bind address can close a port here.** Only the absence of a
  listener can. Don't try a third time.
- A private bridge network with `Proxy: http://app:8000` would also close the tailnet path, but
  keeps a real TCP listener any container on that network can reach unauthenticated. Rejected.

**Watch out**
- `APP_SOCKET` and the `Proxy` line in `serve.json` are **one setting in two files**. Either one
  alone → 502 on every request. `deploy.sh <tag>` moves both together; hand-edits do not.
- **`--forwarded-allow-ips` must be `'*'` on the socket path.** Over a UDS `getpeername()` returns
  a str, so uvicorn's `get_remote_addr()` returns `None`, and `ProxyHeadersMiddleware` evaluates
  `None in {"127.0.0.1"}` → False and **silently drops every `X-Forwarded-*` header** — no error,
  no log. Measured: `'127.0.0.1'` → `scheme=http client=None`; `'*'` → `scheme=https` + real IP.
  `'*'` is *tighter* here than the old value, because only a process with filesystem access to the
  socket can connect at all, and Serve `Set`s those headers rather than appending.
- Serve rewrites `Host` to `localhost` for unix targets (real value stays in `X-Forwarded-Host`).
  Nothing reads `Host` today; a future `TrustedHostMiddleware` would need to know.
- `rm` of a stale socket is guarded on `[ -S ]`. Unguarded it is an unbounded delete running every
  boot in a container that also mounts `./data/uploads`.
- **Nothing else in this repo makes an HTTP request.** CI and `release.sh` stop at
  `import app.main`, and `release.sh` *overrides the CMD*, so the uvicorn line is executed by no
  gate. That is why the smoke test exists — without it a bad serve target ships silently.
- `serve.json` is a **single-file bind mount**, pinned to the host file's inode. Editing it does
  not reach the running container and `tailscale serve status` keeps showing the old target. There
  is **no pre-deploy way to validate it**; nothing validates the `Proxy` string either
  (`setServeProxyHandlersLocked` logs and `continue`s), so a typo'd path is a silent permanent 502.
- First deploy failed the smoke test as a **false alarm**: `PUBLIC_URL` had a trailing slash →
  `//api/version` → the SPA catch-all answers **200 + HTML**, so the commit grep found nothing.
  Fixed in v2.1.0: slashes stripped, and "wrong commit" now reads differently from "no response".
  The general trap: a 200 from an SPA fallback is not evidence the API answered.

## 2026-08-30 — Git history rewritten to strip personal names

**What changed**
- `git filter-repo --replace-text --mailmap` over all 235 commits + 13 tags, force-pushed. Every
  commit is now `vkotaru <17078723+vkotaru@users.noreply.github.com>` (GitHub noreply, so
  contribution attribution survives). Rollback bundle: `~/.askesis/backups/askesis-prepurge-20260830.bundle`.

**Watch out**
- **`kotaru` alone must never be replaced.** It is the GitHub handle in the
  `github.com/vkotaru/askesis.app` compare URLs throughout `CHANGELOG.md` — replacing it breaks
  every changelog link. Only the given name and the gmail address were targets.
- `user.email` is set **repo-locally** to the noreply address. A fresh clone reintroduces the real
  name on its first commit unless that override is set again.
- Every pre-2026-08-30 SHA changed. Any clone made before then fails `deploy.sh`'s fetch with
  `would clobber existing tag`; fix is `git fetch origin --force --tags --prune`, then
  `git checkout -B main origin/main`. The Beelink hit this a month later.
- `git-filter-repo` on this machine needs an explicit 3.12 interpreter — the installed script's
  `#!/usr/bin/python3` shebang resolves to 3.14 while the module lives in `python3.12` site-packages.

## 2026-08-27 — The Android icon: four releases to fix one missing line

**What didn't work** — three wrong diagnoses, shipped as v1.2.1–v1.2.3:
- Flattening the circular icons to squares. Also a **branding change that was never asked for**.
- Restoring the circles — which reintroduced transparent corners and the white padding.
- Matching another app's manifest icon declarations.

**What actually worked** — `frontend/src/app.html` had **no `<link rel="manifest">` at all**.
SvelteKit does not inject one. Chrome never read the manifest, so it fell back to the favicon as a
legacy icon: white plate, shrunk. Every icon-file change was optimising an asset nothing was reading.

**Watch out**
- Verify the whole chain is *being read* before optimising what it contains.
- Icons are `purpose: 'any maskable'`, opaque, full-bleed — the round look comes from Android's
  mask, never from transparency in the file. Do not reintroduce a transparent-corner icon.
- Android caches WebAPK icons hard; a reinstall is not always enough to see a change.

## 2026-08-24 — Garmin Connect import + connector UI

**What changed**
- `app/garmin.py` pulls steps/sleep/activities; `app/scheduler.py` runs it nightly; per-field
  provenance in `daily_logs.sources` (`app/provenance.py`) so the UI can say a value came from
  Garmin. Settings panel + Sync now.

**What didn't work**
- **`--dry-run` committed everything.** `sync_user` commits internally, so the script's later
  `db.rollback()` was a no-op. Caught in the wild: the dry run reported 6 new logs, the real run
  reported 0 — because the dry run had already written them. `dry_run` now lives inside `sync_user`.
- v1.1.0 failed to build on the server: `garminconnect` needs Python ≥3.12, the Dockerfile pinned
  3.11. Every check until then had run against the venv, never the shipped image — which is why
  `release.sh` now builds the image.

**Watch out**
- Day totals (steps, water) must not be written for a partial day, or a mid-day sync overwrites a
  full day's figure with a partial one (`_DAY_TOTALS`, `partial_day`).
- The day boundary is read in `garmin_sync_tz`, not UTC; the image runs UTC and would otherwise
  close the day mid-evening local time.
