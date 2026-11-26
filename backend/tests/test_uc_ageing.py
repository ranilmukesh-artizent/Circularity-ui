"""Plan 9 P9-9.18 (story UC-19): cars more than 45 days on a lot are flagged with a suggested move, and one model type ageing at
one lot raises an alert for the lot manager (Planner).

The stock is the dealer mock's: 30 cars, the five EV crossovers at LOT-N (52 to 72 days), three more EV crossovers, and 22
trade-ins of which two are over 45 days (VINs ...063 and ...070). The facts are written as the dealer adapter writes them."""

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import vin_key
from di.services.cases import uc_ageing
from di.services.modeler.pack import load_pack

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
SID = "uc_dms"
EV_DAYS = {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}
TRUCK_DAYS = {"LOT-N": 40, "LOT-C": 30, "LOT-S": 32}
PRICE = {"LOT-N": 23600, "LOT-C": 24000, "LOT-S": 24300}
EV_STOCK = ((41, "LOT-N", 52), (42, "LOT-N", 58), (43, "LOT-N", 61), (44, "LOT-N", 66), (45, "LOT-N", 72),
            (46, "LOT-C", 31), (47, "LOT-C", 35), (48, "LOT-S", 29))  # fmt: skip
OLD = {63: ("LOT-S", 49, "truck"), 70: ("LOT-N", 47, "suv")}


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _stock() -> list[tuple[int, str, int, str]]:
    rows = [(n, lot, d, "ev_crossover") for n, lot, d in EV_STOCK]
    for n in range(61, 83):
        lot, d, seg = OLD.get(n, (("LOT-N", "LOT-C", "LOT-S")[(n - 61) % 3], 3 + ((n - 61) * 7) % 41, "suv"))
        rows.append((n, lot, d, seg))
    return rows


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM work_item WHERE type = 'AL-UC-AGEING'"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUC%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


@pytest.fixture
def stock():
    _clean()
    with SessionLocal() as s:
        extra.register(s, SID, ORG)
        facts = []
        for n, lot, days, seg in _stock():
            k = vin_key(ORG, vin(n))
            sale = EV_DAYS if seg == "ev_crossover" else TRUCK_DAYS if seg == "truck" else {"LOT-N": 34, "LOT-C": 21, "LOT-S": 15}
            facts += [
                store.Fact("asset", k, "lot_id", lot), store.Fact("asset", k, "days_on_lot", days),
                store.Fact("asset", k, "segment", seg), store.Fact("market", k, "lot_days_to_sale", sale),
                store.Fact("market", k, "lot_avg_price", PRICE),
            ]
        store.apply(s, SID, facts)
        s.commit()
    yield
    _clean()


def _flags():
    with SessionLocal() as s:
        return uc_ageing.flagged(s, ORG)


def test_uc_19_cars_over_45_days_flagged(stock):
    flags = _flags()
    assert len(_stock()) == 30 and len(flags) == 7
    assert [f["days_on_lot"] for f in flags] == [72, 66, 61, 58, 52, 49, 47]  # oldest first
    assert {f["vin"] for f in flags} == {vin(n) for n in (41, 42, 43, 44, 45, 63, 70)}
    assert all(f["days_on_lot"] > 45 for f in flags)


def test_uc_19_ev_crossovers_suggest_south_lot(stock):
    ev = [f for f in _flags() if f["segment"] == "ev_crossover"]
    assert len(ev) == 5 and {f["lot"] for f in ev} == {"LOT-N"}
    for f in ev:
        assert (f["kind"], f["to_lot"], f["to_days"]) == ("transfer", "LOT-S", 29)
        assert f["instruction"] == {"type": "lot_transfer", "vin": f["vin"], "fromLot": "LOT-N", "toLot": "LOT-S"}
        assert "South lot" in f["text"] and "29 days" in f["text"]
    truck = next(f for f in _flags() if f["vin"] == vin(63))
    assert (truck["kind"], truck["to_lot"]) == ("transfer", "LOT-C")


def test_uc_19_alert_one_model_one_lot(stock):
    with SessionLocal() as s:
        groups = uc_ageing.sync_alerts(s, ORG, "system")
        uc_ageing.sync_alerts(s, ORG, "system")  # a second sync opens nothing more
        s.commit()
    assert [(g["title"], g["n"]) for g in groups] == [("EV crossovers ageing at North lot", 5)]
    with SessionLocal() as s:
        rows = s.execute(text("SELECT title, owner_role, action, kind FROM work_item WHERE type = 'AL-UC-AGEING' AND status = 'open'")).all()
    assert [tuple(r) for r in rows] == [
        ("EV crossovers ageing at North lot", "Planner", "Move cars to the lot where demand is higher", "exception")
    ]


def test_uc_19_alert_closes_when_the_cars_move(stock):
    with SessionLocal() as s:
        uc_ageing.sync_alerts(s, ORG, "system")
        for n in (41, 42, 43):  # three cars leave North lot: two are left, below min_cars
            store.apply(s, SID, [store.Fact("asset", vin_key(ORG, vin(n)), "days_on_lot", 2)])
        uc_ageing.sync_alerts(s, ORG, "system")
        s.commit()
        n_open = s.execute(text("SELECT count(*) FROM work_item WHERE type = 'AL-UC-AGEING' AND status = 'open'")).scalar_one()
    assert n_open == 0


def test_uc_19_auction_when_no_lot_is_under_45_days():
    pack = load_pack("used_cars")
    slow = uc_ageing.Car("x:V1", "V1", "LOT-N", 60, "truck", 1000.0, {"LOT-N": 50, "LOT-C": 46, "LOT-S": 45})
    s = uc_ageing.suggest(slow, pack)
    assert s["kind"] == "auction" and s["instruction"] is None
    own = uc_ageing.Car("x:V2", "V2", "LOT-S", 60, "suv", 1000.0, {"LOT-N": 34, "LOT-C": 21, "LOT-S": 15})
    assert uc_ageing.suggest(own, pack)["kind"] == "auction"  # its own lot is already the fastest
