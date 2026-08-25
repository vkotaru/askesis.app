# Self-hosting Askesis on your home server (Tailscale)

This runs the web app/API in Docker on your own box, reachable over your
tailnet. Nothing about it phones home: no OAuth provider, no cloud storage.

Files: `Dockerfile`, `docker-compose.yml`, `deploy.sh`, `.env.example`,
`tailscale/serve.json`.

Release and rollback mechanics live in **`RELEASING.md`** — read it before you
roll back, because the database does not roll back with the container.

## What runs
Three containers:
- **app** — builds the SvelteKit SPA and serves it **same-origin** with the
  FastAPI API (no API hostname baked into the frontend).
- **db** — bundled `postgres:16`.
- **tailscale** — a Tailscale **sidecar** that joins your tailnet as its own
  host (`askesis.<tailnet>.ts.net`), terminates HTTPS via Tailscale Serve, and
  proxies to the app. The app shares this container's network namespace, so it's
  reachable **only on the tailnet** (no host ports exposed).

Giving Askesis its **own hostname** (not just a different port on a shared host)
matters: Android associates an installed PWA with its *host*, so two PWAs on the
same host but different ports collide — a distinct hostname installs cleanly.

Progress/meal photos live on **the server's own disk** (see *Photo storage*).
Personal data backups download straight to whatever device you clicked from
(Settings → Backup & Restore); nothing is uploaded anywhere. That in-app backup
is **per-user**: it contains the signed-in account's own rows only, and never
`users`, `report_tokens` or `data_shares`. A **whole-database** snapshot is an
operator job, not something an account can pull over HTTP — take it on the box:

```bash
mkdir -p ~/.askesis/backups
docker compose exec -T db pg_dump -U askesis askesis \
  > ~/.askesis/backups/db-$(date +%F-%H%M).sql
```

**Write dumps to `~/.askesis/backups/`, never into the checkout.** A bare
redirect lands the file in whatever directory you ran the command from, which is
this git repo — and a dump holds every health record plus the `users` row with
its bcrypt hash. `.gitignore` covers `*.sql` so it can't be committed by
accident, but keeping backups outside `/srv/apps/askesis.app` entirely is the
real protection: they then survive `rm -rf` on the checkout, a re-clone, or a
`deploy.sh` gone wrong, none of which should be able to take the backups with
them.

Same disk, though — this protects you from a bad migration, not from the drive
failing. Getting a copy **off the box** (restic/Borg to an external drive or a
cloud bucket) is still an open task, and it needs to cover both halves: these
dumps *and* `./data/uploads`.

That split is deliberate: the app has no admin role, so a logged-in household
member must not be able to download another member's health data — or their
bcrypt password hash — through a "backup" button.

## First-time setup (on the server)

1. **Clone + configure**
   ```bash
   git clone <repo> askesis && cd askesis
   cp .env.example .env
   $EDITOR .env            # secrets + TS_AUTHKEY (see notes below)
   ```
   Generate a Tailscale **auth key**: Admin console → Settings → Keys →
   Generate auth key (reusable recommended) → put it in `.env` as `TS_AUTHKEY`.

2. **Deploy**
   ```bash
   ./deploy.sh             # latest vX.Y.Z tag: fetch, checkout, down, up --build
   ```
   `deploy.sh` deploys the **latest release tag**, not the tip of `main` —
   unreleased work never reaches the box by accident. It leaves the checkout on a
   detached HEAD, which is correct; don't `git pull` here.
   The sidecar joins the tailnet as **`askesis`** and serves HTTPS. Open:
   **`https://askesis.<your-tailnet>.ts.net`**
   (First run, confirm it came up: `docker compose logs tailscale` — look for it
   authenticating and obtaining a cert. If a device named `askesis` already
   exists in your tailnet it'll be renamed `askesis-1`; rename in the admin
   console or change `hostname:` in `docker-compose.yml`.)

