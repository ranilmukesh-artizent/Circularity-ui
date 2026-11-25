"""Plan 9, P9-6.4 (story DV-01): one case per received device.

A trade-in the device lab landed (`device_tradein`) opens one case per IMEI (`asset_key` `IMEI:<imei>`, quantity 1, the
reference value from the market feed at the as-of date, else the quote), or, for a bulk batch, one lot case with a line per
device. The lab adapter's hook opens them in the sync's own session, so a dry run writes nothing. A PO lot keeps its four
channels and its numbers (`channels_for`). Needs no source-sim: the rows are landed by literal records.
"""

import dataclasses
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories import device_tradeins
from di.services.actions.registry import ActionError
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import store
from di.services.device import inputs
from di.services.device import intake as device_intake
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import device
from tests import starting
from tests.device_registry import seed_registry

ORG = "Customer A"
IMEI = "359990000000428"
TABLES = ("device_tradein", "device_price_point")


def _today():
    return clock.now().date()


def _doc(n: int = 428, **kw) -> dict:
    when = (clock.now() - timedelta(days=5)).isoformat()
    d = {
        "tradeInId": f"TI-{n:05d}", "imei": IMEI if n == 428 else f"35999000{n:07d}",
        "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
        "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
        "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": when, "payoutAmount": 410,
    }  # fmt: skip
    return d | kw


def _land(*docs: dict, org: str | None = ORG) -> None:
    with SessionLocal() as s:
        for d in docs:
            lab.land_tradein(s, d, org)
        s.commit()
    for d in docs:  # a received device with no registry check is held (P9-6.6): these cases have a clear one
        seed_registry(d["imei"])


def _price(grade: str, price: float, days_ago: int = 3, sku: str = "iPhone 14|128") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                "VALUES (:k, :g, :w, :p, 'USD', 'dvmkt') ON CONFLICT DO NOTHING"
            ),
            {"k": sku, "g": grade, "w": _today() - timedelta(days=days_ago), "p": price},
        )


def _open_pending() -> list[str]:
    with SessionLocal() as s:
        ids = device_intake.open_pending(s, ORG)
        s.commit()
    return ids


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = 'dvlab' AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def test_dv_01_one_case_per_imei():
    _price("B", 330)
    _land(_doc())
    (cid,) = _open_pending()
    c = _case(cid)
    assert c["assetId"] == "IMEI:" + IMEI and c["template"] == "device" and c["qty"] == 1
    assert c["intake"]["reason"] == "trade_in" and c["owner"] == ORG
    v = c["valuer"]
    assert v["imei"] == IMEI and v["sku_key"] == "iPhone 14|128" and v["ref"] == 330 and v["grade"] == "B"
    assert v["ref_source"] == "feed" and v["band"] == "25-48m" and v["inputs"]["feed_price"] == 330
    assert [r["id"] for r in c["routes"]] == ["buynow", "offers", "auction"]  # the Recover channels (pack list)
    assert c["recommendation"] is not None
    with SessionLocal() as s:
        assert device_tradeins.by_imei(s, IMEI).case_id == cid and device_tradeins.pending(s, ORG) == []


def test_dv_01_no_feed_price_falls_back_to_the_quote():
    _land(_doc())
    (cid,) = _open_pending()
    v = _case(cid)["valuer"]
    assert v["ref"] == 410 and v["ref_source"] == "quote" and v["inputs"]["feed_price"] is None


def test_dv_01_the_graded_cosmetic_grade_beats_the_declared_one():
    _price("B", 330)
    _price("C", 250)
    _land(_doc())
    with SessionLocal() as s:  # the lab's grading, as the adapter maps it
        canonical.apply(s, "dvlab", [Fact("condition", "IMEI:" + IMEI, "cosmetic_grade", "C", "cosmeticGrade", "C", "x")])
        s.commit()
    (cid,) = _open_pending()
    v = _case(cid)["valuer"]
    assert v["grade"] == "C" and v["graded"] is True and v["ref"] == 250


def test_dv_01_device_case_fields():
    t = device_tradeins.TradeInRow(
        "TI-1",
        ORG,
        IMEI,
        _doc()["sku"],
        _doc()["quote"],
        "P01",
        "BATCH-0011",
        False,
        clock.now() - timedelta(days=5),
        None,
        None,
        "dvlab",
    )
    c = device_intake.device_case(
        "RT-9", t, {"as_of": clock.now().isoformat(), "feed_price": 330.0, "feed_week": "2026-10-01", "feed_stale": False}
    )
    assert (c["imei"], c["sku_key"], c["brand"], c["model"], c["storage_gb"], c["band"]) == (
        IMEI, "iPhone 14|128", "Apple", "iPhone 14", 128, "25-48m",
    )  # fmt: skip
    assert (c["grade"], c["graded"], c["ref"], c["ref_source"], c["qty"], c["doh"]) == ("B", False, 330.0, "feed", 1, 5)
    assert c["partner"] == "P01" and c["batch_id"] == "BATCH-0011" and c["quote"]["amount"] == 410
    unknown = dataclasses.replace(t, sku={"brand": "Nokia", "model": "3310", "storageGb": 1})
    with pytest.raises(ActionError) as e:
        device_intake.device_case("RT-9", unknown, {"as_of": clock.now().isoformat()})
    assert e.value.code == "validation_error"


