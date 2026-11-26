"""The canonical store: facts in, chosen values and conflicts out (docs/backend-steps.md, B9).

A connector maps each source record to `Fact`s. `apply()` keeps every source's value (provenance), then for each
touched field picks the canonical value:
    1. the value of the source with authority over the field (canonical/schema.py), when it has one;
    2. otherwise the value with the highest confidence (ties: most recently fetched).
When the sources' values differ, a conflict is opened that names the authority. It is closed automatically when
they agree again, or by a person (conflict.resolve / conflict.escalate).

A person's resolution sticks (plan 6 B2): the conflict keeps the fingerprint of the values it was resolved on
(`conflict.values_hash`), and while the sources keep sending those values it is not reopened. Choosing another
source's value or entering one (`override`) writes a provenance row from source `manual` (resource `conflict`) that
is the canonical value while the resolution holds; when a value changes, a new conflict opens and the choice is
dropped. Manual Import rows (di/connectors/manual.py) are ordinary facts from source `manual` (resource `import`).

Any `compliance` fact (gate evidence, plan 9 P9-1.2) also enqueues a `case.gateRecheck` job for its asset, and so does a
`condition.wipe_certificate` (a device's data-wipe certificate, P9-6.7); a rental device's decontamination facts
(`DECON_FIELDS`, P9-11.6) re-check the `medical_rental` cases held on it. A `condition`
`grade` or `test_result` fact (the workbench grade, P9-3.5) enqueues a `case.reevaluate` job for each open tool-fleet case
of that serial.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import jobs
from di.services.canonical.schema import MODELS, authority, compliance_asset

NUMERIC_TOLERANCE = 0.005  # values within 0.5% count as the same (currency rounding, unit conversion)
# list fields every source adds to: the canonical value is the union, and sources never conflict on them
MERGE_FIELDS = {"asset.source_refs"}
MANUAL = "manual"  # the source of data a person entered: Manual Import rows, choices in the Conflict Queue
# the `condition` fields a tool-fleet case is valued again on: a workbench grade (P9-3.5), the telematics last seen (P9-3.8)
GRADE_FIELDS = ("grade", "test_result", "telemetry_at")
TITLE_FIELDS = (
    "title_status",
    "lien_open",
    "lien_release_ref",
    "title_brand",
    "payoff_confirmed",
    "odometer_statement_ref",
    "odometer_not_actual",
    "odometer_photo_reading",
)  # a car's title facts (P9-9.8), and the odometer facts that release a car held for a second inspection (P9-9.9)
DECON_FIELDS = ("decon_ended_at", "decon_started_at", "decon_record_ref", "decon_result")  # a device's decontamination (P9-11.6)
INVENTORY_FIELDS = ("inventory_status", "model", "site", "manufacturer", "region")  # a unit's inventory facts (P9-10.6, 10.7)
BENCH_FIELDS = (
    "wipe_status",
    "wipe_attempts",
    "wipe_scope",
    "wipe_certificate_ref",
    "wipe_verified_at",
    "bench_passed",
    "bench_total",
    "firmware",
)  # a unit's test bench facts: the wipe certificate and the bench read (P9-10.7)
OVERRIDE_RESOURCE = "conflict"  # a person's choice in the Conflict Queue (provenance.resource); imports are "import"


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
    # new evidence may release the cases held for it (plan 9, P9-1.2): one recheck job per asset (deduped)
    for asset_key in sorted({compliance_asset(f.key) for f in facts if f.model == "compliance"}):
        jobs.enqueue(session, "case.gateRecheck", {"asset_key": asset_key}, dedupe_key=f"case.gateRecheck:{asset_key}")
    # a device's wipe certificate may release the cases held on it (plan 9, P9-6.7): one recheck job per device (deduped)
    for key in sorted({f.key for f in facts if f.model == "condition" and f.field == "wipe_certificate"}):
        jobs.enqueue(session, "case.gateRecheck", {"asset_key": key}, dedupe_key=f"case.gateRecheck:{key}")
    # a change of a contract line re-checks the cases held on it (plan 9, P9-3.6): one recheck job per serial (deduped)
    lines = sorted({f.key for f in facts if f.model == "contract_line"})
    if lines:
        held = session.execute(
            text(
                "SELECT DISTINCT data ->> 'assetId' FROM case_record WHERE stage <> 'closed' AND data ->> 'assetId' = ANY(:k) "
                "AND data ->> 'template' = 'tool_fleet' AND jsonb_typeof(data -> 'gateHold') = 'object'"
            ),
            {"k": lines},
        ).scalars()
        for asset_key in sorted(held):
            jobs.enqueue(session, "case.gateRecheck", {"asset_key": asset_key}, dedupe_key=f"case.gateRecheck:{asset_key}")
    # facts that can release a gate hold re-check the cases held on that asset, one recheck job per asset (deduped):
    # a car's title (P9-9.8), a rental device's decontamination (P9-11.6), a telecom unit's inventory record (P9-10.6)
    for model, fields, template in (
        ("condition", TITLE_FIELDS, "used_cars"),
        ("condition", DECON_FIELDS, "medical_rental"),
        ("asset", INVENTORY_FIELDS, "telecom_network"),
        ("condition", BENCH_FIELDS, "telecom_network"),  # the wipe re-run on the bench (P9-10.7)
    ):
        keys = sorted({f.key for f in facts if f.model == model and f.field in fields})
        if not keys:
            continue
        held = session.execute(
            text(
                "SELECT DISTINCT data ->> 'assetId' FROM case_record WHERE stage <> 'closed' AND data ->> 'assetId' = ANY(:k) "
                "AND data ->> 'template' = :t AND jsonb_typeof(data -> 'gateHold') = 'object'"
            ),
            {"k": keys, "t": template},
        ).scalars()
        for asset_key in sorted(held):
            jobs.enqueue(session, "case.gateRecheck", {"asset_key": asset_key}, dedupe_key=f"case.gateRecheck:{asset_key}")
    # a late workbench grade re-evaluates the open tool-fleet cases of the serial (plan 9, P9-3.5): one job per case (deduped)
    for serial in sorted({f.key for f in facts if f.model == "condition" and f.field in GRADE_FIELDS}):
        ids = session.execute(
            text(
                "SELECT id FROM case_record WHERE stage <> 'closed' AND data ->> 'template' = 'tool_fleet' "
                "AND data ->> 'serial' = :k ORDER BY id"
            ),
            {"k": serial},
        ).scalars()
        for case_id in list(ids):
            jobs.enqueue(session, "case.reevaluate", {"case_id": case_id}, dedupe_key=f"case.reevaluate:{case_id}")
    return len(facts)


def values_hash(values: dict[str, Any]) -> str:
    """The fingerprint of a conflict's differing values ({source: value}): a person's resolution holds while it is
    unchanged (plan 6 B2)."""
    norm = {k: _norm(v) for k, v in values.items()}
    return hashlib.sha256(json.dumps(norm, sort_keys=True, default=str).encode()).hexdigest()[:32]


def settle(session: Session, model: str, key: str, field: str) -> None:
    """Choose the field's canonical value again (after a person resolved its conflict)."""
    _settle(session, model, key, field, datetime.now(UTC))


