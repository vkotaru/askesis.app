# Self-hosting Askesis on your home server (Tailscale)

This runs the same web app/API that's on Railway, in Docker, on your own box,
reachable over your tailnet. Railway is left untouched — this is independent.

Files: `Dockerfile`, `docker-compose.yml`, `deploy.sh`, `.env.example`,
`tailscale/serve.json`.

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
DB backups still go to Google Drive.

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
   ./deploy.sh             # git pull, docker compose down, up --build
   ```
   The sidecar joins the tailnet as **`askesis`** and serves HTTPS. Open:
   **`https://askesis.<your-tailnet>.ts.net`**
   (First run, confirm it came up: `docker compose logs tailscale` — look for it
   authenticating and obtaining a cert. If a device named `askesis` already
   exists in your tailnet it'll be renamed `askesis-1`; rename in the admin
   console or change `hostname:` in `docker-compose.yml`.)

3. **Google OAuth**: in the Google Cloud console, add the authorized redirect URI:
   `https://askesis.<your-tailnet>.ts.net/auth/callback`
   (the existing `app.askesis.app://auth/callback` for the mobile app stays.)
   HTTPS + `--proxy-headers` mean the secure cookies and OAuth redirect work.

Updating later is just `./deploy.sh` again.

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
Google Drive export into `_inbox/` with ordinary host tools, and `docker cp`
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

### Adopting a Google Drive photo dump

Download the Askesis folder from Drive, unzip it, and copy the tree into
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

- **`ENCRYPTION_KEY`** — Google refresh tokens are encrypted with it. To move
  data from Railway, set the *same* `ENCRYPTION_KEY` here, or everyone has to
  re-link Google (Drive photos won't load until they do). Fresh install: just
  generate one.
- **Moving your data** from Railway Postgres:
  ```bash
  # on a machine with the Railway DATABASE_URL:
  pg_dump "$RAILWAY_DATABASE_URL" > askesis.sql
  # on the server, after the stack is up:
  docker compose exec -T db psql -U askesis askesis < askesis.sql
  ```
  Skip this for a fresh start (Alembic creates the schema on first boot).
- **`SECRET_KEY`** must not stay the placeholder — the app refuses to start in
  production mode otherwise.
- **Always use the `https://askesis.<tailnet>.ts.net` URL.** The sidecar serves
  HTTPS with a real cert; Google OAuth and the `DEV_MODE=false` HTTPS-only
  cookies require it. There are no plain-HTTP host ports anymore.
- **`TS_ACCEPT_DNS=false`** is set on the sidecar on purpose — it stops Tailscale
  from overriding the container's DNS, so the app can still resolve the `db`
  service. Don't remove it.
- **CORS_ORIGINS** only matters for cross-origin clients; the PWA is served
  same-origin with the API. Put your `ts.net` host there anyway.
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