3. **Create your account.** There is no sign-up page and no OAuth; accounts are
   made on the box:
   ```bash
   docker compose exec app python scripts/manage_users.py \
       create --username you --email you@example.com --name "Your Name"
   ```
   It prompts for the password twice and never takes it as a flag (shell history).
   `set-password --username you` resets one later; `list` shows every account.

Updating later is just `./deploy.sh` again — it picks up whatever the newest
`vX.Y.Z` tag is. To pin, roll back, or deploy unreleased work:

```bash
./deploy.sh v0.2.0      # a specific release (rollback / pin)
./deploy.sh main        # tip of main, deliberately
```

Check what actually landed:

```bash
curl -s https://askesis.<your-tailnet>.ts.net/api/version
# {"version":"0.2.0","commit":"<sha>","ref":"v0.2.0"}
```

The same information is under the logo in the sidebar. A bare `v0.2.0` means a
clean release; `v0.2.0 (main@e4230a8)` means it isn't one. See `RELEASING.md`.

> Migrating from a port-based setup? Remove the old manual mapping first:
> `sudo tailscale serve --https=8443 off` (on the host), then deploy — the
> sidecar owns serving now.

## Accounts that predate password sign-in

Askesis used Google sign-in before v0.2.0. Those user rows survive with all their
data, but their `password_hash` is NULL — there is no password to type, so they
cannot log in at all. `manage_users.py list` shows them as **`CLAIMABLE`**.

Such an account can be claimed from the login screen. Type its username or email
with any password; the server answers `409 password_not_set` and the form turns
into "set your password". Whatever is entered there becomes the account's
password and signs that browser in immediately.

> **This is unauthenticated.** An account with no password belongs to whoever
> reaches the login screen first — there is no email round-trip, no invite code,
> nothing to prove ownership. It is only tolerable because the app is reachable
> solely from your tailnet. **Claim every account in the first session after the
> first deploy**, or set their passwords on the box yourself:
>
> ```bash
> docker compose exec app python scripts/manage_users.py list
> docker compose exec app python scripts/manage_users.py set-password --email old@example.com
> ```

The path closes permanently for an account the moment it has a password: from
then on `POST /auth/set-initial-password` refuses it, and the only way to change
the password is `/auth/change-password`, which requires the current one. It is a
claim, never a reset — a forgotten password is still a `set-password` on the box.

Every successful claim is logged: `docker compose logs app | grep "Initial password claimed"`.

## Photo storage

Photos are written to `./data/uploads` on the host, bind-mounted into the
container at `/app/backend/uploads`:

```
data/uploads/
  photos/     progress photos   (askesis_{user}_{date}_{view}_{hex}.jpg)
  meals/      meal photos       (meal_{user}_{meal_id}_{hex}.jpg)
  _inbox/     ← drop files here for adoption; not served
```

The database stores the **relative** path (`photos/<name>`), never an absolute
one, so moving the mount point doesn't invalidate every row. `data/` is
gitignored and excluded from the Docker build context.

A **bind mount, not a named volume**, on purpose: you need to be able to copy a
photo export into `_inbox/` with ordinary host tools, and `docker cp`
into an anonymous volume path is needlessly awkward.

### One-time: copy the old named volume across

Earlier builds mounted a named volume here. If it has anything in it, move it
before the first deploy on the new compose file — switching the mount does
**not** migrate the contents, and the named volume simply stops being attached.

**Find the real name first.** Compose prefixes the volume with the project name,
which it derives from the directory (`askesis.app` → `askesisapp`), so the
volume is typically `askesisapp_uploads` — not `askesis_uploads`. Getting this
wrong is silent, not loud: `docker run -v <name>:/from` **creates an empty
volume** when the name doesn't exist, so a typo copies nothing and looks like
"there was nothing to migrate".

```bash
docker volume ls | grep -E '_uploads$'          # confirm the exact name
VOL=askesisapp_uploads                          # ...and set it here

mkdir -p data/uploads
docker volume inspect "$VOL" >/dev/null         # fails loudly if the name is wrong
docker run --rm \
  -v "$VOL":/from \
  -v "$PWD/data/uploads":/to \
  alpine sh -c 'cp -a /from/. /to/ && ls -la /to'
```

