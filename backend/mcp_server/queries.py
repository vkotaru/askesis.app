"""Every database read in this package goes through here.

**This module is the security boundary for data access.** Two invariants have
to hold on every query the MCP service makes, and both fail silently when
missed:

1. **Ownership.** A tool may only ever see rows belonging to the account the
   OAuth token was issued for. There is no ``user_id`` parameter on any tool —
   the token subject is the only identity — so the scoping has nowhere else to
   live.
2. **Soft deletes.** Most tables here are soft-deleted (``deleted_at``), and
   the app's routers filter them out per-endpoint. A deleted row resurfacing in
   a summary is invisible: no error, no warning, just a model confidently
   telling you about a workout you removed.

Reimplementing both by hand in a dozen query sites is exactly how one of them
gets forgotten, and this repo has no test suite to catch it. So there is one
constructor, `owned()`, it takes ``user_id`` as a required positional argument
(forgetting it is a ``TypeError``, not a leak), and it applies the soft-delete
filter for any model that has the column.

**Do not add ``db.query(...)`` anywhere else in this package.** Every access
goes through one of the four constructors below; the CI check greps for it.
Two models cannot use `owned()` because they have no ``user_id`` of their own,
so they get sanctioned escape hatches rather than an ad-hoc query at the call
site: `by_id` (``User``, keyed by the primary key that *is* the identity) and
`children_of` (``PlannedWorkout``, reached only through an already-owned
parent). The point is that ownership is enforced by construction, not by a
reader noticing a filter two lines away.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any, TypeVar

from sqlalchemy.orm import Query, Session

T = TypeVar("T")

#: Rows returned by any single tool call, before the tool's own tighter cap.
#: A backstop against a query with a bad date range dragging the whole table
#: into a model's context window.
MAX_ROWS = 1000


def owned(db: Session, model: type[T], user_id: int) -> Query[T]:
    """The only way this package builds a query.

    Scopes to ``user_id`` and excludes soft-deleted rows. Both are mandatory;
    neither is a keyword argument you can leave off.
    """
    # `type(...) is not int` rather than isinstance: bool subclasses int, so
    # `owned(db, DailyLog, True)` would otherwise filter `user_id == 1` and
    # hand back user 1's rows. A str would compare cleanly and silently match
    # nothing, which reads as "no data" rather than as a bug.
    if type(user_id) is not int or user_id <= 0:
        raise TypeError(f"user_id must be a positive int, got {user_id!r}")

    q = db.query(model).filter(model.user_id == user_id)
    if hasattr(model, "deleted_at"):
        q = q.filter(model.deleted_at.is_(None))
    return q


def by_id(db: Session, model: type[T], row_id: int) -> T | None:
    """Fetch one row by primary key. For ``User``, whose PK *is* the identity.

    Sanctioned bypass of `owned()`: ``User`` has no ``user_id`` column, and the
    id being looked up is the token subject itself. Never use this for a model
    that has an owner — that is what `owned()` is for.
    """
    if type(row_id) is not int or row_id <= 0:
        raise TypeError(f"row_id must be a positive int, got {row_id!r}")
    return db.query(model).filter(model.id == row_id).one_or_none()


def children_of(
    db: Session, model: type[T], fk_column: Any, parent_id: int
) -> Query[T]:
    """Rows hanging off an already-owned parent.

    Sanctioned bypass of `owned()` for models with no ``user_id`` of their own
    (``PlannedWorkout`` → ``TrainingPlan``). **The caller must have obtained
    ``parent_id`` from an `owned()` query** — that is what makes this safe, and
    it is the one invariant here that a reader has to check rather than the
    type system.
    """
    q = db.query(model).filter(fk_column == parent_id)
    if hasattr(model, "deleted_at"):
        q = q.filter(model.deleted_at.is_(None))
    return q


def in_range(
    q: Query[T], model: type[T], start: date_type | None, end: date_type | None
) -> Query[T]:
    """Constrain a query to a date window, inclusive at both ends."""
    if start is not None:
        q = q.filter(model.date >= start)
    if end is not None:
        q = q.filter(model.date <= end)
    return q


def clamp_limit(limit: int, ceiling: int = MAX_ROWS) -> int:
    """Validate a caller-supplied row limit.

    Raises rather than silently clamping: the caller is a language model, and a
    request for 999999 rows that quietly returns 1000 teaches it that the
    argument does nothing. `MAX_ROWS` is the hard ceiling on any single call.
    """
    if type(limit) is not int or isinstance(limit, bool):
        raise ValueError(f"limit must be an integer, got {limit!r}")
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    return min(limit, ceiling)


def capped(q: Query[T], limit: int) -> tuple[list[T], bool]:
    """Return at most ``limit`` rows, plus whether more were available.

    Fetches one extra row rather than issuing a COUNT: the caller only needs to
    know *that* it truncated, so it can say so instead of silently cutting.
    """
    limit = clamp_limit(limit)
    rows = q.limit(limit + 1).all()
    if len(rows) > limit:
        return rows[:limit], True
    return rows, False


def iso(value: Any) -> Any:
    """Dates and datetimes as ISO-8601 strings; everything else untouched."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
