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

## 2026-09-25 — Strength logging, stage 1: schema, migration, catalogue API

**What changed**
- `exercise_catalog` (shared), `exercise_sets` (per-set rows), and `exercises`
  gains `catalog_id` + `position`, an index on `activity_id`, and the cascade it
  was the only parent in the codebase to lack.
- `/api/exercise-catalog` CRUD + `/{id}/last`; activities now accept nested sets.

**Watch out**
- **`UNIQUE(user_id, name)` cannot dedupe the shared rows.** SQL treats NULLs as
  distinct, so `(NULL, 'Squat')` twice passes a composite unique constraint. For
  a library two people write into, duplicate names are *the* obvious failure —
  so the shared half needs a **partial unique index** (`WHERE user_id IS NULL`)
  on top. Verified both halves: a second shared "Squat" is rejected, a private
  one with the same name is still allowed.
- **Shared catalogue, private history — and they must be tested separately.**
  `_visible()` returns shared ∪ mine; `/{id}/last` joins through `Activity` to
  filter on the owner. Verified with two accounts logging the same movement on
  the same day: both see the entry, each gets their own numbers back (100kg vs
  40kg). Getting only one of these right looks like it works.
- **The update path must `db.delete()` each exercise, not bulk `.delete()`.** A
  bulk delete emits one DELETE and bypasses the ORM relationship, orphaning
  every child set row. Verified: 0 orphans after replacing a session's contents.
- The backfill preserves what it cannot parse. `"60s,60s,45s"` has no integer rep
  count, so those sets are created with null reps and the original string is
  appended to the exercise note rather than dropped. `"10,10,8,8"` round-trips
  exactly through `downgrade`.
- **The app warns about this itself** — `import app.main` prints "Tables absent
  from the backup spec" for any table missing from `_BACKUP_SPEC`. Worth reading
  the startup output after adding a table.

## 2026-09-24 — Weekly calorie average divided by 7 regardless

**What changed**
- `weekCaloriesAvg` averages over days that have a figure, not over the calendar
  week, and the heading says how many days it covers when that is fewer than 7.
- The mobile rail is 48px rather than 56px, the page gutter is 12px rather than
  16px on phones, and dashboard cards are `p-4 md:p-6`. Net: content inside a
  card on a 390px screen goes 254px -> 286px, recovering 32 of the 56px the rail
  had taken.
- The four snapshot tiles no longer break between a value and its unit.

**Watch out**
- `Math.round(weekTotalCalories / 7)` made an unfinished week read as
  starvation: two logged days totalling 4,419 reported as **631 cal/day**. The
  protein, carbs and fat averages beside it already filtered to days with data —
  calories was the single one that didn't, which is why it looked plausible
  rather than obviously broken.
- The heading now carries "over N days". An average whose denominator is not the
  obvious one has to say so, or it is just a smaller number with no explanation.
- **Padding compounds.** The rail cost 56px, but the visible squeeze was worse
  than that: page gutter *and* card padding both sat inside it, so 24px of card
  padding on each side was being spent on a column that had already lost 56px.
  When a layout gains an edge element, check the paddings nested inside it.

## 2026-09-24 — The backfill window could not actually backfill

**What changed**
- `sync_user` fetches the whole window's steps in one ranged call. When that
  response omits a day, that day now gets its own single-day request instead of
  being skipped, and `SyncReport.steps_backfilled` names every day repaired that
  way.

**Why it mattered**
- The overlapping window exists so a failed or missed run is repaired by the
  next one. But the repair only ever re-issued the *same ranged call* — so a day
  that call omits is missed again on every subsequent sync, forever. Syncing
  "again" fixed today and left yesterday permanently blank, which is the opposite
  of what a catch-up window is for. Reported as: "I synced and only got today's
  steps, I'm only seeing yesterday's bike."
- The repair is **recorded, not silent**. A window that keeps needing per-day
  patching is saying something about the upstream endpoint, and hiding that would
  turn a diagnosable pattern into folklore.

**Watch out**
- `steps_by_day.get(iso)` cannot distinguish "absent" from "present and zero" —
  the fallback keys off `iso not in steps_by_day` for that reason. A zero is a
  real answer meaning the day was measured and empty.
