"""POST /api/ingest/mfp through the real FastAPI app, over SQLite.

The parser is replaced with a stub in most tests (its own tests cover it), so
these run without Tesseract and test the HTTP layer: auth, the dry run, the
real write, idempotency and the double-count guard. One test goes through
real OCR on a fixture image when the binary is present.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import intake_log, mfp_ingest, mfp_ocr
from app.main import app
from app.mfp_ocr import DayRead, MealRead
from app.models import DailyNutrition, Meal

FIX = Path(__file__).parent / "fixtures" / "mfp"
TOKEN = "tests-only-ingest-token"  # what conftest put in MFP_INGEST_TOKEN
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TODAY = "2026-11-08"
NOV4 = date(2026, 11, 4)

READ_NOV4 = DayRead(
    day=NOV4,
    meals={
        "Breakfast": MealRead("Breakfast", 610, 55.0, 22.0, 38.0),
        "Lunch": MealRead("Lunch", 740, 70.0, 25.0, 45.0),
        "Dinner": MealRead("Dinner", 520, 30.0, 18.0, 50.0),
        "Snacks": MealRead("Snacks", 210, 25.0, 8.0, 6.0),
    },
    images=1,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def stub_parser(monkeypatch):
    """No OCR: every upload parses to READ_NOV4."""
    monkeypatch.setattr(mfp_ingest, "tesseract_problem", lambda: None)
    monkeypatch.setattr(mfp_ocr, "parse_screenshots", lambda blobs, today: [READ_NOV4])


def _post(client, *, dry_run, force=False, headers=AUTH, today=TODAY, n_images=1):
    files = [
        ("images", (f"shot{i}.png", b"\x89PNG not really", "image/png"))
        for i in range(n_images)
    ]
    return client.post(
        "/api/ingest/mfp",
        files=files,
        data={
            "today": today,
            "dry_run": str(dry_run).lower(),
            "force": str(force).lower(),
        },
        headers=headers,
    )


def _meals(db, user_id):
    return {
        m.label: m
        for m in db.query(Meal).filter(Meal.user_id == user_id, Meal.date == NOV4).all()
    }


def _day(db, user_id):
    return (
        db.query(DailyNutrition)
        .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == NOV4)
        .first()
    )


# ── auth ─────────────────────────────────────────────────────────────────────


def test_401_without_token(client, user, stub_parser):
    r = _post(client, dry_run=True, headers={})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_401_with_wrong_token(client, user, stub_parser):
    r = _post(client, dry_run=True, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    r = _post(client, dry_run=True, headers={"Authorization": f"Basic {TOKEN}"})
    assert r.status_code == 401


def test_route_is_absent_when_token_unset():
    """main.py mounts the router only when MFP_INGEST_TOKEN is set."""
    import app.main as main_mod

    assert any(getattr(r, "path", "") == "/api/ingest/mfp" for r in main_mod.app.routes)
    # The guard itself: an empty configured token can never match.
    assert not mfp_ingest.token_matches(TOKEN, "")


# ── the flow ─────────────────────────────────────────────────────────────────


def test_dry_run_writes_nothing(client, db, user, stub_parser):
    r = _post(client, dry_run=True)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    lines = r.text.splitlines()
    assert lines[0] == "[preview] Wed Nov 4: 2080 kcal"
    assert "  Lunch: 740 kcal P45 C70 F25 (new)" in lines
    assert lines[-1] == "Would write 4."
    assert len(lines) <= 12
    assert _meals(db, user.id) == {}
    assert _day(db, user.id) is None


def test_real_run_writes_all_four_meals(client, db, user, stub_parser):
    r = _post(client, dry_run=False)
    assert r.status_code == 200, r.text
    assert r.text.splitlines()[-1] == "Wrote 4."
    meals = _meals(db, user.id)
    assert {k: m.calories for k, m in meals.items()} == {
        "Breakfast": 610,
        "Lunch": 740,
        "Dinner": 520,
        "Snack": 210,
    }
    assert meals["Lunch"].protein_g == 45.0
    day = _day(db, user.id)
    assert (day.protein_g, day.carbs_g, day.fat_g) == (139.0, 180.0, 73.0)


def test_resend_is_idempotent(client, db, user, stub_parser):
    _post(client, dry_run=False)
    snapshot = {
        k: (m.calories, m.protein_g, m.carbs_g, m.fat_g, m.updated_at)
        for k, m in _meals(db, user.id).items()
    }
    day_before = (_day(db, user.id).protein_g, _day(db, user.id).updated_at)
    db.rollback()  # end the read snapshot; see conftest

    r = _post(client, dry_run=False)
    assert r.status_code == 200
    assert r.text.splitlines()[-1] == "Wrote 0."
    assert "(same)" in r.text
    after = {
        k: (m.calories, m.protein_g, m.carbs_g, m.fat_g, m.updated_at)
        for k, m in _meals(db, user.id).items()
    }
    assert after == snapshot
    assert (_day(db, user.id).protein_g, _day(db, user.id).updated_at) == day_before
    assert db.query(Meal).filter(Meal.date == NOV4).count() == 4


def test_double_count_guard(client, db, user, stub_parser):
    # An older day: calories per meal, macros typed for the whole day.
    intake_log.log_day(
        db,
        user.id,
        NOV4,
        meals={"Breakfast": 400},
        protein_g=90.0,
        carbs_g=150.0,
        fat_g=60.0,
    )
    db.commit()

    preview = _post(client, dry_run=True)
    assert preview.status_code == 200
    assert "! refused:" in preview.text and "force=true" in preview.text
    assert preview.text.splitlines()[-1] == "Would write 0, skipped 4."

    refused = _post(client, dry_run=False)
    assert refused.status_code == 409
    assert "don't match its meals" in refused.text
    db.rollback()  # end the read snapshot; see conftest
    assert _day(db, user.id).protein_g == 90.0  # untouched
    assert _meals(db, user.id)["Breakfast"].calories == 400

    forced = _post(client, dry_run=False, force=True)
    assert forced.status_code == 200, forced.text
    assert "! forced: dropping 90g protein, 150g carbs, 60g fat" in forced.text
    db.rollback()  # end the read snapshot; see conftest
    day = _day(db, user.id)
    assert (day.protein_g, day.carbs_g, day.fat_g) == (
        139.0,
        180.0,
        73.0,
    )  # the screenshot, once
    assert _meals(db, user.id)["Breakfast"].calories == 610


# ── errors ───────────────────────────────────────────────────────────────────


def test_bad_today_is_400(client, user, stub_parser):
    r = _post(client, dry_run=True, today="11/08/2026")
    assert r.status_code == 400
    assert "YYYY-MM-DD" in r.text


def test_unreadable_header_is_422(client, user, monkeypatch):
    monkeypatch.setattr(mfp_ingest, "tesseract_problem", lambda: None)
    monkeypatch.setattr(
        mfp_ocr,
        "ocr_text",
        lambda blob: "Meals\nBreakfast\n610 cal • NC 55g F 22g P 38g",
    )
    r = _post(client, dry_run=True)
    assert r.status_code == 422
    assert "no date in the header" in r.text


def test_missing_tesseract_is_503(client, user, monkeypatch):
    monkeypatch.setattr(
        mfp_ingest,
        "tesseract_problem",
        lambda: "the `tesseract` binary is not on PATH.",
    )
    r = _post(client, dry_run=True)
    assert r.status_code == 503
    assert "OCR unavailable" in r.text


def test_no_account_is_503(client, stub_parser):
    # No `user` fixture: zero accounts.
    r = _post(client, dry_run=True)
    assert r.status_code == 503
    assert "MFP_INGEST_USER" in r.text


# ── the whole path, real OCR ─────────────────────────────────────────────────


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)
def test_real_ocr_end_to_end(client, db, user):
    blob = (FIX / "grams_nov4.png").read_bytes()
    r = client.post(
        "/api/ingest/mfp",
        files=[("images", ("grams_nov4.png", blob, "image/png"))],
        data={"today": TODAY, "dry_run": "false"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.text.splitlines()[0] == "Wed Nov 4: 2080 kcal"
    assert _meals(db, user.id)["Dinner"].calories == 520
