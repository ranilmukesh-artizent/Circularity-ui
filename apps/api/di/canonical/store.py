"""The canonical store: facts in, chosen values and conflicts out (docs/backend-steps.md, B9).

A connector maps each source record to `Fact`s. `apply()` keeps every source's value (provenance), then for each
touched field picks the canonical value:
    1. the value of the source with authority over the field (canonical/schema.py), when it has one;
    2. otherwise the value with the highest confidence (ties: most recently fetched).
When the sources' values differ, a conflict is opened that names the authority. It is closed automatically when
they agree again, or by a person (conflict.resolve / conflict.escalate).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.canonical.schema import MODELS, authority

NUMERIC_TOLERANCE = 0.005  # values within 0.5% count as the same (currency rounding, unit conversion)
# list fields every source adds to: the canonical value is the union, and sources never conflict on them
MERGE_FIELDS = {"asset.source_refs"}


@dataclass(frozen=True)
class Fact:
    model: str  # asset, condition, demand …
    key: str  # MTR-2041, SO-48102 …
    field: str  # owner_tenant, grade, need_by …
    value: Any  # canonical value (JSON-serialisable)
    source_field: str | None = None  # e.g. "EKPO-NETPR"
    source_value: Any = None  # e.g. "1002000.00 INR"
    transform: str | None = None  # e.g. "Currency at 83.5 (rate dated 2026-10-06)"
    resource: str | None = None
    ext_id: str | None = None
    confidence: float | None = None  # 0-100; defaults to the source's confidence

    def __post_init__(self):
        if self.model not in MODELS:
            raise ValueError(f"unknown canonical model {self.model!r}")


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, Decimal):
        return float(v)
    return v


def same(a: Any, b: Any) -> bool:
    a, b = _norm(a), _norm(b)
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool) and not isinstance(b, bool):
        scale = max(abs(a), abs(b), 1e-9)
        return abs(a - b) / scale <= NUMERIC_TOLERANCE
    return a == b


def _dumps(v: Any) -> str:
    return json.dumps(v, default=str)


def apply(session: Session, source_id: str, facts: list[Fact], default_confidence: float | None = None) -> int:
    """Record the facts of one source and update the canonical values and conflicts they touch. Returns facts written."""
    now = datetime.now(UTC)
    touched: set[tuple[str, str, str]] = set()
    # one fixed order for every writer, so two syncs touching the same records cannot deadlock each other
    for f in sorted(facts, key=lambda x: (x.model, x.key, x.field)):
        session.execute(
            text(
                "INSERT INTO provenance (model, key, field, source_id, value, source_field, source_value, transform, resource, "
                "ext_id, confidence, fetched_at) VALUES (:m, :k, :f, :s, CAST(:v AS jsonb), :sf, CAST(:sv AS jsonb), :t, :r, :e, "
                ":c, :at) ON CONFLICT (model, key, field, source_id) DO UPDATE SET value = EXCLUDED.value, "
                "source_field = EXCLUDED.source_field, source_value = EXCLUDED.source_value, transform = EXCLUDED.transform, "
                "resource = EXCLUDED.resource, ext_id = EXCLUDED.ext_id, confidence = EXCLUDED.confidence, "
                "fetched_at = EXCLUDED.fetched_at"
            ),
            {
                "m": f.model,
                "k": f.key,
                "f": f.field,
                "s": source_id,
                "v": _dumps(f.value),
                "sf": f.source_field,
                "sv": _dumps(f.source_value),
                "t": f.transform,
                "r": f.resource,
                "e": f.ext_id,
                "c": f.confidence if f.confidence is not None else default_confidence,
                "at": now,
            },
        )
        touched.add((f.model, f.key, f.field))
    for model, key, field in sorted(touched):
        _settle(session, model, key, field, now)
    return len(facts)


def _settle(session: Session, model: str, key: str, field: str, now: datetime) -> None:
    rows = session.execute(
        text("SELECT source_id, value, confidence, fetched_at FROM provenance WHERE model = :m AND key = :k AND field = :f"),
        {"m": model, "k": key, "f": field},
    ).all()
    auth = authority(model, field)
    by_source = {r.source_id: r for r in rows}
    if f"{model}.{field}" in MERGE_FIELDS:
        merged: list[Any] = []
        for r in sorted(rows, key=lambda r: r.source_id):
            for v in r.value if isinstance(r.value, list) else [r.value]:
                if v not in merged:
                    merged.append(v)
        chosen = SimpleNamespace(value=merged)
        rows = []  # a merged list never conflicts
    elif auth in by_source:
        chosen = by_source[auth]
    else:
        chosen = max(rows, key=lambda r: (float(r.confidence or 0), r.fetched_at))
    session.execute(
        text(
            "INSERT INTO canonical (model, key, data, version, updated_at) VALUES (:m, :k, jsonb_build_object(CAST(:f AS text), "
            "CAST(:v AS jsonb)), 1, :at) ON CONFLICT (model, key) DO UPDATE SET data = canonical.data || "
            "jsonb_build_object(CAST(:f AS text), CAST(:v AS jsonb)), version = canonical.version + 1, updated_at = :at "
            "WHERE canonical.data -> CAST(:f AS text) IS DISTINCT FROM CAST(:v AS jsonb)"
        ),
        {"m": model, "k": key, "f": field, "v": _dumps(chosen.value), "at": now},
    )
    distinct: list[Any] = []
    for r in rows:
        if not any(same(r.value, d) for d in distinct):
            distinct.append(r.value)
    if len(distinct) > 1:
        values = {r.source_id: r.value for r in rows}
        session.execute(
            text(
                'INSERT INTO conflict (model, key, field, "values", authority, opened_at) '
                "VALUES (:m, :k, :f, CAST(:v AS jsonb), :a, :at) "
                'ON CONFLICT (model, key, field) WHERE status = \'open\' DO UPDATE SET "values" = EXCLUDED."values"'
            ),
            {"m": model, "k": key, "f": field, "v": _dumps(values), "a": auth or chosen.source_id, "at": now},
        )
    else:
        session.execute(
            text(
                "UPDATE conflict SET status = 'resolved', closed_at = :at, closed_by = 'system', "
                "note = 'The sources agree again' "
                "WHERE model = :m AND key = :k AND field = :f AND status = 'open'"
            ),
            {"m": model, "k": key, "f": field, "at": now},
        )


def get(session: Session, model: str, key: str) -> dict | None:
    """The canonical record with each field's provenance."""
    row = session.execute(
        text("SELECT data, version, updated_at FROM canonical WHERE model = :m AND key = :k"), {"m": model, "k": key}
    ).first()
    if row is None:
        return None
    prov: dict[str, list[dict]] = {}
    for r in session.execute(
        text(
            "SELECT field, source_id, value, source_field, source_value, transform, resource, ext_id, confidence, fetched_at "
            "FROM provenance WHERE model = :m AND key = :k ORDER BY field, source_id"
        ),
        {"m": model, "k": key},
    ).mappings():
        prov.setdefault(r["field"], []).append(dict(r) | {"authority": authority(model, r["field"]) == r["source_id"]})
    return {
        "model": model,
        "key": key,
        "data": row.data,
        "version": row.version,
        "updated_at": row.updated_at,
        "provenance": prov,
    }