def override(session: Session, model: str, key: str, field: str, value: Any, by: str, note: str | None = None) -> None:
    """A person's choice in the Conflict Queue: a provenance row from source `manual` (resource `conflict`), which is
    the canonical value while the conflict's resolution holds (the sources' values unchanged). Call it after the
    conflict is marked resolved (conflict.values_hash), in the same transaction."""
    session.execute(
        text(
            "INSERT INTO provenance (model, key, field, source_id, value, source_field, source_value, transform, resource, "
            "ext_id, confidence, fetched_at) VALUES (:m, :k, :f, :s, CAST(:v AS jsonb), NULL, CAST(:v AS jsonb), :t, :r, "
            ":by, NULL, now()) ON CONFLICT (model, key, field, source_id) DO UPDATE SET value = EXCLUDED.value, "
            "source_field = NULL, source_value = EXCLUDED.source_value, transform = EXCLUDED.transform, "
            "resource = EXCLUDED.resource, ext_id = EXCLUDED.ext_id, confidence = NULL, fetched_at = now()"
        ),
        {"m": model, "k": key, "f": field, "s": MANUAL, "v": _dumps(value), "t": note or f"Chosen by {by} in the Conflict Queue",
         "r": OVERRIDE_RESOURCE, "by": by},
    )  # fmt: skip
    settle(session, model, key, field)