- Verified with a fake client whose ranged call deliberately omits yesterday:
  one single-day request follows, the value lands, and the summary names the day.
- That test also showed the importer's `today` running a day ahead of the
  machine's local date, because `garmin_sync_tz` defaults to **UTC**. Harmless
  for the window (it is wide enough), but it means an unset timezone silently
  shifts which day counts as "in progress" for anyone west of Greenwich.

## 2026-09-24 — Today's steps were being withheld on purpose, and it read as a bug

**What changed**
- Removed the `partial_day` suppression in `app/garmin.py`. Steps and water for a
  day still in progress are now written like everything else.

**What didn't work — the reasoning that put it there**
- The guard existed because a cumulative total is "meaningless until the day is
  over", so a mid-day count should not become the day's value. Both halves were
  wrong. It is **self-correcting**: a field this importer owns is refreshed on
  every later run (`owned_by` falls through to `setattr`), and the sync window
  re-reads the last few days, so a partial number is replaced as the day fills in
  and finalised once it ends. And withholding is **not neutral** — with bike
  equivalents now stacked on the same bar, today showed a blue cycling block and
  no green walking at all, which reads as a broken import rather than a
  deliberate silence.
- The general lesson: refusing to show a number is a UI decision, not a safe
  default. "Meaningless until complete" was reasoning about data purity in a
  place where the user was reasoning about whether the app was working.

**Watch out**
- The protections that actually matter are separate and still hold: `is_manual`
  means a value you typed is never overwritten, and a field you deliberately
  cleared stays cleared. Verified all four cases — partial write, later
  correction, manual value, cleared field.
- A day synced once and never again keeps its partial count. Strictly better
  than no count, but worth knowing if the schedule stops.

## 2026-09-24 — Daily Log rebuilt around the two fields still typed by hand

**What changed**
- `/daily-log` now leads with a quick-entry card: weight, four meal calorie
  boxes with a computed total, and protein/carbs/fat. Everything else the page
  records — sleep, steps, water, caffeine, ate-out, feelings, notes — moved
  under a collapsed "More". Nothing was deleted.
- **No migration.** The existing schema already fits: a `Meal` row carrying a
  label and `calories` with no food items is valid, and the nutrition tab and
  dashboard both just sum `calories`, so neither has to know these were typed
  rather than itemised. Macros go to `DailyNutrition`, weight to `DailyLog`.

**Why this shape**
- Garmin supplies steps, sleep and activities. The scale app and the food
  tracker do not sync, so weight and calories are the whole daily task — and
  logging individual foods was abandoned as too much friction. The user is
  copying four numbers out of another app, not building a food diary, and the
  meal-logging UI was the wrong tool for that.

**Watch out**
- **`offlineApi.getMeals()` answers from Dexie and refreshes in the background**,
  so on a device that has not cached that date it returns `[]` and the real rows
  arrive later. Fine for a chart, wrong for a form: you would see blank boxes for
  a day you had already filled in, and typing into them would create duplicate
  rows. Relying on the `dataVersion` bump to repair it did **not** work
  reliably — verified empty after a 28 s wait on a cold profile. The form now
  falls back to `api.getMeals()` when the cache returns nothing, wrapped so
  offline stays empty rather than throwing.
- **A label can legitimately have several rows** (the nutrition tab itemises).
  Editing one of them from a single box would silently disagree with the total,
  so those boxes show the sum, go read-only, and point at Nutrition. Verified by
  adding a second Breakfast: 437 + 150 renders as a locked 587.
- Only a real number creates a row — tabbing through an empty box must not
  litter the day with zero-calorie meals.
- The card follows background refreshes but **refuses to while focus is inside
  it**, so a half-typed calorie count is never replaced mid-keystroke.

## 2026-09-24 — Mobile left rail, and bike as equivalent steps

