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

## 2026-10-06 — "Can't reach the server" was the server answering

Asked for: a button on the web that makes the backend investigate the Garmin
card's "Can't reach the server". The message was the first problem. Every
failure of the status request fell into one `catch` and set one boolean, so a
500, a 401 and a 404 all read as a network failure while the rest of the app
loaded fine.

**The trap under it, found only by driving a browser.** The first version
classified errors by `instanceof ApiError` and still printed "Can't reach the
server" for a 500. `fetchJSON` reads the error body with `res.json()`, and
uvicorn's 500 body is the plain text `Internal Server Error`. The parse throws
a `SyntaxError`, and the catch rethrew *any* `Error` whose message wasn't
`HTTP <n>`, so a JSON parse error escaped in place of the status. Every caller
in the app got that for every non-JSON error body: uvicorn 500s, and any HTML
error page from a proxy. Only `ApiError` may escape now. Without the browser
pass this would have shipped looking fixed: the types checked and the logic
read correctly.

**Diagnose** (`GET /api/integrations/garmin/diagnose`) runs each server-side
step in its own `try`, *including the status handler itself called
in-process*, so when that is the failing thing its exception text finally
reaches a screen. It also checks the token store is **writable**, not just
readable: every run renews the token and writes it back, so a read-only store
works once and then expires a few weeks later for no visible reason.

**What we didn't build:** a button that hands the problem to Claude to read the
server logs. It would mean the internet-facing MCP container, or a cloud agent,
holding log access. Diagnose answers the same question from inside the app with
no new trust boundary.

**Watch out**
- Diagnose makes one unauthenticated GET to connect.garmin.com. That is not the
  SSO login Garmin rate-limits by IP. Never make it log in.
- Verified at 390px with headless Chrome over CDP, using an unreadable token
  store (`chmod 000`) as the real failure: 500 → named, diagnosed; browser
  offline → "Can't reach the server"; restored → status passes.

## 2026-10-06 — The "tomorrow after 6 PM" bug was the server, not the browser

