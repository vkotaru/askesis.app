#!/usr/bin/env python3
"""Manage Askesis user accounts from the command line.

Usage:
    python scripts/manage_users.py list
    python scripts/manage_users.py create --username alice --email alice@example.com --name "Alice"
    python scripts/manage_users.py set-password --username alice
    python scripts/manage_users.py set-password --email alice@example.com

This is the *only* way to create accounts or set passwords. There is
deliberately no env-var seeding and no "auto-create an admin if the users table
is empty" startup path: an env password ends up in .env and `docker inspect`,
and auto-bootstrap is an unauthenticated account-creation hole.

`set-password` prompts twice via getpass and never accepts the password as an
argv flag, which would land it in shell history and in `ps` output.
"""

import argparse
import getpass
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import User, derive_username
from app.security import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, hash_password


def _find_user(db, username: str | None, email: str | None) -> User | None:
    query = db.query(User)
    if username and email:
        return query.filter(or_(User.username == username, User.email == email)).first()
    if username:
        return query.filter(User.username == username).first()
    return query.filter(User.email == email).first()


def _prompt_password() -> str:
    """Prompt twice for a password and validate it. Returns the plaintext."""
    while True:
        first = getpass.getpass("New password: ")
        second = getpass.getpass("Confirm password: ")

        if first != second:
            print("Passwords do not match. Try again.", file=sys.stderr)
            continue

        if len(first) < MIN_PASSWORD_LENGTH:
            print(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                file=sys.stderr,
            )
            continue

        encoded = len(first.encode("utf-8"))
        if encoded > MAX_PASSWORD_BYTES:
            # bcrypt truncates at 72 bytes; reject rather than silently accept
            # a password that would authenticate on its prefix.
            print(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
                f"(this one is {encoded}; non-ASCII characters cost more than one byte).",
                file=sys.stderr,
            )
            continue

        return first


def _warn_claimable(users: list[User]) -> None:
    """Warn about accounts with no password.

    An account whose ``password_hash`` is NULL can be claimed by *anyone* who
    can reach the app: the login screen offers `POST /auth/set-initial-password`
    for it, with no proof of ownership. That path closes permanently the moment
    a password exists, so the fix is always to set one.
    """
    unclaimed = [u for u in users if not u.password_hash]
    if not unclaimed:
        return

    names = ", ".join(u.username or u.email for u in unclaimed)
    print(
        f"\nWARNING: {len(unclaimed)} account(s) have no password: {names}\n"
        "         Anyone who can reach the app can claim them from the login\n"
        "         screen and take the account, with all of its data. Set a\n"
        "         password now:  manage_users.py set-password --username <name>",
        file=sys.stderr,
    )


def cmd_list(args) -> int:
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id).all()
        if not users:
            print("No users.")
            return 0

        print(f"{'ID':>4}  {'USERNAME':<24} {'EMAIL':<40} {'PASSWORD':<11} NAME")
        for user in users:
            has_pw = "set" if user.password_hash else "CLAIMABLE"
            print(
                f"{user.id:>4}  {user.username or '':<24} {user.email:<40} "
                f"{has_pw:<11} {user.name or ''}"
            )
        _warn_claimable(users)
        return 0
    finally:
        db.close()


def cmd_create(args) -> int:
    username = args.username.strip().lower()
    email = args.email.strip().lower()

    if not username:
        print("Error: --username cannot be empty.", file=sys.stderr)
        return 1

    sanitised = derive_username(username)
    if sanitised != username:
        print(
            f"Error: username must match [a-z0-9._-] (suggested: {sanitised!r}).",
            file=sys.stderr,
        )
        return 1

    db = SessionLocal()
    try:
        existing = _find_user(db, username, email)
        if existing:
            clash = "username" if existing.username == username else "email"
            print(
                f"Error: a user with that {clash} already exists "
                f"(id={existing.id}, username={existing.username}, email={existing.email}).",
                file=sys.stderr,
            )
            return 1

        password = _prompt_password()

        user = User(
            username=username,
            email=email,
            name=args.name,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created user id={user.id} username={user.username} email={user.email}")
        # _prompt_password() never returns empty, so this should not fire —
        # it's here so that a future code path which skips the prompt can't
        # quietly mint a claimable account.
        _warn_claimable([user])
        return 0
    finally:
        db.close()


def cmd_set_password(args) -> int:
    username = args.username.strip().lower() if args.username else None
    email = args.email.strip().lower() if args.email else None

    db = SessionLocal()
    try:
        user = _find_user(db, username, email)
        if not user:
            print("Error: no such user.", file=sys.stderr)
            return 1

        print(
            f"Setting password for id={user.id} username={user.username} email={user.email}"
        )
        password = _prompt_password()

        user.password_hash = hash_password(password)
        db.commit()
        print("Password updated.")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage Askesis user accounts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List all users")
    p_list.set_defaults(func=cmd_list)

    p_create = sub.add_parser("create", help="Create a user (prompts for a password)")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--name", required=True)
    p_create.set_defaults(func=cmd_create)

    p_set = sub.add_parser(
        "set-password", help="Set a user's password (prompts twice; never takes a flag)"
    )
    p_set.add_argument("--username")
    p_set.add_argument("--email")
    p_set.set_defaults(func=cmd_set_password)

    args = parser.parse_args(argv)

    if args.command == "set-password" and not (args.username or args.email):
        parser.error("set-password requires --username or --email")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