No `2>/dev/null || true` on the copy on purpose — a failure here must stop you,
not scroll past. Once you have confirmed the files landed in `data/uploads`:
`docker volume rm "$VOL"`.

## Garmin Connect sync

Optional. There is no official personal Garmin API, so this uses the unofficial
`garminconnect` client — expect it to need version bumps when Garmin changes
its auth flow (it did in March 2026, which deprecated the library everything
previously depended on).

**One-time login.** Garmin rate-limits logins by IP and answers `429` to a
burst, so the session is cached and reused rather than re-established per run:

```bash
docker compose exec app python scripts/garmin_sync.py --login
```

That prompts for your Garmin email, password, and an MFA code if the account
has 2FA. It writes a token to the `garmin-tokens` volume (`GARMIN_TOKENSTORE`,
default `/app/backend/.garminconnect`) and **nothing else stores the password** —
not `.env`, not the database. Losing that volume costs another login, so leave
it out of `docker compose down -v` territory like the others.

**Then sync** — safe to re-run, and meant to be:

```bash
docker compose exec app python scripts/garmin_sync.py --days 7 --dry-run
docker compose exec app python scripts/garmin_sync.py --days 7
```

Daily is the right cadence; hourly will get you rate limited. Overlapping
windows are deliberate — they pick up a device that uploaded late.

**Then stop doing it by hand.** Set `GARMIN_SYNC_ENABLED=true` and the app runs
the pull itself, daily, in-process:

```bash
GARMIN_SYNC_ENABLED=true
GARMIN_SYNC_TZ=Area/City         # your IANA zone; see below. Do not leave this at UTC.
GARMIN_SYNC_HOUR=3               # hour in GARMIN_SYNC_TZ
GARMIN_SYNC_DAYS=3
GARMIN_SYNC_USER=                # only needed once a second account exists
```

**Set `GARMIN_SYNC_TZ` to where you actually live.** It drives two things: the
hour the job fires, and — more importantly — which calendar day counts as
"today". The image runs UTC, so leaving this unset means both are UTC, and for
anywhere west of Greenwich the "nightly" pull fires in the *evening*, on a day
that has not finished. Garmin's own `calendarDate` is your device's local day,
so the two disagree and the pull reaches for a day that has barely started.

With the zone set, `GARMIN_SYNC_HOUR=3` means 03:17 local wherever you are:
after midnight, before you wake up, with the previous day fully closed.

**You will not have to log in again.** Each run refreshes the session token and
writes it back to the volume, so the login survives indefinitely as long as the
schedule runs and the volume lives. A re-login is needed only if you change your
Garmin password, Garmin revokes the token, or the box sits idle long enough for
the refresh token itself to lapse.

If you want even that recovery to happen without a shell, set `GARMIN_EMAIL` and
`GARMIN_PASSWORD`. They are consulted **only** when the cached token is missing
or rejected — never for a normal sync. The trade is a plaintext password on the
box, readable via `docker inspect`; and it does nothing for an account with 2FA,
which still needs an interactive code. Leaving them unset is the safer default.

What lands where: `totalSteps` → `DailyLog.steps`, `sleepTimeSeconds` →
`DailyLog.sleep_hours`, `valueInML` → `DailyLog.water_ml`, and each activity →
one `Activity` keyed by its Garmin `activityId`. **A value you entered is never
overwritten** — and since per-field provenance landed, that covers a field you
deliberately *cleared* too: a blank you made by hand is left blank rather than
refilled. What Garmin may now update is its own earlier readings, which is what
lets a bad or partial number correct itself on the next pass.
Weight is not imported: it only exists in Garmin if a connected scale or a
linked nutrition app is feeding it.

Steps and hydration are **not** written for a day still in progress — they are
running totals, and because a log only ever fills a blank, a midday figure would
be frozen there for good. They land once the day closes, which the overlapping
window takes care of.

