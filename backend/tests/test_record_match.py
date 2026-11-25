"""P9-1.10 (X-08): match a returned asset to the system of record, with exceptions. A case whose asset the pack's system of
record does not hold opens one `not_in_system_of_record` item and is valued anyway (mode "exception"); the record landing
on a sync clears it; a unit the system expects back that has no case after `missing_after_days` is an
`expected_return_missing` item; custody is kept, append-only. The chain of custody is a record the platform keeps, not a
legal claim: Kinective's Legal team reviews any such use. Every test ends with the starting state."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.core import clock
from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import intake, record_match, store
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import client, h

KEYS = ("TF-NOPE-1", "TF-MISS-1", "TF-MOVE-1", "DV-NOPE-1")
FACTS = {"cls": "CMH", "grade": "C", "ft": "Repair center", "site": "Houston", "rul": 62}


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM canonical WHERE model = 'asset' AND key = ANY(:k)"), {"k": list(KEYS)})
        s.execute(text("DELETE FROM provenance WHERE model = 'asset' AND key = ANY(:k)"), {"k": list(KEYS)})
        s.execute(text("DELETE FROM work_item"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    starting.reset()
    yield
    _clean()
    starting.reset()


def _open(asset: str, template: str = "tool_fleet", facts: dict[str, Any] | None = None) -> str:
    body = {"org_unit_id": "Customer A", "template_key": template, "asset_key": asset, "reason": "manual",
            "facts": FACTS if facts is None else facts}  # fmt: skip
    with SessionLocal() as s:
        c = intake.open_case(s, body, "planner.a")
        s.commit()
    return str(c["id"])


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _items(type: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT * FROM work_item WHERE type = :t ORDER BY id"), {"t": type}).mappings()
        return [dict(r) for r in rows]


def _land(source: str, key: str, **fields: Any) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, [Fact("asset", key, f, v) for f, v in fields.items()])
        s.commit()


def _sync_job(source: str) -> None:
    worker.HANDLERS["case.recordMatch"]({"source_id": source})


def _system(source: str) -> str:
    with SessionLocal() as s:
        return str(s.execute(text("SELECT vendor FROM source_system WHERE id = :i"), {"i": source}).scalar())


def test_the_packs_say_where_the_system_of_record_is():
    assert load_pack("tool_fleet").data.record_match == {
        "source_type": "lease", "field": "asset.lease_ref", "mode": "exception", "missing_after_days": 2,
    }  # fmt: skip
    assert load_pack("device").data.record_match == {
        "source_type": "rl", "field": "asset.return_ref", "mode": "exception", "missing_after_days": 2,
    }  # fmt: skip
    for key in ("tool_fleet", "device"):
        types = {t.id: t for t in load_pack(key).runtime.exception_types}
        assert {"not_in_system_of_record", "expected_return_missing"} <= set(types)
        assert types["not_in_system_of_record"].owner_role == "Planner"


def test_x_08_unknown_serial_opens_exception():
    cid = _open("TF-NOPE-1")
    (item,) = _items("not_in_system_of_record")
    assert item["case_id"] == cid and item["kind"] == "exception" and item["status"] == "open"
    assert item["owner_role"] == "Planner" and item["org_unit_id"] == "Customer A"
    assert item["action"] == f"Check the serial in {_system('lease')}, or correct the asset key"
    assert item["due_at"] is not None  # the pack's `exception` SLA
    c = _case(cid)
    assert c["recommendation"] is not None  # mode "exception": valuation goes on
    assert c["recordMatch"]["found"] is False and c["recordMatch"]["since"]
    assert c["recordMatch"]["source"] == _system("lease")


def test_x_08_one_item_however_often_it_is_checked():
    cid = _open("TF-NOPE-1")
    for _ in range(2):
        with SessionLocal() as s:
            c = store.get(s, cid, for_update=True)
            assert c is not None
            intake.revalue(s, c)
            store.save(s, c)
            s.commit()
    assert len(_items("not_in_system_of_record")) == 1
    since = _case(cid)["recordMatch"]["since"]
    _sync_job("lease")  # still not there
    assert _case(cid)["recordMatch"]["since"] == since and len(_items("not_in_system_of_record")) == 1


def test_x_08_reconcile_lists_the_received_but_unknown():
    cid = _open("TF-NOPE-1")
    with SessionLocal() as s:
        rep = record_match.reconcile(s, "lease")
        s.commit()
    assert rep.extra == [cid] and rep.matched == [] and rep.missing == []


def test_x_08_found_on_next_sync_clears():
    cid = _open("TF-NOPE-1")
    _land("lease", "TF-NOPE-1", lease_ref="LS-7001", owner_tenant="Customer A")
    with SessionLocal() as s:
        rep = record_match.reconcile(s, "lease")
        s.commit()
    assert rep.matched == [cid] and rep.extra == []
    (item,) = _items("not_in_system_of_record")
    assert item["status"] == "done" and item["outcome"] == f"Found in {_system('lease')}"
    c = _case(cid)
    assert c["recordMatch"]["found"] is True and c["recordMatch"]["key"] == "LS-7001"
    assert [e["event"] for e in c["custody"]] == ["received", "matched"]


def test_x_08_the_sync_job_does_the_same():
    cid = _open("TF-NOPE-1")
    _land("lease", "TF-NOPE-1", lease_ref="LS-7001", owner_tenant="Customer A")
    _sync_job("lease")
    assert _items("not_in_system_of_record")[0]["status"] == "done"
    assert _case(cid)["custody"][-1]["event"] == "matched"


def test_x_08_a_record_of_another_owner_is_not_a_match():
    cid = _open("TF-NOPE-1")
    _land("lease", "TF-NOPE-1", lease_ref="LS-7001", owner_tenant="Customer B")
    _sync_job("lease")
    assert _case(cid)["recordMatch"]["found"] is False and _items("not_in_system_of_record")[0]["status"] == "open"


def test_x_08_a_record_from_another_source_is_not_a_match():
    cid = _open("TF-NOPE-1")
    _land("eam", "TF-NOPE-1", lease_ref="LS-7001")
    _sync_job("lease")
    assert _case(cid)["recordMatch"]["found"] is False


def test_x_08_found_at_open_opens_nothing():
    _land("lease", "TF-NOPE-1", lease_ref="LS-7001", owner_tenant="Customer A")
    cid = _open("TF-NOPE-1")
    c = _case(cid)
    assert c["recordMatch"]["found"] is True and _items("not_in_system_of_record") == []
    assert [e["event"] for e in c["custody"]] == ["received"]  # found at once: nothing to match later


def test_x_08_missing_unit_caught(monkeypatch: pytest.MonkeyPatch):
    start = clock.now()
    _land("lease", "TF-MISS-1", lease_ref="LS-7002", owner_tenant="Customer A", disposition="returned",
          received_at=start.isoformat())  # fmt: skip
    monkeypatch.setattr(clock, "now", lambda: start + timedelta(days=1))
    with SessionLocal() as s:
        assert record_match.reconcile(s, "lease").missing == []  # not yet: the pack waits two days
        s.commit()
    assert _items("expected_return_missing") == []
    monkeypatch.setattr(clock, "now", lambda: start + timedelta(days=3))
    for _ in range(2):  # a second sync opens no second item
        with SessionLocal() as s:
            rep = record_match.reconcile(s, "lease")
            s.commit()
        assert rep.missing == ["TF-MISS-1"]
    (item,) = _items("expected_return_missing")
    assert "TF-MISS-1" in item["title"] and item["org_unit_id"] == "Customer A" and item["status"] == "open"
    assert item["case_id"] is None and item["owner_role"] == "Planner"


def test_x_08_a_unit_with_a_case_is_not_missing(monkeypatch: pytest.MonkeyPatch):
    start = clock.now()
    _land("lease", "TF-MISS-1", lease_ref="LS-7002", owner_tenant="Customer A", disposition="in_transit",
          received_at=start.isoformat())  # fmt: skip
    monkeypatch.setattr(clock, "now", lambda: start + timedelta(days=3))
    with SessionLocal() as s:
        record_match.reconcile(s, "lease")
        s.commit()
    assert len(_items("expected_return_missing")) == 1
    _open("TF-MISS-1")  # the unit arrived and a case was opened for it
    with SessionLocal() as s:
        assert record_match.reconcile(s, "lease").missing == []
        s.commit()
    assert _items("expected_return_missing")[0]["status"] == "done"


def test_x_08_custody_kept():
    _land("wms", "TF-MOVE-1", location="Warehouse 1")
    cid = _open("TF-MOVE-1")
    _land("wms", "TF-MOVE-1", location="Warehouse 2")
    for _ in range(2):  # a move, then a revalue: the revalue drops nothing and adds nothing
        with SessionLocal() as s:
            c = store.get(s, cid, for_update=True)
            assert c is not None
            intake.revalue(s, c)
            store.save(s, c)
            s.commit()
    custody = _case(cid)["custody"]
    assert [e["event"] for e in custody] == ["received", "moved"]
    assert custody[0]["location"] == "Warehouse 1" and custody[1]["location"] == "Warehouse 2"
    assert all({"at", "event", "source", "location", "by"} <= set(e) for e in custody)


def test_x_08_device_lots_match_on_the_return_receipt():
    lot = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
    cid = _open("DV-NOPE-1", "device", lot)
    (item,) = _items("not_in_system_of_record")
    assert item["case_id"] == cid and item["action"].startswith(f"Check the serial in {_system('rl')}")
    _land("rl", "DV-NOPE-1", return_ref="RET-9", owner_tenant="Customer A")
    _sync_job("rl")
    assert _case(cid)["recordMatch"]["found"] is True


def test_x_08_hold_mode_leaves_no_recommendation_until_found():
    pack = load_pack("tool_fleet")
    held = pack.model_copy(update={"data": pack.data.model_copy(update={"record_match": {
        **(pack.data.record_match or {}), "mode": "hold"}})})  # fmt: skip
    cid = _open("TF-NOPE-1")
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None and c["recommendation"] is not None
        record_match.check(s, c, held)
        assert c["recommendation"] is None
        s.rollback()


def test_x_08_the_case_page_shows_the_match_and_custody():
    cid = _open("TF-NOPE-1")
    page = client.get(f"/api/screens/case/{cid}", headers=h("planner-a")).json()
    rm = page["recordMatch"]
    assert rm["found"] is False and rm["system"] == _system("lease") and rm["owner"] == "Planner"
    assert [e["event"] for e in page["custody"]] == ["received"]
    _land("lease", "TF-NOPE-1", lease_ref="LS-7001", owner_tenant="Customer A")
    _sync_job("lease")
    rm = client.get(f"/api/screens/case/{cid}", headers=h("planner-a")).json()["recordMatch"]
    assert rm["found"] is True and rm["key"] == "LS-7001" and rm["syncedMinutesAgo"] >= 0


def test_industrial_has_no_record_match():
    assert load_pack("industrial").data.record_match is None
    page = client.get("/api/screens/case/RT-1048", headers=h("planner-a")).json()
    assert page["recordMatch"] is None and page["custody"] == []
    assert "recordMatch" not in page["case"] and "custody" not in page["case"]
