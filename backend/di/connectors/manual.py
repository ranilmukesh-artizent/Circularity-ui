"""Manual Import through the pipeline (plan 6, B3): a controlled CSV import lands like a sync, from source `manual`.

    load(s, "IMP-3", rows, rejected) -> {"records": 2, "facts": 12, "held": 1}

Each loaded row is kept in `raw_record` (source `manual`, resource `import`, ext_id `IMP-n:<row>`) and mapped to
canonical facts (asset.asset_id, asset.qty, condition.grade, asset.location, asset.owner_tenant, asset.received_at)
that go through the same schema check and canonical store as a sync. They carry no confidence (provenance.confidence
NULL: manual evaluation data ranks below every source) and no live freshness (there is no `manual` source system, so
nothing schedules, ages or syncs it); every field they touch has a source with authority, whose value counts when it
has one. Nothing here queues an instruction or a job: imported rows can never trigger outbound work.

Rows the page or the server rejected are held in `failed_record` (run_kind `import`, run_id the import's IMP-n) with
their reasons. `remove` takes an import's data out again (the canonical values fall back to the sources').
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store
from di.services.canonical.failed import hold
from di.services.canonical.schema import split_facts
from di.services.canonical.store import Fact

SOURCE = store.MANUAL
RESOURCE = "import"
# CSV column -> canonical model and field
COLUMNS = (
    ("asset_id", "asset", "asset_id"),
    ("qty", "asset", "qty"),
    ("grade", "condition", "grade"),
    ("location", "asset", "location"),
    ("owner", "asset", "owner_tenant"),
    ("received", "asset", "received_at"),
)


def _value(col: str, raw: Any) -> Any:
    if col == "qty":
        try:
            return int(str(raw))
        except ValueError:
            return raw  # the schema check holds it
    return raw


def row_facts(row: dict, import_id: str, ext_id: str) -> list[Fact]:
    """One import row -> its canonical facts."""
    key = str(row.get("asset_id") or "")
    note = f"Manual import {import_id}; no live freshness"
    return [
        Fact(model, key, field, _value(col, row.get(col)), col, row.get(col), note, RESOURCE, ext_id, None)
        for col, model, field in COLUMNS
    ]


def load(s: Session, import_id: str, rows: list[dict], rejected: list[tuple[dict, list[str]]] | None = None) -> dict:
    """Land the import's valid rows (raw records, then facts through the schema check and the canonical store) and
    hold the rejected ones. In the caller's transaction."""
    facts = held = 0
    for n, row in enumerate(rows, 1):
        ext = f"{import_id}:{n}"
        s.execute(
            text(
                "INSERT INTO raw_record (source_id, resource, ext_id, payload, request, fetched_at) "
                "VALUES (:s, :r, :e, CAST(:p AS jsonb), :q, now()) ON CONFLICT (source_id, resource, ext_id) "
                "DO UPDATE SET payload = EXCLUDED.payload, request = EXCLUDED.request, fetched_at = now()"
            ),
            {"s": SOURCE, "r": RESOURCE, "e": ext, "p": json.dumps(row, default=str), "q": f"Controlled CSV import {import_id}"},
        )
        ok, bad = split_facts(row_facts(row, import_id, ext))
        facts += store.apply(s, SOURCE, ok, None)
        for f, why in bad:
            held += 1
            hold(
                s, run_kind="import", run_id=import_id, source_id=SOURCE, step="canonical", resource=RESOURCE, ext_id=ext,
                field=f"{f.model}.{f.field}", rule="schema", value=f.value, reason=why, payload=row,
            )  # fmt: skip
    for n, (row, errors) in enumerate(rejected or [], 1):
        held += 1
        hold(
            s, run_kind="import", run_id=import_id, source_id=SOURCE, step="validate", resource=RESOURCE,
            ext_id=f"{import_id}:rejected:{n}", rule="csv", value=row.get("asset_id"),
            reason="; ".join(errors) or "Rejected by the import's checks", payload=row,
        )  # fmt: skip
    return {"records": len(rows), "facts": facts, "held": held}


def remove(s: Session, import_id: str | None = None) -> int:
    """Take one import's data out (every import's when None): its raw records, held rows and facts; the canonical
    values fall back to the sources' (a field only the import had is removed). Returns the facts removed."""
    like = f"{import_id}:%" if import_id else "%"
    touched = s.execute(
        text("DELETE FROM provenance WHERE source_id = :s AND resource = :r AND ext_id LIKE :l RETURNING model, key, field"),
        {"s": SOURCE, "r": RESOURCE, "l": like},
    ).all()
    for model, key, field in sorted(set(touched)):
        left = s.execute(
            text("SELECT count(*) FROM provenance WHERE model = :m AND key = :k AND field = :f"),
            {"m": model, "k": key, "f": field},
        ).scalar_one()
        if left:
            store.settle(s, model, key, field)
        else:
            s.execute(
                text(
                    "UPDATE canonical SET data = data - CAST(:f AS text), version = version + 1, updated_at = now() "
                    "WHERE model = :m AND key = :k"
                ),
                {"m": model, "k": key, "f": field},
            )
        s.execute(  # conflicts the import's values opened are gone with them
            text('DELETE FROM conflict WHERE model = :m AND key = :k AND field = :f AND jsonb_exists("values", :s)'),
            {"m": model, "k": key, "f": field, "s": SOURCE},
        )
    for model, key in sorted({(m, k) for m, k, _ in touched}):
        s.execute(text("DELETE FROM canonical WHERE model = :m AND key = :k AND data = '{}'::jsonb"), {"m": model, "k": key})
    s.execute(
        text("DELETE FROM raw_record WHERE source_id = :s AND resource = :r AND ext_id LIKE :l"),
        {"s": SOURCE, "r": RESOURCE, "l": like},
    )
    s.execute(
        text("DELETE FROM failed_record WHERE run_kind = 'import' AND (CAST(:i AS text) IS NULL OR run_id = :i)"),
        {"i": import_id},
    )
    return len(touched)
