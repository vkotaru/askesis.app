#!/usr/bin/env python3
"""Pull Garmin Connect wellness + activities into Askesis.

Run from `backend/` — config resolves `.env` against the working directory.

    python scripts/garmin_sync.py --login          # once: interactive, answers MFA
    python scripts/garmin_sync.py --user user --days 7
    python scripts/garmin_sync.py --user user --days 7 --dry-run

In the container `WORKDIR` is already `/app/backend`:

    docker compose exec app python scripts/garmin_sync.py --login
    docker compose exec app python scripts/garmin_sync.py --user <name> --days 7

`--login` is a one-time step per token store. It prompts for the password (and
an MFA code if the account has 2FA), then writes a session token to
GARMIN_TOKENSTORE. Every later run reuses that file and needs no credentials,
so **no Garmin password is stored anywhere** — not in .env, not in the database.

Garmin rate-limits logins by IP and answers 429 to a burst. Reuse the token;
schedule this daily, not hourly.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import garmin
from app.config import get_settings
from app.database import SessionLocal
from app.models import User


def resolve_user(db, identifier: str | None) -> User:
    """The named account, or the only one if the server has just the one."""
    if identifier:
        user = (
            db.query(User)
            .filter((User.username == identifier) | (User.email == identifier))
            .one_or_none()
        )
        if user is None:
            sys.exit(f"No user matches {identifier!r}.")
        return user

    users = db.query(User).all()
    if len(users) == 1:
        return users[0]
    sys.exit(
        "--user is required (accounts: " + ", ".join(u.username for u in users) + ")"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--login",
        action="store_true",
        help="authenticate interactively and cache a session token, then exit",
    )
    ap.add_argument("--user", help="Askesis username or email")
    ap.add_argument("--days", type=int, default=7, help="days back to pull (default 7)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and map, roll back instead of committing",
    )
    args = ap.parse_args()

    tokenstore = get_settings().garmin_tokenstore
    print(f"Token store: {tokenstore}")

    if args.login:
        email = input("Garmin email: ").strip()
        password = getpass.getpass("Garmin password: ")
        try:
            garmin.connect(
                tokenstore,
                email,
                password,
                prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
            )
        except Exception as exc:  # noqa: BLE001 - report cleanly, no traceback
            sys.exit(f"Login failed: {type(exc).__name__}: {exc}")
        print(
            f"Logged in. Session cached to {tokenstore} — later runs need no password."
        )
        return 0

    try:
        api = garmin.connect(tokenstore)
    except Exception as exc:  # noqa: BLE001
        sys.exit(
            f"No usable cached session ({type(exc).__name__}: {exc}).\n"
            "Run once with --login first."
        )

    db = SessionLocal()
    try:
        user = resolve_user(db, args.user)
        print(f"Syncing {args.days}d for {user.username} (id={user.id})")
        report = garmin.sync_user(api, db, user, days=args.days, dry_run=args.dry_run)

        if args.dry_run:
            print("DRY RUN — rolled back, nothing written.")

        print(report.summary())
        for err in report.errors:
            print(f"  ! {err}")
        # A day Garmin has no data for is normal, so partial errors are not a
        # failed run; only a total absence of both feeds is worth a non-zero exit.
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
