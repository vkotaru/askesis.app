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

Progress/meal photos and DB backups live in **Google Drive** (unchanged).

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
- **CORS_ORIGINS** only matters for the Capacitor apps / cross-origin clients;
  the web app is same-origin. Put your `ts.net` host there anyway.
- Native Kotlin Android app is **not** affected — it talks to Google
  Sheets/Drive directly and never touches this server.
