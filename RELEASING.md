# Releasing and deploying Askesis

One box, one container, one operator. This is the whole process.

`VERSION` at the repo root is the single source of truth for the version number. The
backend reads it (`GET /api/version`, the OpenAPI version) and Vite inlines it into the
SPA at build time. Release tags are plain `vX.Y.Z`.

> The two historical tags `v0.1.0-pre-simplify` and `v0.2.0-simplified` are meaningful
> checkpoints, not releases. Nothing resolves them as deploy targets; leave them alone.

## Cutting a release

From a clean `main` that is in sync with origin:

1. Write the release notes under `## [Unreleased]` in `CHANGELOG.md` as you go — the
   release script refuses to run with an empty section.
2. Cut it:

   ```bash
   ./scripts/release.sh 0.3.0        # no 'v' — the tag gets it
   ```

   This checks every guard (valid semver, strictly greater than the current `VERSION`,
   on `main`, clean tree, in sync with `origin/main`, tag unused locally and on origin,
   `[Unreleased]` non-empty), then runs the CI-equivalent checks — `ruff check`,
   `ruff format --check`, the `import app.main` smoke test, `npm run check`,
   `npm run build`. Only then does it write `VERSION`, roll `[Unreleased]` into
   `## [0.3.0] - <date>` with the Alembic head recorded, commit both files, and create
   an annotated `v0.3.0` tag whose message is that changelog section.

3. It does **not** push. Review, then push deliberately:

   ```bash
   git show v0.3.0
   git push origin main
   git push origin v0.3.0
   ```

CI then re-runs everything on the tag and fails if `VERSION` does not match it. It also
fails any PR or push that changes `VERSION` without changing `CHANGELOG.md`.

## Deploying

On the server, in the checkout:

```bash
./deploy.sh            # the latest vX.Y.Z tag — the normal case
./deploy.sh v0.2.0     # a specific release  (rollback / pin)
./deploy.sh main       # tip of main, deliberately — NOT a release
```

`deploy.sh` refuses to run against a dirty working tree, fetches explicitly
(`git fetch --all --tags --prune`), checks the target out with
`git checkout --detach`, prints the target ref and commit next to what is currently
deployed, then `docker compose down && docker compose up -d --build`.

The checkout ends up on a detached HEAD, which is correct and expected — a tag is not a
branch. Do not `git pull` on the server; `deploy.sh` does the fetching.

Confirm what landed:

```bash
curl -s https://askesis.<your-tailnet>.ts.net/api/version
# {"version":"0.3.0","commit":"<sha>","ref":"v0.3.0"}
```

## What the version in the UI means

The label under the sidebar logo is fetched from `/api/version` at runtime (not baked
into the JS bundle — the SPA is built in an earlier Docker stage, so baking a SHA would
mean rebuilding the whole frontend to change a label).

| Label | Meaning |
| --- | --- |
| `v0.3.0` | A clean release: the deployed ref is exactly `v<VERSION>` and the loaded bundle agrees. |
| `v0.3.0 (main@e4230a8)` | Deployed from `main`, or from a ref that is not this version's tag. Unreleased work. |
| `v0.3.0 (e4230a8)` | The ref is unknown but the commit is known. |
| `v0.3.0 (unknown)` | Neither was baked in — a hand-built image, or a local dev server. |
| `v0.3.0` while offline | `/api/version` was unreachable, so this is the build-time version from the bundle. |

Anything with a suffix is not a release. That is the point.

## Rolling back

```bash
./deploy.sh v0.2.0
```

### The caveat: the database does not roll back with the container

`deploy.sh` starts the container with `alembic upgrade head` (see the `Dockerfile`
`CMD`), unconditionally, on every deploy. Rolling the **container** back to an older tag
therefore leaves the **database** on the newer schema, and the old code runs against it.

- **Usually this is fine.** Migrations here are additive — new tables and new nullable
  columns. Old code simply does not select the columns it does not know about.
- **When it is not fine** (a migration renamed or dropped something, or added a NOT NULL
  column the old code does not populate), you must roll the schema back too. Every
  released `CHANGELOG.md` entry records the Alembic head it shipped with, which is
  exactly the revision to go back to:

  ```bash
  docker compose exec app python -m alembic downgrade <head-from-that-release>
  ```

  Do this **before** deploying the old tag, while the newer code and its migration
  scripts are still in the container. Then `./deploy.sh vX.Y.Z`.

- **The real safety net is a dump taken before you deploy.** Take one every time:

  ```bash
  mkdir -p ~/.askesis/backups
  docker compose exec -T db pg_dump -U askesis askesis \
    > ~/.askesis/backups/db-$(date +%F-%H%M).sql
  ```

  Dumps go to `~/.askesis/backups/`, **not** into the checkout — see
  `SELF_HOSTING.md`. Photos live on the host at `./data/uploads` and are not in that dump. A database whose
  `file_path` rows point at files you no longer have restores to broken images, so back
  up both halves together (see `SELF_HOSTING.md`).

CI proves every migration is reversible on every push — it runs `alembic upgrade head`
followed by `alembic downgrade base` — so a downgrade path always exists. It does not
prove the *data* survives the round trip; a dump is still the safety net.

## When something in the release is wrong

Do not delete and re-push a tag. Cut a new patch release
(`./scripts/release.sh 0.3.1`) and deploy that. A tag someone may have already deployed
must keep meaning what it meant.