**What changed**
- The mobile bottom bar is gone, replaced by a 56px icon rail down the left
  (`Layout.svelte`). The bar held eleven destinations in a strip about five fit
  in, so the rest needed scrolling a nav that gave no sign it scrolled, and it
  ate the bottom of every screen. The rail mirrors the desktop sidebar, keeps
  navigation one tap (a drawer alone would make it two), and the hamburger still
  opens the labelled menu as the accessible path to the same links.
- `lib/utils/stepEquivalent.ts` converts cycling to walking-equivalent steps, and
  `StepsBarCard` stacks it on the walked figure in a second colour.

**Watch out**
- **The conversion is energy-based, not a per-minute constant**, and that was the
  explicit ask. 2011 Compendium of Physical Activities: cycling to/from work at a
  self-selected pace is **6.8 METs** (code 01011), walking is **3.5** (17190), so
  `kcal = min x (MET x 3.5 x kg / 200)` and `steps = kcal / kcal_per_walking_step`.
  A flat "150 steps/min" rule undercounts a commute by about a third, because a
  minute of cycling costs roughly twice a minute of walking.
- **Body weight cancels out** whenever the calories are *derived* — it appears in
  both the ride's kcal and the per-step kcal. Verified: 55/70/90/110 kg all give
  6,411 steps for the same 30-minute commute. It only changes the answer when
  Garmin supplied a measured calorie figure, which is the case we want it in.
- **`log.weight` is in the user's preferred unit, not kg.** The API converts at
  the boundary, so the energy formula needs `weightToMetric()` first. `distance_km`
  on activities *is* canonical km — the two are inconsistent, which is the trap.
- The bar must scale on the **combined** total; scaling on walked steps alone lets
  a long ride overflow the plot area.
- On riding days the bike portion legitimately dominates: a 50-minute vigorous
  ride is ~12,500 equivalent steps. Left as-is deliberately, pending a week of
  real data rather than seeded rides.
- Verified by rendering a real build with seeded data in headless Chrome over
  CDP. `--virtual-time-budget` is useless for this app: it fast-forwards the clock,
  IndexedDB callbacks never fire, and every screenshot is the loading spinner.
  Drive CDP and sleep in real time instead.

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
- **The SDK's RFC 9728 document disagreed with ours about the issuer.** It builds
  `authorization_servers` from `AuthSettings(issuer_url=AnyHttpUrl(...))`, and
  pydantic's `AnyHttpUrl` normalises a bare origin by **appending a trailing
  slash** — so it advertised `https://host/` while our RFC 8414 document reported
  `issuer` as `https://host`. A client checking those agree rejects; one that
  concatenates gets `https://host//.well-known/oauth-authorization-server`, which
  **404s here** (verified). Either way: generic transport error, nothing in any log.
  Fixed by serving our own route ahead of `Mount("/")`, so both documents come
  from `oauth.py` and cannot drift apart again.
- **An unset `MCP_DB_PASSWORD` produced a service that looked up and was not.**
  Because compose has to use `${MCP_DB_PASSWORD:-}` (a required `:?` would break
  *app* deploys — see above), an unset value yields a valid DSN with an empty
  password. The container starts, `/healthz` returns 200 because it runs no
  queries, and every database-backed request 500s with `fe_sendauth: no password
  supplied`. Now a startup guard, like every other check in `config.py`.
  Second guard alongside it: **refuse the app's `askesis` role**, because the
  intuitive fix for a DB auth error is to paste in the app's `DATABASE_URL`, which
  silently undoes H1 — the whole reason the separate role exists.
- **`Invalid host header` on every request was the unix-socket Host rewrite**, and
  it is the trap recorded in the v2.0.0 entry below — written hours earlier, then
  walked straight into. Serve replaces `Host` with the proxy target's host for
  socket backends, so `TrustedHostMiddleware` and the SDK's
  `TransportSecuritySettings` only ever see `localhost` and **both allowlists are
  inert here**. Widening them to include `localhost` is necessary but deletes the
  protection, so the real check moved to `ForwardedHostMiddleware`, reading
  `X-Forwarded-Host` — which Serve `Set`s to the true incoming value and a client
  cannot forge. Verified: correct host 200, `evil.example` 421, absent 200.
  A control that only passes because it can no longer see anything is worse than
  no control, because it reads as protection in a review.
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
