"""Plan 6 B2: conflicts that stay resolved.

A person's resolution sticks while the sources keep sending the values it was made on (conflict.values_hash); a
changed value opens a new conflict. conflict.resolve keeps the authority's value (the demo's), another source's value
or a value a person enters, with a reason (the last two write a provenance row from source `manual`); escalation is
stored as status 'escalated' and stays in the queue. Uses its own keys (CFT-*), removed afterwards.
"""

from sqlalchemy import text

from di.canonical import store
from di.canonical.store import Fact
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()
    _clean()


def teardown_module():
    _clean()
    starting.reset()


def _clean():
    with engine.begin() as conn:
        for t in ("conflict", "provenance", "canonical"):
            conn.execute(text(f"DELETE FROM {t} WHERE key LIKE 'CFT-%'"))  # noqa: S608 - fixed table names


def sync(key: str, erp: float, proc: float) -> None:
    """What two syncs do: S/4HANA (authority over the purchase baseline) and Ariba send their values."""
    with SessionLocal() as s:
        store.apply(s, "erp", [Fact("demand", key, "purchase_baseline", erp)], 97)
        store.apply(s, "proc", [Fact("demand", key, "purchase_baseline", proc)], 90)
        s.commit()


def conflicts(key: str) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT * FROM conflict WHERE key = :k ORDER BY id"), {"k": key}).mappings()]


def active(key: str) -> list[dict]:
    return [c for c in conflicts(key) if c["status"] in ("open", "escalated")]


def value(key: str):
    with SessionLocal() as s:
        return store.get(s, "demand", key)["data"]["purchase_baseline"]


def manual_row(key: str):
    with SessionLocal() as s:
        return s.execute(text("SELECT * FROM provenance WHERE key = :k AND source_id = 'manual'"), {"k": key}).mappings().first()


def queue_row(cid: str) -> dict:
    rows = client.get("/api/screens/integration/conflicts", params={"status": "all", "limit": 5000}, headers=h("admin")).json()
    return next(c for c in rows["conflicts"] if c["id"] == cid)


def test_resolution_sticks_until_values_change():
    sync("CFT-1", 12000.0, 15000.0)
    [c] = active("CFT-1")
    assert c["values_hash"]
    r = call(
        "conflict.resolve", {"id": f"CF-{c['id']}", "choose": "authority", "reason": "S/4HANA is the book of record"}, "developer"
    )
    assert r["ok"] and r["output"]["kept"] == "erp", r
    sync("CFT-1", 12000.0, 15000.0)  # the next sync, same values: it stays resolved
    sync("CFT-1", 12000.0, 15000.0)
    assert [x["status"] for x in conflicts("CFT-1")] == ["resolved"] and value("CFT-1") == 12000.0
    sync("CFT-1", 12000.0, 15500.0)  # one value changes: a new conflict opens
    assert [x["status"] for x in conflicts("CFT-1")] == ["resolved", "open"]


def test_choosing_the_other_value_changes_canonical_and_releases_the_routes():
    sync("CFT-2", 12000.0, 15000.0)
    [c] = active("CFT-2")
    cid = f"CF-{c['id']}"
    assert (
        call("conflict.resolve", {"id": cid, "choose": "other"}, "developer")["error"]["code"] == "validation_error"
    )  # no reason
    r = call("conflict.resolve", {"id": cid, "choose": "other", "reason": "The PO was amended in Ariba"}, "developer")
    assert r["ok"] and r["output"]["kept"] == "proc" and r["output"]["value"] == 15000.0, r
    assert value("CFT-2") == 15000.0 and active("CFT-2") == []  # nothing holds the routes on CFT-2 any more
    m = manual_row("CFT-2")
    assert m["value"] == 15000.0 and m["resource"] == "conflict" and "The PO was amended in Ariba" in m["transform"]
    assert queue_row(cid)["status"] == "resolved"
    with SessionLocal() as s:
        prov = store.get(s, "demand", "CFT-2")["provenance"]["purchase_baseline"]
    assert {p["source_id"] for p in prov} == {"erp", "proc", "manual"}
    sync("CFT-2", 12000.0, 15000.0)  # the choice holds through the next sync
    assert value("CFT-2") == 15000.0 and active("CFT-2") == []
    sync("CFT-2", 12500.0, 15000.0)  # the authority's value changes: a new conflict, the authority counts again
    assert value("CFT-2") == 12500.0 and len(active("CFT-2")) == 1 and manual_row("CFT-2") is None


def test_entering_a_value():
    sync("CFT-3", 12000.0, 15000.0)
    cid = f"CF-{active('CFT-3')[0]['id']}"
    bad = call("conflict.resolve", {"id": cid, "choose": "value", "value": "a lot", "reason": "Agreed"}, "developer")
    assert bad["error"]["code"] == "validation_error" and "must be a number" in bad["error"]["message"]
    assert call("conflict.resolve", {"id": cid, "choose": "maybe"}, "developer")["error"]["code"] == "validation_error"
    r = call(
        "conflict.resolve", {"id": cid, "choose": "value", "value": "13,500", "reason": "Agreed with the supplier"}, "developer"
    )
    assert r["ok"] and r["output"]["kept"] == "manual" and r["output"]["value"] == 13500.0, r
    assert value("CFT-3") == 13500.0
    ev = client.get("/api/screens/integration/events", headers=h("admin")).json()["events"][0]
    assert ev["type"] == "conflict.resolved" and ev["note"].startswith(
        "Purchase baseline conflict on CFT-3 resolved with a value"
    )
    sync("CFT-3", 12000.0, 15000.0)
    assert value("CFT-3") == 13500.0
    assert client.post("/api/actions/conflict.resolve", json={"id": cid}, headers=h("planner.a")).status_code == 403


def test_escalated_is_stored_and_stays_in_the_queue():
    sync("CFT-4", 12000.0, 15000.0)
    cid = f"CF-{active('CFT-4')[0]['id']}"
    r = call("conflict.escalate", {"id": cid}, "developer")
    assert r["ok"], r
    assert [x["status"] for x in conflicts("CFT-4")] == ["escalated"]
    q = queue_row(cid)
    assert q["status"] == "open" and q["escalated"]["by"] and q["escalated"]["to"]  # shown open, with the data owner
    sync("CFT-4", 12000.0, 16000.0)  # a sync updates the escalated conflict, it does not open a second one
    [c] = conflicts("CFT-4")
    assert c["status"] == "escalated" and c["values"]["proc"] == 16000.0
    r = call("conflict.resolve", {"id": cid}, "developer")
    assert r["ok"] and [x["status"] for x in conflicts("CFT-4")] == ["resolved"]
    sync("CFT-4", 12000.0, 16000.0)
    assert [x["status"] for x in conflicts("CFT-4")] == ["resolved"]


def test_agreement_closes_an_escalated_conflict():
    sync("CFT-5", 12000.0, 15000.0)
    cid = f"CF-{active('CFT-5')[0]['id']}"
    assert call("conflict.escalate", {"id": cid}, "developer")["ok"]
    sync("CFT-5", 12000.0, 12000.0)
    [c] = conflicts("CFT-5")
    assert c["status"] == "resolved" and c["closed_by"] == "system"
