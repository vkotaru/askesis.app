#!/usr/bin/env bash
# PreToolUse hook on Bash: before Claude commits app code, ask once whether the
# change earns a JOURNAL.md entry.
#
# The entry is written at commit time, not at session end, because a session
# that crashes never reaches its end. The hook only nudges: it blocks the first
# attempt for a given staged diff, and a repeat of the same commit goes through,
# so a routine change costs one retry and never a filler entry.
#
# Exit 2 blocks the tool call and hands stderr to Claude; exit 0 lets it run.

cmd=$(jq -r '.tool_input.command // empty')

# Only `git commit` (also `git -C dir commit`, `cd x && git commit`).
grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' <<<"$cmd" || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# `commit -a` commits tracked changes that are not staged yet. Look for the flag
# on the commit line only, not in a heredoc message below it.
line=$(grep -m1 -E 'git.*[[:space:]]commit' <<<"$cmd")
if grep -Eq '[[:space:]](--all|-[a-zA-Z]*a[a-zA-Z]*)([[:space:]]|$)' <<<"$line"; then
  files=$(git diff HEAD --name-only)
  diff=$(git diff HEAD)
else
  files=$(git diff --cached --name-only)
  diff=$(git diff --cached)
fi

grep -Eq '^(frontend/src|backend/app)/' <<<"$files" || exit 0
grep -qx 'JOURNAL.md' <<<"$files" && exit 0

marker=$(git rev-parse --git-path journal-check-asked)
hash=$(sha1sum <<<"$diff" | cut -d' ' -f1)
[ -f "$marker" ] && [ "$(cat "$marker")" = "$hash" ] && exit 0
echo "$hash" >"$marker"

cat >&2 <<'MSG'
App code is changing without a JOURNAL.md entry. If this was non-trivial (a
non-obvious fix, an approach dropped and why, a trap found, a decision whose
rationale won't survive in the diff), add an entry at the top of JOURNAL.md and
stage it. If it is routine, run the same commit again; it will go through.
MSG
exit 2
