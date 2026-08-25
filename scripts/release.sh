#!/usr/bin/env bash
# Cut a release.
#
#   ./scripts/release.sh 0.3.0
#
# Checks every guard, runs the CI-equivalent checks, writes VERSION, rolls the
# CHANGELOG's [Unreleased] section into [X.Y.Z], commits, and creates an
# annotated tag vX.Y.Z whose message is that changelog section.
#
# It does NOT push. Pushing a tag is hard to undo, so the exact commands are
# printed for you to run deliberately. See RELEASING.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

step() { echo; echo "==> $*"; }

# Everything up to "Writing VERSION" is read-only, so an abort before that
# leaves nothing behind. After it, say how to undo — a half-written release is
# the one state this script can leave that isn't obvious from `git status`.
ENTRY_FILE=""
FILES_WRITTEN=0
cleanup() {
  status=$?
  [ -n "$ENTRY_FILE" ] && rm -f "$ENTRY_FILE"
  if [ "$status" -ne 0 ] && [ "$FILES_WRITTEN" -eq 1 ]; then
    echo >&2
    echo "Aborted after VERSION / CHANGELOG.md were modified. Undo with:" >&2
    echo "    git checkout -- VERSION CHANGELOG.md" >&2
  fi
  return $status
}
trap cleanup EXIT

NEW_VERSION="${1:-}"
[ -n "$NEW_VERSION" ] || die "usage: ./scripts/release.sh X.Y.Z   (no 'v' prefix — the tag gets it)"

# --- guard: semver ----------------------------------------------------------
if ! printf '%s' "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  die "'$NEW_VERSION' is not a valid version. Expected X.Y.Z with no 'v' prefix."
fi

CUR_VERSION="$(tr -d '[:space:]' <VERSION)"
TAG="v$NEW_VERSION"

# --- guard: strictly increasing --------------------------------------------
# `sort -V` orders versions numerically; equal versions collapse to one line,
# which is why the equality case is checked separately.
if [ "$NEW_VERSION" = "$CUR_VERSION" ]; then
  die "VERSION is already $CUR_VERSION — nothing to release."
fi
highest="$(printf '%s\n%s\n' "$CUR_VERSION" "$NEW_VERSION" | sort -V | tail -n 1)"
if [ "$highest" != "$NEW_VERSION" ]; then
  die "$NEW_VERSION is not greater than the current VERSION ($CUR_VERSION)."
fi

# --- guard: on main, clean, in sync with origin -----------------------------
BRANCH="$(git symbolic-ref --short -q HEAD || echo '(detached)')"
[ "$BRANCH" = "main" ] || die "releases are cut from main; you are on '$BRANCH'."

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree is dirty:" >&2
  git status --short >&2
  exit 1
fi

step "Fetching origin"
git fetch --quiet origin --tags --prune

git rev-parse -q --verify origin/main >/dev/null || die "origin/main not found."
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
if [ "$LOCAL" != "$REMOTE" ]; then
  ahead="$(git rev-list --count origin/main..HEAD)"
  behind="$(git rev-list --count HEAD..origin/main)"
  die "main is not in sync with origin/main (ahead $ahead, behind $behind). Push or pull first."
fi

# --- guard: tag does not exist ----------------------------------------------
# Origin first: the fetch above copies origin's tags into the local repo, so a
# tag that only ever existed on origin would otherwise be reported as "local"
# and hide where it actually came from.
if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  die "tag $TAG already exists on origin. Releases are immutable — cut the next version."
fi
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "tag $TAG already exists locally (not on origin). Delete it or pick another version."
fi

# --- guard: CHANGELOG has unreleased content --------------------------------
[ -f CHANGELOG.md ] || die "CHANGELOG.md not found."
grep -qE '^## \[Unreleased\]' CHANGELOG.md || die "CHANGELOG.md has no '## [Unreleased]' section."

# Everything between the [Unreleased] heading and the next '## ' heading.
UNRELEASED="$(
  awk '
    /^## \[Unreleased\]/ { inside = 1; next }
    inside && /^## / { exit }
    inside { print }
  ' CHANGELOG.md
)"
# Strip blank lines to decide emptiness; keep the original for the entry body.
if [ -z "$(printf '%s' "$UNRELEASED" | tr -d '[:space:]')" ]; then
  die "CHANGELOG.md '## [Unreleased]' is empty — write the release notes first."
fi

# ---------------------------------------------------------------------------
# CI-equivalent checks. Cheaper to fail here than to fail on a pushed tag.
# ---------------------------------------------------------------------------
if [ -x backend/venv/bin/python ]; then
  PY="$ROOT/backend/venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
[ -n "$PY" ] || die "no python found (expected backend/venv or python3 on PATH)."