**Watching it from the app.** Settings → Garmin Connect shows whether the
schedule is on, when it last ran, what it filled, and any errors, plus a **Sync
now** button. Values it filled carry a small watch icon in the daily log. The
panel diagnoses a dead session and prints the `--login` command, but it never
asks for your Garmin password — connecting is still the shell step above. Run
state lives in memory, so a container restart resets it to "not since the server
started".

### Adopting a photo dump

If you have an export of photos from an earlier hosting setup, copy the tree into
`data/uploads/_inbox/` — nested subdirectories are fine, the walk is recursive.
Then match the files to database rows by filename:

```bash
docker compose exec app python scripts/adopt_photos.py             # dry run
docker compose exec app python scripts/adopt_photos.py --apply
docker compose exec app python scripts/adopt_photos.py --verify
```

**Dry run is the default** — there is no `--dry-run`, only `--apply`. The dry
run prints a per-file table (`ADOPT`, `SKIP-ALREADY`, `CONFLICT-DEST`,
`CONFLICT-ROWS`, `ORPHAN`, `UNPARSEABLE`) and exits non-zero if anything
conflicted. `--apply` **copies** and leaves `_inbox/` intact; a later
`--apply --prune-inbox` deletes each source only after re-reading its copy and
matching the sha256. Re-running is a no-op — everything already adopted comes
back as `SKIP-ALREADY`.

Files that parse but match no row land in `_inbox/_orphans/`; files whose names
match no known pattern land in `_inbox/_unparseable/`. Neither is deleted.
`--create-missing` will synthesize a *progress photo* row (its filename carries
user, date and view — the whole row); it will never synthesize a *meal* row,
because a meal needs a date and a label that the filename doesn't carry.

## Gotchas / migration notes

- **Importing an existing Postgres database:**
  ```bash
  # on a machine with the old DATABASE_URL:
  pg_dump "$OLD_DATABASE_URL" > askesis.sql
  # on the server, after the stack is up:
  docker compose exec -T db psql -U askesis askesis < askesis.sql
  ```
  Skip this for a fresh start (Alembic creates the schema on first boot).
- **Rows carried over from an older install keep their Google columns**
  (`google_refresh_token`, `picture`, the Drive/Sheets settings columns,
  `drive_file_id`). No code reads them — SQLAlchemy ignores unmapped columns —
  and a later migration drops them. They are kept for now because
  `drive_file_id` is the only remaining mapping from a row to a file in an
  un-exported Drive folder.
- **`SECRET_KEY`** must not stay the placeholder — the app refuses to start in
  production mode otherwise.
- **Always use the `https://askesis.<tailnet>.ts.net` URL.** The sidecar serves
  HTTPS with a real cert, and the `DEV_MODE=false` session cookie is
  HTTPS-only, so plain HTTP silently fails to keep you logged in. There are no
  plain-HTTP host ports anymore.
- **`TS_ACCEPT_DNS=false`** is set on the sidecar on purpose — it stops Tailscale
  from overriding the container's DNS, so the app can still resolve the `db`
  service. Don't remove it.
- **CORS_ORIGINS** only matters for cross-origin clients; the PWA is served
  same-origin with the API. Put your `ts.net` host there anyway.
- **Rolling back the container does not roll back the database.** The container
  runs `alembic upgrade head` on every start, so an older image ends up talking
  to a newer schema. Usually harmless (migrations are additive); when it isn't,
  `alembic downgrade` to the head recorded in that release's `CHANGELOG.md`
  entry, and take a `pg_dump` before every deploy. Full detail in `RELEASING.md`.
- **`deploy.sh` runs `docker compose down`, which is safe** — it stops and
  removes containers, and leaves both volumes (`pgdata`, `tailscale-state`) and
  the `./data/uploads` bind mount untouched. **Never run `docker compose
  down -v`**: `-v` destroys the named volumes, which means your Postgres data
  and the Tailscale node identity. Photos survive `-v` now that they're a bind
  mount, but the database that points at them would not.
- **Back up `data/uploads` along with the database.** They are two halves of one
  backup: a Postgres dump whose `file_path` rows point at files you no longer
  have restores to broken images. `scripts/adopt_photos.py --verify` reports
  exactly that mismatch in both directions.
