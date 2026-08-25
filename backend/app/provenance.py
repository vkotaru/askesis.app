"""Per-field provenance for daily logs: who put this number here?

`daily_logs.sources` holds comma-separated `field:owner` pairs
(`steps:garmin,weight:manual`), matching how `feelings` is already stored
rather than introducing this schema's first JSON column.

Two rules give the format its meaning:

- **An absent entry means unknown**, and unknown behaves exactly as the app did
  before this column existed: a NULL field is fillable by an importer, a filled
  field is never overwritten. Every row predating the migration is unknown, so
  adding the column changed the meaning of no stored data.
- **`manual` is a claim by a person**, and it wins permanently. It is recorded
  even when the field is NULL, because "I deleted this" and "nothing has ever
  written this" need to be distinguishable -- otherwise the next import puts
  back exactly what the user just removed.

The payoff beyond a badge in the UI: knowing a value is an importer's own lets
that importer *correct* it. Without provenance the only safe rule is fill-blanks-
only, which freezes whatever lands in a NULL column -- including a bad or partial
reading -- for good.
"""

from __future__ import annotations

from collections.abc import Iterable

MANUAL = "manual"


def parse_sources(raw: str | None) -> dict[str, str]:
    """`"steps:garmin,weight:manual"` -> `{"steps": "garmin", ...}`.

    Tolerant on purpose: a malformed pair is dropped rather than raised. This
    column is metadata about health data, and it is never worth failing a read
    of someone's weight over a stray comma.
    """
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        field, _, owner = pair.partition(":")
        field, owner = field.strip(), owner.strip()
        if field and owner:
            out[field] = owner
    return out


def format_sources(sources: dict[str, str]) -> str | None:
    """Inverse of `parse_sources`. Empty maps to NULL, not to `""`, so "no
    provenance" has one representation in the database instead of two."""
    if not sources:
        return None
    return ",".join(f"{field}:{owner}" for field, owner in sorted(sources.items()))


def mark(raw: str | None, fields: Iterable[str], owner: str) -> str | None:
    """Stamp `owner` on each of `fields`, preserving every other entry."""
    sources = parse_sources(raw)
    for field in fields:
        sources[field] = owner
    return format_sources(sources)


def mark_manual(raw: str | None, fields: Iterable[str]) -> str | None:
    """A person set these fields -- including setting them to empty."""
    return mark(raw, fields, MANUAL)


def mark_provider(raw: str | None, fields: Iterable[str], provider: str) -> str | None:
    """An importer set these fields."""
    return mark(raw, fields, provider)


def owned_by(raw: str | None, field: str, owner: str) -> bool:
    """True only if `owner` is the recorded writer. Unknown is never owned --
    which is what keeps pre-migration rows behaving as they always have."""
    return parse_sources(raw).get(field) == owner


def is_manual(raw: str | None, field: str) -> bool:
    return owned_by(raw, field, MANUAL)