step "Backend: ruff"
(cd backend && ruff check . && ruff format --check .)

step "Backend: import smoke test"
(cd backend && DEV_MODE=true SECRET_KEY=release-check-not-a-real-secret \
  DATABASE_URL="sqlite:///./release-check.db" "$PY" -c "import app.main")
rm -f backend/release-check.db

step "Frontend: check + build"
# Via npm.sh, not npm: it execs the real npm when one is installed and
# otherwise runs the same commands in the docker-compose.dev.yml toolchain, so
# a release can be cut from a machine that has Docker but no Node.
(cd frontend && ./npm.sh run check && ./npm.sh run build)

# ---------------------------------------------------------------------------
# The Alembic head this release ships with. Recorded in the changelog so a
# rollback is legible: deploy.sh runs `alembic upgrade head` unconditionally,
# so going back a tag needs `alembic downgrade <that head>` to go back a schema.
# ---------------------------------------------------------------------------
step "Resolving Alembic head"
ALEMBIC_HEAD="$(
  cd backend && DEV_MODE=true SECRET_KEY=release-check-not-a-real-secret \
    DATABASE_URL="sqlite:///./release-check.db" "$PY" -m alembic heads 2>/dev/null |
    tail -n 1 | awk '{print $1}' || true
)"
rm -f backend/release-check.db
[ -n "$ALEMBIC_HEAD" ] || die "could not determine the Alembic head."
echo "    $ALEMBIC_HEAD"

# ---------------------------------------------------------------------------
# Write VERSION + roll the changelog.
# ---------------------------------------------------------------------------
TODAY="$(date +%Y-%m-%d)"

step "Writing VERSION ($CUR_VERSION -> $NEW_VERSION)"
FILES_WRITTEN=1
printf '%s\n' "$NEW_VERSION" >VERSION

step "Rolling CHANGELOG.md [Unreleased] -> [$NEW_VERSION]"
ENTRY_FILE="$(mktemp)"
{
  printf '## [%s] - %s\n\n' "$NEW_VERSION" "$TODAY"
  printf 'Alembic head: `%s`\n' "$ALEMBIC_HEAD"
  printf '%s\n' "$UNRELEASED"
} >"$ENTRY_FILE"

# The compare links at the bottom. PREV is whatever the [Unreleased] line
# currently compares against — i.e. the previous release — so this keeps
# working across the handover from the historical suffixed tags.
REPO_URL="https://github.com/vkotaru/askesis.app"
PREV_TAG="$(sed -n 's#^\[Unreleased\]:.*/compare/\(.*\)\.\.\.HEAD$#\1#p' CHANGELOG.md | head -n 1)"

NEW_CHANGELOG="$(mktemp)"
awk -v entry="$ENTRY_FILE" -v tag="$TAG" -v ver="$NEW_VERSION" \
    -v prev="$PREV_TAG" -v repo="$REPO_URL" '
  # Replace the [Unreleased] section with an empty one followed by the entry.
  /^## \[Unreleased\]/ && !rolled {
    print "## [Unreleased]"
    print ""
    while ((getline line < entry) > 0) print line
    close(entry)
    print ""          # keep a blank line before the next section heading
    rolled = 1
    skipping = 1
    next
  }
  skipping && /^## / { skipping = 0 }
  skipping { next }

  # Re-point the compare footer and add one for this release.
  /^\[Unreleased\]:/ && prev != "" {
    printf "[Unreleased]: %s/compare/%s...HEAD\n", repo, tag
    printf "[%s]: %s/compare/%s...%s\n", ver, repo, prev, tag
    next
  }
  { print }
' CHANGELOG.md >"$NEW_CHANGELOG"
mv "$NEW_CHANGELOG" CHANGELOG.md

step "Committing"
git add VERSION CHANGELOG.md
git commit -m "Release $TAG" -m "Alembic head: $ALEMBIC_HEAD"
FILES_WRITTEN=0   # committed; `git checkout --` is no longer the undo

step "Tagging $TAG"
{
  printf '%s\n\n' "$TAG"
  cat "$ENTRY_FILE"
  # --cleanup=verbatim is load-bearing: git tag's default cleanup mode is
  # "strip", which discards every line starting with '#'. That is every
  # markdown heading in the changelog entry — "## [0.3.0]", "### Added" — so
  # without this the tag message is a headless pile of bullets.
} | git tag -a "$TAG" --cleanup=verbatim -F -

cat <<EOF

Release $TAG is committed and tagged LOCALLY. Nothing has been pushed.

Review it:
    git show $TAG
    git show HEAD

Then push — deliberately, in this order:
    git push origin main
    git push origin $TAG

Then deploy (on the server):
    ./deploy.sh

EOF
