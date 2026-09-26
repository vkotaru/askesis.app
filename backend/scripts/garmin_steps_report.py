#!/usr/bin/env python3
"""Show what Garmin says about your steps, what the database says, and why.

This exists because a step count can be wrong in four different places and the
app's screen shows only the last one. It prints all four side by side:

    date        garmin(range)  garmin(single)  stored  owner     verdict
    2026-09-25           4187            4187      43  manual    STORED IS STALE

* **garmin(range)** — the one ranged call the nightly sync actually makes.
* **garmin(single)** — the same day asked for on its own. These two disagreeing
  means the ranged endpoint dropped a day, which is a Garmin-side flake the sync
  repairs by falling back to the per-day call.
* **stored / owner** — the row in this database and who provenance says owns the
  step count (`garmin`, `manual`, or `-` for rows predating provenance).

The verdict column is the point. `MANUAL LOCK` means the field is flagged as
hand-entered, so **the importer will never correct it** no matter how many times
you re-sync — which is exactly how a partial early-morning count gets frozen
forever. `--repair` hands those days back to the importer.

Check the dry run before applying: `--repair` cannot tell a count frozen by the
provenance bug from one you genuinely typed, so it lists every day and its value
for you to read first. A step count you really did enter by hand should be left
alone — re-run with a narrower `--days` if one appears in the list.

Run from `backend/` — config resolves `.env` against the working directory:

    python scripts/garmin_steps_report.py --days 14
    python scripts/garmin_steps_report.py --days 14 --repair          # dry run
    python scripts/garmin_steps_report.py --days 14 --repair --apply

In the container `WORKDIR` is already `/app/backend`:

    docker compose exec app python scripts/garmin_steps_report.py --days 14

Needs the same cached session as the sync; run `garmin_sync.py --login` first if
there isn't one. `--offline` skips Garmin entirely and reports only what is
stored, which is enough to find a locked field.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import garmin
from app.config import get_settings
from app.database import SessionLocal
from app.models import DailyLog
from app.provenance import MANUAL, mark_provider, parse_sources
from scripts.garmin_sync import resolve_user


def fetch_range(api, start: str, end: str) -> dict[str, int | None]:
    """The one ranged call the scheduled sync makes, verbatim."""
    rows = api.get_daily_steps(start, end)
    return {r["calendarDate"]: r.get("totalSteps") for r in rows}


def fetch_single(api, iso: str) -> int | None:
    """The same day on its own — the sync's fallback when the range drops one."""
    for row in api.get_daily_steps(iso, iso):
        if row.get("calendarDate") == iso:
            return row.get("totalSteps")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", help="Askesis username or email")
    ap.add_argument("--days", type=int, default=14, help="days back (default 14)")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="skip Garmin; report only what is stored and who owns it",
    )
    ap.add_argument(
        "--repair",
        action="store_true",
        help="release the manual flag on steps so the importer can correct them",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="with --repair, actually write (default is a dry run)",
    )
    args = ap.parse_args()

    settings = get_settings()
    tz = ZoneInfo(settings.garmin_sync_tz)
    today = datetime.now(tz).date()
    start = today - timedelta(days=args.days)
    days = [start + timedelta(days=i) for i in range(args.days + 1)]

    api = None
    if not args.offline:
        try:
            api = garmin.connect(settings.garmin_tokenstore)
        except Exception as exc:  # noqa: BLE001 - report cleanly, no traceback
            sys.exit(
                f"No usable cached session ({type(exc).__name__}: {exc}).\n"
                "Run `python scripts/garmin_sync.py --login` first, "
                "or pass --offline to report on the database alone."
            )

    ranged: dict[str, int | None] = {}
    if api is not None:
        print(f"Asking Garmin for {start} .. {today} (tz {settings.garmin_sync_tz})")
        try:
            ranged = fetch_range(api, start.isoformat(), today.isoformat())
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ranged call failed: {type(exc).__name__}: {exc}")

    db = SessionLocal()
    try:
        user = resolve_user(db, args.user)
        print(f"Account: {user.username} (id={user.id})\n")

        logs = {
            log.date: log
            for log in db.query(DailyLog)
            .filter(
                DailyLog.user_id == user.id,
                DailyLog.date >= start,
                DailyLog.deleted_at.is_(None),
            )
            .all()
        }

        header = (
            f"{'date':<12}{'range':>8}{'single':>9}{'stored':>9}  {'owner':<9}verdict"
        )
        print(header)
        print("-" * len(header))

        locked: list[DailyLog] = []
        for day in days:
            iso = day.isoformat()
            log = logs.get(day)
            stored = log.steps if log else None
            owner = parse_sources(log.sources).get("steps", "-") if log else "-"

            in_range = iso in ranged
            range_val = ranged.get(iso)

            # Only worth a second request where it tells us something: the range
            # omitted the day, or what it returned disagrees with the database.
            single_val: int | None = None
            single_shown = "-"
            if api is not None and (not in_range or range_val != stored):
                try:
                    single_val = fetch_single(api, iso)
                    single_shown = "none" if single_val is None else str(single_val)
                except Exception as exc:  # noqa: BLE001
                    single_shown = f"ERR({type(exc).__name__})"

            truth = range_val if in_range and range_val else single_val
            verdict = ""
            if api is None:
                verdict = "MANUAL LOCK" if owner == MANUAL else ""
            elif truth is None:
                verdict = "garmin has nothing"
            elif stored is None:
                verdict = "MISSING — never imported"
            elif truth != stored:
                verdict = "STORED IS STALE"
                if owner == MANUAL:
                    verdict += " (MANUAL LOCK — import refuses to correct it)"
                    locked.append(log)
            if not in_range and truth is not None:
                verdict = (verdict + " | range dropped this day").lstrip(" |")

            print(
                f"{iso:<12}"
                f"{('-' if not in_range else 'none' if range_val is None else range_val):>8}"
                f"{single_shown:>9}"
                f"{('-' if stored is None else stored):>9}  "
                f"{owner:<9}{verdict}"
            )

        if args.offline:
            locked = [
                log
                for day, log in sorted(logs.items())
                if parse_sources(log.sources).get("steps") == MANUAL
            ]

        if not args.repair:
            if locked:
                print(
                    f"\n{len(locked)} day(s) have a manual lock on steps. "
                    "Re-syncing will NOT fix those.\n"
                    "Hand them back to the importer with --repair "
                    "(add --apply to write)."
                )
            return 0

        if not locked:
            print("\nNothing to repair — no step count is manually locked.")
            return 0

        print(f"\n{'APPLYING' if args.apply else 'DRY RUN'} — handing the step count")
        print(
            f"on these days back to '{garmin.SOURCE}', so the next sync corrects them:"
        )
        # Reassigned to the importer, NOT merely un-flagged. Dropping the entry
        # leaves the field with no recorded owner, and `garmin.py` treats unknown
        # ownership as fill-blanks-only -- so a wrong-but-present count would sit
        # there exactly as stuck as before, which is how this repair failed its
        # first test. Naming the importer as owner is also the honest claim: the
        # number came from the importer, and the manual flag was never true.
        for log in locked:
            print(f"  {log.date}  steps={log.steps}  -> owner = {garmin.SOURCE}")
            if args.apply:
                log.sources = mark_provider(log.sources, ["steps"], garmin.SOURCE)

        if args.apply:
            db.commit()
            print(
                f"\nReassigned {len(locked)} day(s). Now run:\n"
                f"  python scripts/garmin_sync.py --user {user.username} "
                f"--days {args.days}"
            )
        else:
            print("\nNothing written. Re-run with --apply to commit.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