def test_dv_01_bulk_lot_with_lines():
    _price("B", 330)
    quote = _doc()["quote"]
    docs = [
        _doc(n, bulk=True, batchId="BATCH-0020", quote=quote | {"declaredGrade": "B" if n % 4 else "C"}) for n in range(100, 120)
    ]
    _land(*docs)
    (cid,) = _open_pending()
    c = _case(cid)
    v = c["valuer"]
    assert c["assetId"] == "BATCH-0020" and c["qty"] == 20 and len(v["lines"]) == 20 and "imei" not in v
    assert v["grade"] == "B" and v["lines"][0]["imei"] == "35999000" + "0000100"
    assert [r["id"] for r in c["routes"]] == ["buynow", "offers", "auction", "market"]  # a PO-shaped lot: four channels
    with SessionLocal() as s:
        assert {r.case_id for r in [device_tradeins.by_imei(s, x["imei"]) for x in docs]} == {cid}


def test_dv_01_duplicate_refused():
    _land(_doc())
    (cid,) = _open_pending()
    with SessionLocal() as s:
        row = device_tradeins.by_imei(s, IMEI)
        assert row is not None
        s.execute(text("UPDATE device_tradein SET case_id = NULL"))
        row = device_tradeins.by_imei(s, IMEI)
        with pytest.raises(ActionError) as e:
            device_intake.open_from_tradein(s, row, "system")
        assert e.value.code == "duplicate" and cid in e.value.message
        s.rollback()


def test_dv_01_a_second_pass_opens_nothing():
    _land(_doc())
    assert len(_open_pending()) == 1 and _open_pending() == []


def test_dv_01_a_row_without_an_org_or_a_known_model_stays_pending():
    _land(_doc(1), org=None)
    _land(_doc(2, sku={"brand": "Nokia", "model": "3310", "storageGb": 1}))
    assert _open_pending() == []
    with SessionLocal() as s:
        assert len(device_tradeins.pending(s, ORG)) == 2


def test_dv_01_the_hook_opens_in_the_sync_session_and_a_dry_run_writes_nothing(monkeypatch):
    _land(_doc())
    adapter = lab.ADAPTER
    monkeypatch.setattr(adapter, "flat", lambda *a, **k: iter(()))
    with SessionLocal() as s:
        client = SimpleNamespace(session=s, source_id="dvlab")
        list(adapter.read("disputes", "/disputes", "disputeId")(client, None))  # the last resource: the hook
        assert (
            len(device_tradeins.pending(s, ORG)) == 0
            and s.execute(
                text("SELECT count(*) FROM case_record WHERE data->'intake'->>'key' = :k"), {"k": f"IMEI:{IMEI}:trade_in"}
            ).scalar()
            == 1
        )
        s.rollback()  # a dry run
    with SessionLocal() as s:
        assert len(device_tradeins.pending(s, ORG)) == 1
        assert (
            s.execute(
                text("SELECT count(*) FROM case_record WHERE data->'intake'->>'key' = :k"), {"k": f"IMEI:{IMEI}:trade_in"}
            ).scalar()
            == 0
        )


def test_device_po_lots_unchanged():
    for lot in device.sample_lots():
        assert device.channels_for(lot) == device.DCH
        d = device.decide(lot)
        assert [v["k"] for v in d["all"]] == ["buynow", "offers", "auction", "market"] and d["best"] is not None
    assert device.channels_for({"imei": IMEI}) == load_pack("device").valuer.params["recover_channels"]
    assert "wholesale" not in device.DCH


def test_decide_scores_only_the_channels_of_the_lot():
    lot = device.sample_lots()[0] | {"imei": IMEI}
    d = device.decide(lot)
    assert [v["k"] for v in d["all"]] == device.channels_for(lot) and len(d["all"]) == 3


def test_dv_01_gather_reads_the_feed_and_the_evidence_as_of():
    _price("B", 330, days_ago=3)
    _price("B", 999, days_ago=-3)  # next week: never read
    _price("B", 300, days_ago=40, sku="iPhone 14|128")
    with SessionLocal() as s:
        g = inputs.gather(s, {"imei": IMEI, "sku_key": "iPhone 14|128", "grade": "B"}, _today())
    assert g.feed_price == 330 and g.feed_week == str(_today() - timedelta(days=3)) and g.feed_stale is False
    assert set(g.evidence) == {"quote", "blacklist_check", "diagnostics", "photo_grade", "wipe_certificate", "parts_declaration"}
    assert all(v is None for v in g.evidence.values())
    with SessionLocal() as s:
        old = inputs.gather(s, {"imei": IMEI, "sku_key": "iPhone 14|128", "grade": "B"}, _today() - timedelta(days=20))
    assert old.feed_price == 300 and old.feed_stale is True
