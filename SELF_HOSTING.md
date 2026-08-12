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
Database backups download straight to whatever device you clicked from
(Settings → Backup & Restore); nothing is uploaded anywhere.

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
   docker compose exec app python backend/scripts/manage_users.py \
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

Earlier builds mounted a named volume called `askesis_uploads` here. If it has
anything in it, move it before the first deploy on the new compose file —
switching the mount does **not** migrate the contents, and the named volume
simply stops being attached:

```bash
mkdir -p data/uploads
docker run --rm \
  -v askesis_uploads:/from \
  -v "$PWD/data/uploads":/to \
  alpine sh -c 'cp -a /from/. /to/ 2>/dev/null || true; ls -la /to'
# once you've confirmed the copy:  docker volume rm askesis_uploads
```

(`docker volume ls` to confirm the exact name — Compose prefixes it with the
project directory name.)

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
