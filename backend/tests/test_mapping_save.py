"""Plan 9 P9-0.10 (G 6 item 8, G 2.8): mapping.save, the Data Mapping tab's save split out of source.update.

- a person with manageIntegrations saves rows: a new mapping version, the audit entry, and the next sync applies them
- unchanged rows are a conflict ("No changes to save."); a bad target keeps _check_maps' message
- an agent (autonomy act) only proposes it (HELD_FOR_PERSON); a person accepts the proposal and then it runs
- source.update with `maps` keeps working
"""

import pytest
from sqlalchemy import text

from di.connectors import mapping
from di.connectors.sync import ensure_sources, run_sync
from di.core.db import SessionLocal
from tests import starting
from tests.helpers import call, client, h

SID = "insp"
AGENT = "coordinator"  # seeded, autonomy act


@pytest.fixture(autouse=True)
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
            s.execute(text("DELETE FROM agent_proposal"))
            s.commit()

    starting.reset()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = :i"), {"i": SID})
        s.commit()
    clean()
    yield
    clean()
    starting.reset()


def _edited() -> list[list[str]]:
    rows = [list(m) for m in mapping.starting_maps(SID)]
    rows[0][4] = "code:grade"
    rows.append(["audit_data.status", "", "condition.inspection_status", "", "upper"])
    return rows


def _version() -> int | None:
    with SessionLocal() as s:
        return mapping.active_version(s, SID)


def test_mapping_save_new_version():
    """P9-0.10: a person saves rows; the active version rises by 1 and the next sync applies them."""
    assert run_sync(SID, "manual", full=True)["status"] == "ok"
    with SessionLocal() as s:
        assert mapping.save_version(s, SID, mapping.starting_maps(SID), "test") == 1
        s.commit()
    maps = _edited()
    r = call("mapping.save", {"source_id": SID, "maps": maps, "note": "two rows"}, "developer")
    assert r["ok"], r
    out = r["output"]
    assert out["source_id"] == SID and out["version"] == 2 and out["rows"] == len(maps) and out["ver"]
    assert _version() == 2
    with SessionLocal() as s:
        assert mapping.active_rows(s, SID) == mapping.to_rows(mapping.rows_from_maps(SID, maps))
    src = client.get(f"/api/screens/integration/sources/{SID}", headers=h("developer")).json()["source"]
    assert src["cfgVer"] == out["ver"] and "Field mapping saved" in src["audit"][0]["change"]
    ev = client.get("/api/screens/integration/events", headers=h("developer")).json()["events"]
    assert any(e["type"] == "connector.updated" and "field mapping saved" in (e.get("note") or "") for e in ev)
    run = run_sync(SID, "manual", full=True)
    assert run["status"] == "ok" and run["records_failed"] == 0, run


def test_mapping_save_unchanged_conflict():
    maps = _edited()
    assert call("mapping.save", {"source_id": SID, "maps": maps}, "developer")["ok"]
    v = _version()
    r = call("mapping.save", {"source_id": SID, "maps": maps}, "developer")
    assert r["ok"] is False and r["error"] == {"code": "conflict", "message": "No changes to save."}, r
    assert _version() == v


def test_mapping_save_bad_target_refused():
    bad = [["a", "", "widget.x", "", "copy"]]
    with pytest.raises(ValueError, match=r".") as e:
        mapping.rows_from_maps(SID, bad)
    r = call("mapping.save", {"source_id": SID, "maps": bad}, "developer")
    assert r["ok"] is False and r["error"]["code"] == "validation_error", r
    assert r["error"]["message"] == str(e.value)
    assert _version() is None
    assert call("mapping.save", {"source_id": SID, "maps": _edited()}, "engineer")["ok"] is False  # no manageIntegrations


def test_mapping_save_agent_held_then_accepted():
    hdr = h("developer") | {"X-Circularity-Preparer": AGENT}
    r = client.post("/api/actions/mapping.save", json={"source_id": SID, "maps": _edited()}, headers=hdr).json()
    assert r["ok"] is True and set(r["output"]) == {"held"}, r
    assert _version() is None  # nothing was saved
    pid = r["output"]["held"]
    acc = call("proposal.accept", {"id": pid}, "admin")
    assert acc["ok"] is True, acc
    assert _version() == 2  # the first save of a demo source records its default mapping as v1
    with SessionLocal() as s:
        assert mapping.active_rows(s, SID) == mapping.to_rows(mapping.rows_from_maps(SID, _edited()))


def test_source_update_with_maps_still_works():
    c = client.get(f"/api/screens/integration/sources/{SID}", headers=h("developer")).json()["source"]
    d = {k: c.get(k) for k in ("name", "vendor", "ver", "env", "url", "method", "cfg", "auth", "owner", "interval")}
    d["type"] = c["type"]
    r = call(
        "source.update",
        {"mode": "edit", "id": SID, "d": d, "ops": {"read": c["read"], "write": c["write"]}, "maps": _edited()},
        "developer",
    )
    assert r["ok"] and any(x.startswith("field mapping") for x in r["output"]["changes"]), r
    assert _version() == 2
