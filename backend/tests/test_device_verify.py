"""Plan 9, P9-6.5 (story DV-02): verify the device against the quote.

The lab's diagnostics (IMEI, model and storage read) are compared with what the trade-in quoted. A mismatch opens one
`quote_mismatch` exception (owner "Customer care", role Planner) that names both values, and every channel of the case holds
(GR-D13, the gate G-DEV-QUOTE) until a person resolves the exception. No diagnostics: no exception, the case waits. The
comparison is computed, so nothing here runs on a model (R16): the text is fixed wording over the two values read.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import store
from di.services.device import intake as device_intake
from di.services.device import verify
from di.services.device.verify import Mismatch, compare_quote
from di.services.modeler.pack import load_pack
from tests import starting
from tests.device_registry import seed_registry
from tests.helpers import call, client, h

ORG = "Customer A"
IMEI = "359990000000428"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM device_tradein"))
        conn.execute(text("DELETE FROM device_price_point"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _land(storage: int = 128, model: str = "iPhone 14") -> None:
    when = (clock.now() - timedelta(days=5)).isoformat()
    doc = {
        "tradeInId": "TI-00428", "imei": IMEI,
        "sku": {"brand": "Apple", "model": model, "storageGb": storage, "colour": "Blue", "carrierLock": "unlocked"},
        "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
        "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": when, "payoutAmount": 410,
    }  # fmt: skip
    with SessionLocal() as s:
        lab.land_tradein(s, doc, ORG)
        s.commit()
    seed_registry(IMEI)  # a received device with no registry check is held (P9-6.6): this one has a clear one


def _read(**read) -> None:
    """The lab's diagnostics of the device, as the adapter maps them."""
    base = {"imei_read": IMEI, "model_read": "iPhone 14", "storage_read_gb": 128} | read
    with SessionLocal() as s:
        canonical.apply(s, "dvlab", [Fact("condition", "IMEI:" + IMEI, k, v) for k, v in base.items()])
        s.commit()


def _open() -> dict:
    with SessionLocal() as s:
        (cid,) = device_intake.open_pending(s, ORG)
        s.commit()
        c = store.get(s, cid)
    assert c is not None
    return c


def _items(cid: str) -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, status, owner_role, title, cause, action FROM work_item "
                 "WHERE case_id = :c AND type = 'quote_mismatch' "
                 "ORDER BY id"), {"c": cid},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


# ---------------------------------------------------------------- the comparison (pure)
def test_dv_02_compare_quote_lists_each_difference():
    quote = {"imei": IMEI, "model": "iPhone 14", "storage_gb": 256}
    read = {"imei_read": IMEI[:-1] + "9", "model_read": "iphone 13 ", "storage_read_gb": 128}
    got = compare_quote(quote, read)
    assert got == [
        Mismatch("imei", IMEI, IMEI[:-1] + "9"),
        Mismatch("model", "iPhone 14", "iphone 13"),
        Mismatch("storage", 256, 128),
    ]
    assert [verify.mismatch_line(m) for m in got][2] == "Storage quoted 256 GB, read 128 GB"
    assert verify.mismatch_line(got[1]) == "Model quoted iPhone 14, read iphone 13"
    assert compare_quote(quote, {"imei_read": IMEI, "model_read": " IPHONE 14", "storage_read_gb": 256.0}) == []
    assert compare_quote(quote, {"imei_read": IMEI}) == []  # a field the lab did not read is not a mismatch


# ---------------------------------------------------------------- the case
def test_dv_02_mismatch_opens_exception_with_both_values():
    _land(storage=256)
    _read(storage_read_gb=128)
    c = _open()
    line = "Storage quoted 256 GB, read 128 GB"
    (item,) = _items(c["id"])
    assert item["status"] == "open" and item["owner_role"] == "Planner"
    assert line in item["title"] and line in item["cause"] and "Customer care" in item["action"]
    assert c["routes"] and all(r["excluded"] and r["failReason"] == f"Quote match: {line}" for r in c["routes"])
    assert c["recommendation"] is None and c["stage"] == "none"
    g = next(x for x in c["gates"] if x["id"] == "G-DEV-QUOTE")
    assert (g["id"], g["type"], g["passed"], g["owner"]) == ("G-DEV-QUOTE", "Data quality", False, "Customer care")
    rec = load_pack("device")
    assert next(x for x in rec.guardrails if x.id == "GR-D13").type == "Data quality"
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    qc = r.json()["case"]["device"]["quoteCheck"]
    assert qc["state"] == "mismatch" and qc["owner"] == "Customer care" and qc["item"]["state"] == "open"
    assert qc["rows"][-1] == {"field": "storage", "quoted": 256, "read": 128, "mismatch": True}


def test_dv_02_one_item_however_often_the_case_is_valued():
    _land(storage=256)
    _read(storage_read_gb=128)
    c = _open()
    from di.services.cases import intake

    for _ in range(2):
        with SessionLocal() as s:
            d = store.get(s, c["id"], for_update=True)
            intake.revalue(s, d)
            store.save(s, d)
            s.commit()
    assert len(_items(c["id"])) == 1


def test_dv_02_match_passes():
    _land()
    _read()
    c = _open()
    assert _items(c["id"]) == []
    assert any(not r["excluded"] for r in c["routes"]) and c["recommendation"] is not None
    assert c["valuer"]["inputs"]["comparison"]["state"] == "match"


def test_dv_02_no_diagnostics_waits():
    _land()
    c = _open()
    assert _items(c["id"]) == []
    assert c["valuer"]["inputs"]["comparison"]["state"] == "waiting"
    assert c["recommendation"] is not None  # nothing is held on evidence that has not come


def test_dv_02_a_person_resolves_it_and_the_channels_release():
    _land(storage=256)
    _read(storage_read_gb=128)
    c = _open()
    (item,) = _items(c["id"])
    # an agent may not resolve it (golden rule 10)
    assert forbidden("work.resolve")
    ok = call("work.resolve", {"item_id": item["id"], "outcome": "Re-quote accepted"}, "planner.a")
    assert ok.get("ok") is not False, ok
    got = _get(c["id"])
    assert any(not r["excluded"] for r in got["routes"]) and got["stage"] == "awaiting_approval"
    assert next(x for x in got["gates"] if x["id"] == "G-DEV-QUOTE")["passed"] is True and _items(c["id"])[0]["status"] == "done"
    assert len(_items(c["id"])) == 1  # resolved: not opened again


def test_dv_02_returning_the_trade_in_keeps_the_channels_held():
    _land(storage=256)
    _read(storage_read_gb=128)
    c = _open()
    (item,) = _items(c["id"])
    call("work.resolve", {"item_id": item["id"], "outcome": "Trade-in returned"}, "planner.a")
    got = _get(c["id"])
    assert all(r["excluded"] for r in got["routes"]) and got["recommendation"] is None


def test_dv_02_a_po_lot_has_no_quote_gate():
    from di.services.cases import intake

    lot = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
    with SessionLocal() as s:
        c = intake.open_case(s, {"org_unit_id": ORG, "template_key": "device", "asset_key": "LOT-Q1", "reason": "manual",
                                 "facts": lot}, "admin")  # fmt: skip
        s.commit()
    assert "gates" not in c and c["recommendation"] is not None