def drop_override(session: Session, model: str, key: str, field: str) -> None:
    session.execute(
        text("DELETE FROM provenance WHERE model = :m AND key = :k AND field = :f AND source_id = :s AND resource = :r"),
        {"m": model, "k": key, "f": field, "s": MANUAL, "r": OVERRIDE_RESOURCE},
    )


def _settle(session: Session, model: str, key: str, field: str, now: datetime) -> None:
    rows = session.execute(
        text(
            "SELECT source_id, value, confidence, fetched_at, resource FROM provenance "
            "WHERE model = :m AND key = :k AND field = :f"
        ),
        {"m": model, "k": key, "f": field},
    ).all()
    # a person's choice in the Conflict Queue is not a source: it never takes part in a conflict
    manual = next((r for r in rows if r.source_id == MANUAL and r.resource == OVERRIDE_RESOURCE), None)
    if manual is not None:
        rows = [r for r in rows if r is not manual]
        if not rows:  # every source's value is gone: so is the choice between them
            drop_override(session, model, key, field)
            session.execute(
                text(
                    "UPDATE canonical SET data = data - CAST(:f AS text), version = version + 1, updated_at = :at "
                    "WHERE model = :m AND key = :k AND jsonb_exists(data, CAST(:f AS text))"
                ),
                {"m": model, "k": key, "f": field, "at": now},
            )
            return
    auth = authority(model, field)
    by_source = {r.source_id: r for r in rows}
    if f"{model}.{field}" in MERGE_FIELDS:
        merged: list[Any] = []
        for r in sorted(rows, key=lambda r: r.source_id):
            for v in r.value if isinstance(r.value, list) else [r.value]:
                if v not in merged:
                    merged.append(v)
        chosen: Any = SimpleNamespace(value=merged)
        rows = []  # a merged list never conflicts
    elif auth in by_source:
        chosen = by_source[auth]
    else:
        chosen = max(rows, key=lambda r: (float(r.confidence or 0), r.fetched_at))
    distinct: list[Any] = []
    for r in rows:
        if not any(same(r.value, d) for d in distinct):
            distinct.append(r.value)
    keep_choice = False
    if len(distinct) > 1:
        values = {r.source_id: r.value for r in rows}
        h = values_hash(values)
        last = session.execute(
            text(
                "SELECT status, closed_by, values_hash FROM conflict WHERE model = :m AND key = :k AND field = :f "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"m": model, "k": key, "f": field},
        ).first()
        # resolved by a person and the sources still say the same: it stays resolved (plan 6 B2)
        keep_choice = last is not None and last.status == "resolved" and last.closed_by != "system" and last.values_hash == h
        if not keep_choice:
            session.execute(
                text(
                    'INSERT INTO conflict (model, key, field, "values", authority, opened_at, values_hash) '
                    "VALUES (:m, :k, :f, CAST(:v AS jsonb), :a, :at, :h) "
                    "ON CONFLICT (model, key, field) WHERE status IN ('open', 'escalated') "
                    'DO UPDATE SET "values" = EXCLUDED."values", values_hash = EXCLUDED.values_hash'
                ),
                {"m": model, "k": key, "f": field, "v": _dumps(values), "a": auth or chosen.source_id, "at": now, "h": h},
            )
    else:
        session.execute(
            text(
                "UPDATE conflict SET status = 'resolved', closed_at = :at, closed_by = 'system', "
                "note = 'The sources agree again' "
                "WHERE model = :m AND key = :k AND field = :f AND status IN ('open', 'escalated')"
            ),
            {"m": model, "k": key, "f": field, "at": now},
        )
    if manual is not None:
        if keep_choice:
            chosen = manual
        else:  # the values the person chose between changed (or agree now): the choice no longer applies
            drop_override(session, model, key, field)
    session.execute(
        text(
            "INSERT INTO canonical (model, key, data, version, updated_at) VALUES (:m, :k, jsonb_build_object(CAST(:f AS text), "
            "CAST(:v AS jsonb)), 1, :at) ON CONFLICT (model, key) DO UPDATE SET data = canonical.data || "
            "jsonb_build_object(CAST(:f AS text), CAST(:v AS jsonb)), version = canonical.version + 1, updated_at = :at "
            "WHERE canonical.data -> CAST(:f AS text) IS DISTINCT FROM CAST(:v AS jsonb)"
        ),
        {"m": model, "k": key, "f": field, "v": _dumps(chosen.value), "at": now},
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
