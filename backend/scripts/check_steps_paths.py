#!/usr/bin/env python3
"""Every way a step count can be written, checked in one run.

This repo has no test suite, and this is the one place that hurt for it: the
"Garmin is not importing my steps" bug was reported three times and fixed four,
because each fix verified the path it had just changed and shipped. The failure
was never in that path. It was in the one nobody re-checked.

So: all of them, together, every time. Run it against a scratch database after
touching `provenance.py`, `garmin.py`, `routers/daily_log.py` or the DailyLog
half of `routers/sync.py`:

    cd backend
    rm -f /tmp/steps.db
    DEV_MODE=true SECRET_KEY=x DATABASE_URL="sqlite:////tmp/steps.db" \
      python -m alembic upgrade head
    DEV_MODE=true SECRET_KEY=x DATABASE_URL="sqlite:////tmp/steps.db" \
      python scripts/check_steps_paths.py

Exits non-zero on any failure, so CI can call it. Point it at a throwaway
database -- it deletes every daily_log row between cases.

The two cases most worth keeping are not the bug: they are cases 3 and 4, which
say a number the user typed beats the importer and a field they cleared stays
clear. Every fix to this bug risks trading one of those away for the other.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date
from app.database import SessionLocal
from app.models import User, DailyLog
from app.garmin import _fill_daily_log, SyncReport
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
c.get("/api/settings/")
db = SessionLocal()
u = db.query(User).first()
DAY = date(2026, 9, 26)
fails = []


def reset():
    db.query(DailyLog).delete()
    db.commit()


def garmin(v):
    _fill_daily_log(db, u, DAY, {"steps": v}, SyncReport())
    db.commit()
    db.expire_all()


def row():
    return db.query(DailyLog).filter(DailyLog.date == DAY).one()


def push(data, ts="2027-01-01T12:00:00", op="update"):
    r = c.post(
        "/api/sync/push",
        json={
            "changes": [
                {
                    "table": "dailyLogs",
                    "operation": op,
                    "localId": 1,
                    "timestamp": ts,
                    "serverId": row().id if op == "update" else None,
                    "data": data,
                }
            ]
        },
    )
    db.expire_all()
    return r


def rest(data):
    r = c.post("/api/daily-log/", json={**data, "date": DAY.isoformat()})
    db.expire_all()
    return r


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print(f"  {'OK  ' if ok else 'FAIL'} {label:<58} {got!r:>8}  want {want!r}")


# 1. THE REPORTED BUG, via sync: stale tab pushes an old steps value with a weight edit.
reset()
garmin(43)
stale = row().steps
garmin(4187)
push({"date": DAY.isoformat(), "weight": 74.2, "steps": stale, "_edited": ["weight"]})
check("stale tab logs weight (sync) -> steps untouched", row().steps, 4187)
garmin(9001)
check("  ...and garmin can still correct it", row().steps, 9001)

# 2. Same, via the REST path.
reset()
garmin(43)
stale = row().steps
garmin(4187)
rest({"weight": 74.2, "steps": stale, "_edited": ["weight"]})
check("stale tab logs weight (REST) -> steps untouched", row().steps, 4187)
garmin(9001)
check("  ...and garmin can still correct it", row().steps, 9001)

# 3. A REAL hand-typed step count must win and must stick.
reset()
garmin(100)
push({"date": DAY.isoformat(), "steps": 9999, "_edited": ["steps"]})
check("user types 9999 -> stored", row().steps, 9999)
garmin(4187)
check("  ...and garmin must NOT overwrite it", row().steps, 9999)

# 4. A deliberate clear must stay blank.
reset()
garmin(500)
push({"date": DAY.isoformat(), "steps": None, "_edited": ["steps"]})
check("user clears steps -> blank", row().steps, None)
garmin(4187)
check("  ...and garmin must NOT refill it", row().steps, None)

# 5. An OLD client that sends no _edited at all: must not freeze the importer.
reset()
garmin(43)
stale = row().steps
garmin(4187)
push({"date": DAY.isoformat(), "weight": 74.2, "steps": stale})
check("pre-upgrade client, no _edited -> steps untouched", row().steps, 4187)
garmin(9001)
check("  ...and garmin can still correct it", row().steps, 9001)

# 6. The create-that-upserts branch (offline create landing on an existing row).
reset()
garmin(43)
garmin(4187)
push(
    {"date": DAY.isoformat(), "weight": 70.0, "steps": 43, "_edited": ["weight"]},
    op="create",
)
check("offline create upserts -> steps untouched", row().steps, 4187)

# 7. A field with no importer is still freely writable.
reset()
garmin(4187)
push({"date": DAY.isoformat(), "weight": 71.5, "_edited": ["weight"]})
check("weight (unowned) is written", row().weight, 71.5)

# 8. Clearing a field from the FORM must reach the server. The form used to send
#    `undefined` for an emptied weight/water/notes, which JSON.stringify drops --
#    so "cleared" was indistinguishable from "this request is not about that
#    field" and the old value came straight back on the next sync.
reset()
rest({"weight": 74.0, "_edited": ["weight"]})
rest({"weight": None, "_edited": ["weight"]})
check("clearing weight from the form sticks", row().weight, None)

# 9. Empty feelings must not 500 (reviewer finding 4).
reset()
check(
    "REST feelings=[] does not crash",
    rest({"feelings": [], "_edited": ["feelings"]}).status_code,
    200,
)

print()
print(
    "  "
    + (
        "ALL PATHS PASS"
        if not fails
        else f"{len(fails)} FAILURE(S): " + ", ".join(fails)
    )
)
raise SystemExit(1 if fails else 0)