Open since August, never reproduced, and the note on it pointed at the browser:
`toISOString()` building a UTC date. **The frontend was innocent.** Every "today"
there is `format(new Date(), 'yyyy-MM-dd')`, which is local. The UTC date came
from the server: the container has no `TZ`, and four call sites used a bare
`date.today()` — the public report (its printed date *and* its 30-day windows),
three MCP tools (`_window`, the week anchor, the plan's "this week"), and the
training plan's race-date check.

`app/config.py::local_today()` is the one answer now, in `APP_TZ` falling back to
`GARMIN_SYNC_TZ`. Garmin had already met this exact bug and fixed it locally
(`app/garmin.py` reads its zone with a comment saying why); the fix stayed local,
so the next three callers repeated it. It lives in `config.py` because that file
already ships in the MCP image — a new module would need a Dockerfile `COPY`.

Reproduced and verified one evening when UTC was already on the next day: the report
endpoint, driven in-process under `TZ=UTC`, returned tomorrow's date unset
and today's with the zone.

**Watch out**
- The MCP container gets no `env_file` by design, so a new setting it needs is
  named in its `environment:` block or it silently isn't there. Both zones are.
- `requirements-mcp.lock` gained `tzdata` by seeding pip-compile with the
  existing lock as its output file, so nothing else moved. Regenerating from
  scratch per the header recipe would re-resolve every transitive pin.
- Whether the box sets `GARMIN_SYNC_TZ` was not checked (it was unreachable).
  If not, set `APP_TZ` there, or this ships and fixes nothing.
- `scripts/check_mcp_writes.py` and `check_steps_paths.py` fail against a
  reused dev DB (leftover rows from earlier runs). They are written for a fresh
  one, as CI gives them; that is not a regression.

## 2026-10-05 — A four-millisecond failure is still a failure

Two asks: fewer icons, and a Garmin sync that is not three taps into Settings.

**The rail.** It had grown to fourteen icons by always being "every section the
mode allows". An icon-only rail is legible only while it is short enough to
learn by position; past about six it is a wall of grey glyphs. `PRIMARY_NAV` in
`lib/appMode.ts` names five per mode, and a **More** button opens the same
labelled drawer the hamburger does. The drawer is unchanged — a rail that
silently drops nine destinations has to say where they went, and the header
hamburger is at the opposite corner from where the eye is.

**The bug this turned up.** The new header button first reported its outcome by
watching `running` go true→false. Tapping it did nothing visible at all, and the
reason is worth keeping: a sync with no cached session **fails in about four
milliseconds** — faster than the status request that follows the POST — so the
running state is never observed, and an edge-triggered reporter has no edge to
fire on. Verified before and after: tap, 4ms run, no spinner, no message, no way
to tell the tap had registered.

Now keyed on a *new* `last_run.started_at` captured before starting, so the
outcome is reported whether or not the run was ever seen in flight. The failure
text is shown verbatim because the common one names the command that fixes it.

The general shape, which this repo keeps meeting: **an edge-triggered UI misses
anything faster than its own polling interval**, and the fast path is usually
the error path. Compare state, not transitions.

**And the extraction, done first rather than after the drift.** Two things now
start a sync and report on it. The card owned the fetch, the 3s poller, the
"may I sync" predicate and the pull-new-rows call; a second copy would have been
a second poller on the same endpoint and two answers to the same question.
`lib/garmin.ts` holds it, refcounted so the poller stops with the last watcher.

**Watch out**
- The button renders *nothing* when no watch is configured or the configured one
  is the other account's. A permanently greyed control in a header is a
  permanent question.
- Its toast is `position: fixed` rather than anchored to the button, because the
  button is in a header at one breakpoint and a sidebar footer at the other.
  `max-w-sm` on a 390px screen overflows — the parent's padding is not part of
  the child's max-width. `max-w-full`.

## 2026-09-30 — Trends, and the thing that made it cheap

"No way to look at six months of calories." The decisive fact turned up before
any design work: **`hydrate` pulls 500 rows per table into Dexie and nothing
ever evicts them.** So a full-history view needs no endpoint, no pagination and
no network — about sixteen months of daily logs are already on the device. That
turned a backend feature into a frontend one.

A dedicated `/trends` page rather than range selectors on the dashboard cards,
because the two are answering different questions and a 6-month bar chart inside
a dashboard-sized card is cramped in a way no amount of care fixes. The
dashboard stays a this-week view, which is its job.

**Aggregation is the whole problem.** A year is ~365 points across ~310 CSS px.
`lib/trends.ts` holds the rules, in one place, because they are the same rules
three cards already implement separately:
- Average over the days that **have a figure**, never over the calendar. Two
  logged days totalling 4,400 kcal is 2,200/day, not 631. `NutritionChartCard`
  carries the same comment; this is that bug one zoom level out, where nobody
  would notice it.
- A missing day is missing, not zero. No point is invented.
- Granularity comes from the data's **actual span**, not the button pressed:
  "All" on three months of logging should still be daily.

**SVG scaling bit twice, and both are worth remembering.**
1. `viewBox="0 0 560 300"` with `height: 220px` in CSS letterboxes the drawing
   into the middle of the box — `preserveAspectRatio` defaults to `meet`. The
   chart rendered at about half the height of the card it sat in. `h-auto` and
   let the viewBox's ratio decide.
2. Every length inside a viewBox is scaled by the same factor as the box. At
   310px wide that is ~0.55, so `font-size: 10` axis labels came out at five and
   a half pixels. The sizes in that file are now chosen for how they *render*,
   and say so.

**Watch out**
- `scrollbar-hide` existed only inside `Layout.svelte`'s scoped `<style>`.
  Svelte scopes component styles, so every other use of that class in the repo
  did nothing. Moved into `app.css`.
- An x-axis labeller that keeps "every Nth, plus always the last" draws the last
  two on top of each other whenever `(n-1) % N` is small.
- The trend arrow is **grey unless the metric has an opinion**. Sleep up is
  good, steps up is good; weight is not the app's business — this install is
  used by someone cutting and someone who is not.
- Verification used a *scratch copy* of the dev database seeded with 14 months
  (`scratchpad/seed_trends.py`), not the real one. In DEV_MODE the synthetic user
  is not user 1, so a seed written against `User.first()` silently fills rows
  nobody can see.

## 2026-09-29 — The OAuth surface, finally executed instead of read

"Can this work with Gemini?" turned out to be a question about testing, not
about Gemini.

**The answer was yes, and I could only say so by reading the code.** Nothing in
the connector is Claude-specific: `_redirect_allowed` permits any loopback
redirect (RFC 8252 §7.3), `resource` is optional and defaults, PKCE is
standard, and the consent page has always rendered `client_name` from the
client's own registration — the "Claude" strings are all in comments. But
`server.py` imports the MCP SDK, CI cannot install it, and so the most
security-critical surface in the repo had *zero* executable coverage. Same
finding as the scope gate two days ago, one layer up.

`oauth.py` imports no SDK — Starlette, SQLAlchemy, pyjwt. So the entire flow
runs in-process over an httpx ASGI transport: discover, register, consent,
exchange, refresh. `scripts/check_oauth_flow.py`, 32 assertions, wired into the
MCP isolation job.

It is deliberately shaped as a client that is **not** Claude — loopback
callback on a random port, no `resource` parameter at all, `client_name` of
"Some Other CLI" — and two of its assertions are about that directly: the
consent page contains the registered name, and does not contain "Claude".

**Writing it found a real one.** A code redeemed with the wrong PKCE verifier
was rejected and left *live* for the rest of its TTL. Not brute-forceable (256
bits), but the threat model for PKCE is an intercepted code, and in that
scenario the attacker's failed attempt was costing them nothing while the
legitimate client had not redeemed yet. Now the code is burned on verification
failure. A real client never reaches that branch.

Three of the four initial failures were my *expectations* being wrong, and each
was worth learning rather than papering over:
- `scopes_supported` legitimately includes `offline_access` (that is what a
  refresh token is).
- A bad `resource` is refused **with a 302 carrying `error=invalid_target`** —
  RFC 6749 §4.1.2.1 says a client-actionable failure goes back to the client.
  The assertion that matters is "no code came with it".
- A wrong password re-renders the consent form with **401**, not 200, and
  crucially does not redirect: a failed login is not the client's business.

**Watch out**
- `MCPConfig` refuses to build under `DEV_MODE`, so the check runs with
  `DEV_MODE=false` and a throwaway `SECRET_KEY`. That is a feature — it means
  the script exercises real bcrypt authentication rather than the dev bypass.
- The check needs `pyjwt`, which is in `requirements-mcp.txt` and deliberately
  not in `requirements.txt`. CI installs that one package alone; installing the
  whole MCP tree would drag in a pydantic that conflicts with the app's pin,
  which is the split the job exists to defend. On this dev machine the venv has
  no pip, so `venv/lib/python3.12/site-packages/jwt` is a **symlink** to the
  system dist-packages copy — that is why `import jwt` works there.
- httpx 0.26 (the app tree) has no *sync* ASGI transport. The script is async so
  one file runs under either dependency tree.

## 2026-09-29 — "I saved a session with a name but don't see it in Routines"

Not a bug in the sense of a broken code path: `finishSession` writes one
Activity and has never touched `workout_templates`. A bug in the sense that
matters — the screen asked for a name, gave no indication where the named thing
went, and the app has a page called Routines full of named workouts.

Three changes, and only the first is really the fix:

1. The finish sheet now says **"Saved to Activities for Tue, Sep 29."** under the
   name box. One line of copy; the rest is what you would want once you know.
2. An "Also save as a routine" checkbox, off by default — most sessions are not
   templates, and a Routines list that grows every time you train stops being a
   list of routines. Offered only when the session did *not* come from a
   routine, since you already have that one.
3. The Routines page had no way to **start** a routine. It calls itself "saved
   workouts you repeat" and you had to go back to the dashboard to repeat one.

What crosses into the derived routine: every movement (including ones added and
never logged — they were part of the plan) and the set counts, plus the modal
rep count for movements that have reps at all. What does not: the weight. A
routine is the intention, and pinning today's load into it makes "did I hit my
targets" a comparison of a number with itself. That rule was already written
down in `ExerciseLogger.applyRoutine`, going the other way.

**Watch out**
- Routine creation is online-only, like catalogue entries and for the same
  reason: a routine references catalogue rows by *server* id. A workout finished
  offline with the box ticked therefore saves the workout and not the routine,
  and says so through the sync toast rather than failing the save — the activity
  is the irreplaceable half and is never held hostage to the convenience half.
- `startSession` from the Routines page refuses when a draft is live instead of
  replacing it. A live draft is the only copy of those sets.
- I wrote this entry and the changelog notes into a heredoc that asserted on
  `## [Unreleased]` *after* `release.sh` had already emptied that section, so the
  edit silently no-op'd and the code committed without them. Second time this
  session. If a docs edit is in the same command as the commit, read the file
  back before trusting it.

## 2026-09-29 — One page's overflow is every page's overflow

Five complaints from the first real gym session, four of them one bug each and
the third one worth writing down properly.

**"Parts moving all around."** The set row was
`grid-cols-[2.25rem_1fr_1fr_4rem_2.75rem]` with `.input` (which carries `px-4`)
in the two `1fr` cells. A `1fr` track will not shrink below its content's
min-content width, and a number input with 2rem of padding has a large one, so
the row's *minimum* width was about 400px — wider than a 360px phone. That alone
would be a contained bug. It was not contained, because `<main class="flex-1">`
had no `min-w-0`, and a flex item's `min-width: auto` means it will not shrink
below its content either. So `main` grew past the viewport, the **document**
scrolled sideways, and on a phone that pans the visual viewport — which drags
`position: fixed` elements with it. The user's screenshots show the fixed header
and the fixed nav rail at four different horizontal offsets across five
screenshots, which is exactly what that looks like and reads as "the app is
broken", not "this one screen is too wide".

Fixed in both places, and the second is the one that matters: `main` now has
`min-w-0 overflow-x-hidden`, so a too-wide page is that page's problem.

**Every field of a set that no screen shows is a field that will be dropped.**
Adding `duration_seconds`/`distance_m` meant touching six writers and renderers.
`sync.py::_write_exercises` — the path every set logged in the gym takes, since
the client queues and pushes — built its `ExerciseSet` from a hand-written
column list, so it would have accepted both fields at the REST boundary and
silently dropped them on the offline path. It now builds from
`ExerciseSetCreate.model_fields`, and `check_mcp_writes.py` asserts every one of
those is a real column.

**And a bug I shipped mid-session and caught in the browser.** The new "how is
this measured" sheet sent `{name, tracking_type}` to
`PUT /api/exercise-catalog/{id}`, whose contract is *this is the whole object*.
The server did as told and cleared the movement's muscle group, video link and
form notes — for both accounts, from a sheet that mentioned none of them.
Verified by reading the row back: `muscle_group` went from `"Core"` to `null`.

`planning.update_catalog_entry` has had `replace=False` since the MCP work; the
web app simply had no endpoint that used it. There is now a `PATCH`, and
`check_mcp_writes.py` asserts the merge semantic directly, because this is the
second time a caller has reached for the replace-everything write to change one
thing.

**Watch out**
- `interactive-widget=resizes-content` on the viewport meta is what stops the
  Android keyboard covering a `fixed` sheet. Without it the *layout* viewport
  keeps its full height and a bottom sheet is simply drawn underneath the
  keyboard; `dvh` does not help on its own, because it measures the same
  unchanged viewport. Cannot be verified headless — it needs a real soft
  keyboard.
- The duration field holds its own text while focused. `"1:"` parses to 60, and
  writing `"1:00"` back into the input mid-word would move the caret and eat the
  next keystroke.
- `formatDuration` (for inputs) and `formatDurationLabel` (for display) differ by
  one character: a bare `45` beside a rep-only movement's `12` is ambiguous, so
  the read-only one says `45s`.

## 2026-09-28 — Extracting *some* of the rules is worse than extracting none

The review of the MCP write surface found nine things. The one that mattered is
the one I should have predicted, because I had already fixed it twice in the
same session.

**The bug.** `app/planning.py` was extracted so the connector and the REST API
would share one set of rules. It took the name check and the URL scheme check
and left the **length** limits behind in the routers' Pydantic schemas — which
the MCP path never touches. So `create_exercise(notes="x" * 2508)` committed
into a `Text` column and `GET /api/exercise-catalog/` then failed its response
model on every call, permanently, for both accounts. Reproduced before fixing:
200 -> 500.

This is the third instance of one shape this session: a value that no writer
validates, stored, then rejected on the way out by a response model, leaving an
endpoint that cannot be loaded and therefore a row that cannot be deleted. The
first two were `_sanitise_exercise` on the sync push path and `_python_value` on
restore. **A partial extraction creates exactly the drift the extraction was
meant to remove**, and is harder to spot than no extraction at all, because the
module looks like it owns the rules.

The rule to carry forward: when moving validation into a shared layer, inventory
the *constraints*, not the *validators*. Pydantic `Field(max_length=...)` is a
constraint with no validator function, so reading the `@field_validator`
decorators — which is what I did — finds none of them.

**Consent could disagree with the grant.** `/authorize` renders the page from
one request and stamps the scope from the next, merging form over query. A GET
with no scope rendered "read-only"; a POST with `scope=askesis:read
askesis:write` in the *body* was granted write. Never meaningfully exploitable —
the POST carries the password — but the screen is where consent happens. Fixed
by taking scope from the query string on both methods: the form has no `action`,
so it posts to the same URL and the query survives, which makes the two the same
expression.

**Two things were claimed to be verified and were not.**
- `mcp_db_role.sql`'s "self-verifying" block was a list of bare
  `SELECT has_table_privilege(...)`. `ON_ERROR_STOP` aborts on SQL errors, not
  on a result of `f` — so wrong grants printed wrong answers and exited 0. Now a
  `DO $$ ... RAISE EXCEPTION $$` per group.
- The scope gate lived in `server.py`, which imports the MCP SDK, which CI never
  installs. Nothing in the repo could execute the single line separating a
  read-only token from a write tool. Moved to `mcp_server/authz.py` — no SDK
  imports, seven cases in the check script.

**Watch out**
- `check_mcp_writes.py` now detects a *mutating tool missing from*
  `WRITE_TOOLS` structurally, by reading each tool's source for calls to
  planning's write functions. That tool would otherwise be callable with a
  read-only token and would silently lose its write, since the commit is keyed
  on the same set.
- Run `check_steps_paths.py` on a **fresh** database. Run after
  `check_mcp_writes.py` it fails with `MultipleResultsFound` — a harness
  ordering trap, not a product bug.

## 2026-09-28 — MCP writes, and the service layer that made them safe

The connector was read-only by design, down to the database role. Making it
write meant deciding where the rules live.

**The constraint that decided the design:** `mcp_server/` cannot import
`app.routers` — CI greps for it and the MCP image has no FastAPI — and every
rule worth reusing lived inside route handler bodies. So the choice was a second
copy of each rule, or extraction. This repo had already paid for the first
option twice: three `daily_logs` write paths where only two learned the
provenance rule, and two `_write_exercises` that disagreed about empty lists.

`app/planning.py` is the answer: plain SQLAlchemy, no FastAPI, called by both.
Extracting it surfaced four real defects that had been live in the web app —
the case-sensitive URL scheme check, the unvalidated `catalog_id` on routines,
blank movement names, and targets with no bounds at all.

**Scope, and why `required_scopes` could not do the work.** The SDK reads that
list as "the token must carry ALL of these", so adding `askesis:write` there
would have locked read-only tokens out of the *read* tools. It stays at
`askesis:read`, and the write check is hand-written per tool in `_register`
against `WRITE_TOOLS`. Separately, `/authorize` had been ignoring the requested
scope entirely — a client could ask for anything and got `config.scope` stamped
on its grant with no error. It now negotiates.

**The commit is structural, not per-tool.** `SessionLocal` is
`autocommit=False`, so a tool that forgot `db.commit()` would lose its write
*silently* when `db.close()` returned the connection to the pool. `_register`
commits on success and rolls back on exception, both **inside the worker
thread** — `run()`'s `finally: db.close()` executes before the outer `except`
blocks, so a rollback attempted there would be on a closed session.

**Watch out**
- `tools.py` arguments must stay builtins. `server.py` copies annotation
  *strings* onto a handler in its own module, so `Literal`, `date` or a Pydantic
  model is a NameError at container boot — which CI cannot catch, because it
  never installs the MCP dependency set.
- The grants in `mcp_db_role.sql` are applied by hand on the live database.
  Deploying without running it means every write tool fails at runtime. The
  script's self-verifying block now asserts the new shape; it previously
  asserted the opposite and would have become a lie.
- `scripts/check_mcp_writes.py` runs all 39 cases. The ones that matter are not
  the happy paths: ownership between the two accounts, refusal rather than
  half-writing, and that `WRITE_TOOLS` still contains only planning tools.

## 2026-09-28 — The live workout: a session, not a form

Strength mode shipped as a filter — the same app with nav items and cards
hidden — and the verdict was that this is not a redesign. Correct. Logging a
workout meant Activities -> New -> a nine-field form with the set logger near
the bottom, which is record-keeping done afterwards.

**What changed:** `/workout`, a live session. `lib/stores/workout.ts` holds the
draft; `db.ts` v7 adds `liveSession`, `exerciseHistory` and `routines`.

**Decisions worth not relitigating**
- **The draft is one Dexie row, never synced.** Creating the Activity at "Start"
  and updating per set is the obvious alternative and is wrong four ways: both
  server writers delete and reinsert every set row on each update; offline that
  queues one whole-session replace per set, and `collapseQueue` folds
  create-then-delete, not update-then-update; an abandoned session would be real
  history the other account can see; and `updateActivity` attempts the network
  between every set, in the one place there is none.
- **Timers derive from stored instants, never accumulating counters.**
  `setInterval` is throttled in a backgrounded tab, so a session timed by
  incrementing seconds returns wrong after a screen lock.
- **Duration is `lastLoggedAt - startedAt`, not `now - startedAt`.** A session
  forgotten until morning must not record fourteen hours.
- **A set is `planned` until ticked.** The old form could only ever show last
  session's numbers as hints because it had no moment of confirmation. A session
  has one, which is what makes prefilling honest rather than a claim.

**What didn't work**
- `/workout` redirected home on every reload. `liveSession` is null both when
  nothing is running and before the draft has been read, and the guard treated
  those alike — it bounced out of a live workout with the draft sitting in
  Dexie. Needed `liveSessionLoaded` as a separate fact.
- The "last time" column rendered "—" forever. `lastFor()` read the history map
  from closure, so the template never saw it as a dependency and never
  re-rendered when the cache resolved — while the card header two lines above
  showed the same data correctly. Pass it as an argument.
- Three test runs described code that was no longer on disk: `backend/static`
  was a stale copy of the build, and `registerType: 'prompt'` means the service
  worker never self-updates. Rebuild, re-copy, AND unregister the worker before
  believing an offline result.

**Watch out**
- **Unverified:** reloading the page *while offline* mid-session. It restores
  correctly on the dev server and on the built app online, but in the built app
  offline it lands on `/`. `navigateFallback: '/'` is the likely cause and it is
  the "phone locked and the tab was evicted" case, so it is worth settling on a
  real device before trusting it.
- The dev server registers no service worker, so offline *navigation* can never
  be tested there. Only the built app served from `backend/static` is
  representative.

## 2026-09-28 — What the adversarial review was worth

Ten findings, all fixed. Two were the kind that only a reviewer looking for them
would find, and both are worth remembering as shapes rather than as bugs.

**Restore: "a row exists with that id" is not "that is the row."** Backups
preserve primary keys. On an install that already has a row at that id the
parent is skipped as a duplicate, and its children were then validated against
the *local* row — so one machine's squat sets were filed inside another
machine's easy run, and the response said "Restore completed." The fix is that
a child may only attach to a parent **this run inserted**; `_owned_ids` answers
reachability, which is a different question and was the wrong one to ask here.
The cross-install case now loses rows instead of corrupting them, and says so.

**A file should not be able to break an account.** `_python_value` checked
enums, dates and booleans and passed numbers and strings straight through. Both
SQLite and PostgreSQL accept a string in an INTEGER column under type affinity,
so a restored `{"steps": "lots"}` broke `GET /api/daily-log/` permanently — and
you could not delete the row, because deleting needs the list to load. The enum
branch right above it already reasoned about exactly this failure for enums.
Same class as the sync path's `_sanitise_exercise`; the hole was in the third
writer nobody had lined up beside the other two.

**Watch out**
- Three write paths reach `daily_logs`: REST, sync-update, sync-create-upsert.
  A rule added to one belongs in all three. The server-wins check was missing
  from the third for the same reason the provenance rule was: it looks like a
  create and is actually an update.
- `{#each}` over anything containing `<svelte:component>` must be keyed. Three
  instances found so far (nav, and two in the month card). Assume more.
- The review found more in the code this session shipped than every gate
  combined. `svelte-check`, `ruff`, the import check and the migration round
  trip were all green for every one of these.

## 2026-09-28 — The steps bug, fourth and final: stop inferring authorship

Reported three times, fixed four. Each fix was correct about the cause it found
and wrong that it was the only one. The pattern is the lesson, not the bug.

| # | Cause found | Fix | Why it was not enough |
|---|---|---|---|
| 1 | A `partial_day` guard withheld today's count | Removed it | Yesterday was still missing |
| 2 | The ranged Garmin call silently omits days | Per-day fallback | The number still froze |
| 3 | Every field in a pushed row was marked `manual` | Mark only fields whose value moved | A stale client forges "moved" exactly |
| 4 | Authorship cannot be inferred from data at all | The client states it | — |

**The actual problem, which took four rounds to name:** the server had no way to
know *what the client changed*. Clients push whole rows, two writers own the
same fields, and there is no version to compare against. Attempt 3 tried to
recover the missing information from the values — "unchanged means the client
echoed it back" — which holds only when the client's copy is current. The Daily
Log page caches its row and deliberately does not refresh while you type
(`daily-log/+page.svelte`, and `getDailyLog` does not revalidate), so a tab left
open across an importer's correction sends an old value that *differs* from the
new one. Indistinguishable from typing.

**What changed:** `provenance.claimed_fields`. The client sends `_edited:
["weight"]` naming the fields its user touched; nothing else in the payload can
be claimed, and a field an importer owns that was not claimed is not written at
all. `autoSave(fieldName)` in the Daily Log page already knew which field it was
— it had simply been throwing the information away.

**The fallback direction is deliberate.** With no `_edited` (an older client),
importer-owned fields are left alone rather than claimed. Guessing wrong that way
lets an importer overwrite something hand-typed: visible, and fixable by typing
it again. Guessing wrong the other way freezes a number forever, invisibly, and
no amount of re-syncing shifts it. Between an error you can see and one you
cannot, take the first.

**Watch out**
- `scripts/check_steps_paths.py` now runs all thirteen paths at once. Run it after
  touching `provenance.py`, `garmin.py`, `routers/daily_log.py`, or the DailyLog
  half of `routers/sync.py`. Cases 3 and 4 — a typed number beats the importer, a
  cleared field stays clear — are the ones every fix to this bug risks trading
  away, and three of the four fixes above would have passed a test of only the
  path they changed.
- `_edited` names columns, not form fields. `FIELD_COLUMNS` maps between them; a
  name that matches no column silently means "nothing was edited", which fails
  safe.

## 2026-09-27 — `./db.sh new` was generating a drop-the-whole-schema migration

Found by accident, while adding one nullable column.

**What changed**
- `migrations/env.py` now imports `app.models`. It imported `Base` from
  `app.database` and nothing else, so `Base.metadata` held **zero** tables
  (verified: 0 before the import, 23 after).

**The trap**
Defining a model class is what registers its table on the metadata. With an empty
`target_metadata`, `alembic revision --autogenerate` concludes every table in the
database has been *removed* — and emits exactly that: `op.drop_table` for all 23,
with a `downgrade()` that recreates them. It is ~600 lines of plausible-looking
migration. `CLAUDE.md` documented `./db.sh new` as the normal workflow, and CI
runs `upgrade head && downgrade base` on a **fresh** database, where dropping
everything and putting it back passes cleanly.

Nothing was ever applied, because every migration in this repo happens to have
been hand-written. That is luck, not process.

**Watch out**
- Even fixed, autogenerate is a diff to *read*, not to apply. The models have
  deliberate drift from the database (the Google columns are kept on purpose;
  several indexes are renamed in the models only), so it proposes those too. It
  wanted to drop five `user_settings` Google columns alongside the one column
  being added.
- CI cannot catch this class of bug: a migration that drops everything and
  rebuilds it round-trips on an empty database. Only reading the file catches it.

## 2026-09-26 — One weight entry silently claimed the day's step count

Reported three times as "Garmin isn't importing my steps", and three times I looked at
`garmin.py` and said the fetch was fine. The fetch *was* fine. The write gate was not.

**What changed**
- `sync.py` and `daily_log.py` now mark a field `manual` only when its value actually
  **moved**, via the new `provenance.user_edited`. They used to mark every field present
  in the payload.
- New `scripts/garmin_steps_report.py`: prints Garmin's ranged call, Garmin's per-day
  call, the stored value and its owner side by side, with `--repair` to hand a wrongly
  claimed field back to the importer. `--offline` works without a Garmin session.

**The trap**
Clients push **whole rows, never diffs**. The phone logs a weight and posts the entire
day back — step count included, exactly as its cache received it. Marking everything in
the payload as hand-entered meant a weight entry claimed the steps. `garmin.py` honours a
person's claim by never touching the field again, so:

```
06:00  scheduled sync writes steps=43   (a day barely started — correct, and self-correcting)
08:00  user logs their weight           -> steps:manual, on a number nobody typed
19:00  scheduled sync has steps=4187    -> refused. 43 forever, and re-syncing cannot fix it.
```

The value is the evidence for authorship: unchanged means the client echoed it back.
Clearing a field is still a change (4000 → None), so the deliberate-blank rule survives —
there are three assertions covering exactly that in the repro used to fix this.

**What didn't work**
The repair's first cut *removed* the `steps` entry from `sources`. That leaves the field
with no recorded owner, and `garmin.py` treats unknown ownership as fill-blanks-only — so
a wrong-but-present count stayed exactly as stuck. The repair has to **reassign** the field
to `garmin`, not un-flag it. Caught only because the repair was tested end to end
(repair → sync → assert the number moved) rather than checked for "did it clear the flag".

**Watch out**
- Provenance is written on **three** paths: `daily_log.py` (REST), and two branches of
  `sync.py` (the create-that-upserts, and the update). A rule added to one belongs in all
  three; the bug above lived in the two sync branches while the REST path was half-right.
- Any future importer inherits this. The rule is "did the value move", not "was the key
  present" — see `provenance.user_edited`.
- `--repair` cannot distinguish a count frozen by this bug from one genuinely typed. It is
  dry-run by default and lists every day with its value for that reason.

## 2026-09-25 — Strength logging, stage 5: what Claude can see

**What changed**
- `queries.py` gains `shared()`; `get_activity` emits real sets; new
  `get_exercise_history(exercise, limit)` with top set, volume and an estimated
  1RM per session. Nine tools now. `mcp_db_role.sql` grants the new tables.

**Watch out**
- **`owned()` cannot serve a shared table** — it requires a `user_id` and raises
  without one, which is exactly the property stopping cross-account leaks. The
  catalogue needed `shared()` as a sibling in `queries.py`, *not* a `db.query()`
  in `tools.py`, which CI greps for. `shared()` refuses a model without a `name`
  column as a crude guard against pointing it at personal data.
- **A shared catalogue plus private history is the whole trick here**, and the
  tool has to hold both at once: the *movement* is matched across the shared
  library, every *session* read goes through `owned()`. Verified with two
  accounts training the same lift — the other account's 200kg set does not
  appear in mine.
- Warm-ups are excluded from volume and from the top set. Counting them makes
  the number useless for comparing sessions.
- The 1RM is Epley (`w x (1 + reps/30)`), reasonable to about ten reps and
  optimistic past that. It is labelled in the tool description as a trend line,
  not a number to load a bar with — an LLM will otherwise quote it as fact.
- The DB role needs **relationship targets**, not just tables named in a tool:
  `exercise_sets` is reached through `exercises`, and omitting it fails only at
  runtime, only on a query that touches sets.

## 2026-09-25 — Strength logging, stage 4: routines

**What changed**
- `routine_exercises` hanging off `workout_templates`, a `/api/routines` router,
  a `/routines` page, and a "start from a routine" shortcut in the logger.

**Watch out**
- **Starting a session copies the movements, never the targets.** A routine's
  `target_reps` is what you meant to do. Writing it into the logged set records
  it as what you did, and then "did I hit my target" compares a number with
  itself. Target sets decide how many blank rows appear; nothing else crosses.
- The shortcut only shows while the session is **empty**. Once you have started
  logging, replacing the list wholesale is far likelier to be a misfire than an
  intention.
- Routines are **per account** while the catalogue is shared — the movements are
  communal, the programming is not. Two people training differently out of one
  library is the normal case.
- `workout_templates` was dead code from the initial schema (model, migration
  and a backup-spec row, never a router or a writer), so it became the header
  rather than adding a second table meaning the same thing. Its `exercises_json`
  is left untouched; nothing ever wrote it.
- Backup-spec ordering is load-bearing: `routine_exercises` names both
  `workout_templates` and `exercise_catalog` as parents, so it has to sit after
  **both**. Checked with a parents-before-children sweep over `_BACKUP_SPEC`.

## 2026-09-25 — Strength logging, stage 3: offline

**What changed**
- Sets ride nested inside the activity through the sync protocol, both
  directions. Dexie `version(6)` adds `exerciseCatalog`, in `SYNCED_TABLES` but
  **not** `USER_OWNED_TABLES`, exactly as `foods` is.
- Fixed `sync.py`'s `if exercises_data:` guard, and one writer now serves both
  the create and update push paths.

**Watch out**
- **The changes feed filtered the shared catalogue out of existence.** It scopes
  every table with `hasattr(model, "user_id")` to `user_id == me` — and the
  shared rows have `user_id IS NULL`, so they matched nothing and would never
  have reached any client. `SHARED_CATALOG_MODELS` now matches NULL as well.
  `FoodItem` has the same nullable shape and was silently affected too.
- **Adding a catalogue entry is online-only, deliberately.** Sessions reference
  an entry by server id; an offline-created one has none, so queueing it would
  mean inventing a local id and rewriting every session that pointed at it once
  the server answered. The logger instead falls back to a plain named exercise,
  which loses the video link and nothing else.
- **`if exercises_data:` was the bug**: clearing every exercise offline sends
  `[]`, which is falsy, so the replace never ran and the rows survived — while
  the REST path cleared them. The same edit behaved differently depending on
  whether you had signal.
- A test that pushes a **stale timestamp** is silently ignored by server-wins
  conflict resolution and looks exactly like a broken write. Push with a
  timestamp newer than the row, or you will debug the wrong thing.

## 2026-09-25 — Strength logging, stage 2: the session logger

**What changed**
- `ExerciseLogger.svelte` — exercise cards with a real set table (kg / reps /
  type / RPE), a picker over the shared catalogue with "add it to the list"
  inline, per-exercise session notes, and the video link as an icon.
- Wired into the activity form, shown only when the type is `strength`.

**Watch out**
- **Last session is a placeholder, not a prefill — and tapping accepts it.** A
  prefilled set is a set the app claims you performed; if you close the form
  early, history now contains a lift that never happened. But retyping six
  identical numbers to repeat a workout is what makes people abandon logging. So
  the previous values render as placeholders and `on:focus` fills an *empty*
  field from them. Verified in a driven browser: focusing the inputs produced
  `["80","5","85","5"]` from the prior session, and RPE stayed blank because
  there was no previous RPE.
- **The form deep-copies `activity.exercises` on edit.** The editor mutates sets
  in place, so binding straight to the cached row would edit the activity list
  behind the form — including when the user cancels.
- Adding a set copies the one above it. Within a working block the weight
  usually holds, so "same again" should be the default and the change the
  exception.
- Volume excludes warm-ups. A warm-up set is not the work, and counting it makes
  the number useless for comparing sessions.
- The picker states that the library is shared, because adding to it affects the
  other account and nothing else on that screen would say so.

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
