# Self-hosting Askesis on your home server (Tailscale)

This runs the same web app/API that's on Railway, in Docker, on your own box,
reachable over your tailnet. Railway is left untouched — this is independent.

Files: `Dockerfile`, `docker-compose.yml`, `deploy.sh`, `.env.example`.

## What runs
One container builds the SvelteKit SPA and serves it **same-origin** with the
FastAPI API (so no API hostname is baked into the frontend). A bundled
`postgres:16` container holds the data. Progress/meal photos and DB backups
live in **Google Drive** (unchanged), so there's no photo data to migrate.

## First-time setup (on the server)

1. **Clone + configure**
   ```bash
   git clone <repo> askesis && cd askesis
   cp .env.example .env
   $EDITOR .env            # secrets + your ts.net hostname (see notes below)
   ```

2. **Deploy**
   ```bash
   ./deploy.sh             # git pull, docker compose down, up --build
   ```
   App is published on the Tailscale IP: `http://<bind_addr>:<port>`
   (container listens on 8000; compose maps `<bind_addr>:<port> -> 8000`).

3. **HTTPS — required for Google login.** Google rejects non-localhost `http`
   OAuth redirect URIs, and the app's session cookies are HTTPS-only when
   `DEV_MODE=false`. So put TLS in front via Tailscale Serve (gives a real cert
   on your `*.ts.net` name); uvicorn honors its `X-Forwarded-Proto` via
   `--proxy-headers`:
   ```bash
   tailscale serve --bg --https <port> http://<bind_addr>:<port>
   # -> https://<this-machine>.<your-tailnet>.ts.net:<port>
   ```
   Then use that `https://…ts.net:<port>` URL to access the app and to log in.
   (Plain `http://<bind_addr>:<port>` works for poking at it, but Google login
   won't — see Gotchas.)

4. **Google OAuth**: in the Google Cloud console, add an authorized redirect
   URI matching the HTTPS URL above:
   `https://<this-machine>.<your-tailnet>.ts.net:<port>/auth/callback`
   (the existing `app.askesis.app://auth/callback` for the mobile app stays.)

Updating later is just `./deploy.sh` again.

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
- **Plain `http://<bind_addr>:<port>` and Google login don't mix.** Google
  only allows `http` redirect URIs for localhost, and `DEV_MODE=false` makes
  cookies HTTPS-only. Use the Tailscale Serve HTTPS URL for anything involving
  login. (Only set `DEV_MODE=true` for throwaway local http testing — login
  still won't get a valid Google redirect that way.)
- **CORS_ORIGINS** only matters for the Capacitor apps / cross-origin clients;
  the web app is same-origin. Put your `ts.net` host there anyway.
- Native Kotlin Android app is **not** affected — it talks to Google
  Sheets/Drive directly and never touches this server.
