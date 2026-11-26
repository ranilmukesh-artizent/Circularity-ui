"""Plan 9 P9-9.19 (stories UC-20, UC-21): the used-car worked questions, answered from the dealer stock by id."""

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services import questions  # noqa: F401  (registers the pack questions)
from di.services.canonical import store
from di.services.canonical.schema import vin_key
from di.services.device import analytics

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG, OTHER, SID = "Customer A", "Customer B", "uc_dms"
EV_DAYS = {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}
LEASE_DAYS = {"LOT-N": 40, "LOT-C": 30, "LOT-S": 22}
EV = ((41, "LOT-N", 52), (42, "LOT-N", 58), (43, "LOT-N", 61), (44, "LOT-N", 66), (46, "LOT-C", 31), (48, "LOT-S", 29))


def vin(n: int) -> str:
    return f"SYNUQ{n:012d}"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUQ%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUQ%"})


@pytest.fixture(autouse=True)
def stock():
    _clean()
    with SessionLocal() as s:
        extra.register(s, SID, ORG)
        facts = []
        cars = [(ORG, n, lot, d, "ev_crossover", "trade_in", EV_DAYS) for n, lot, d in EV]
        cars += [(ORG, 71, "LOT-N", 40, "suv", "lease_end", LEASE_DAYS), (ORG, 72, "LOT-S", 12, "suv", "lease_end", LEASE_DAYS),
                 (OTHER, 91, "LOT-N", 99, "ev_crossover", "lease_end", {"LOT-N": 99})]  # fmt: skip
        for org, n, lot, d, seg, kind, sale in cars:
            k = vin_key(org, vin(n))
            facts += [store.Fact("asset", k, "lot_id", lot), store.Fact("asset", k, "days_on_lot", d),
                      store.Fact("asset", k, "segment", seg), store.Fact("asset", k, "return_kind", kind),
                      store.Fact("market", k, "lot_days_to_sale", sale)]  # fmt: skip
        store.apply(s, SID, facts)
        s.commit()
    yield
    _clean()


def _ask(qid: str, orgs: set[str] | None = None) -> analytics.Answer:
    with SessionLocal() as s:
        return analytics.answer(s, qid, analytics.Scope(frozenset(orgs)) if orgs else None, clock.now().date())


def test_uc_20_ev_crossover_answer():
    a = _ask("wq_uc_1", {ORG})
    pts = {p["x"]: p["y"] for p in a.chart["series"][0]["points"]}
    assert pts == {"North lot": 58, "Central lot": 33, "South lot": 29}
    assert "North lot" in a.sentence and "South lot" in a.sentence and "58 days" in a.sentence and "29" in a.sentence
    assert len(a.examples) == 3 and {e["lot"] for e in a.examples} == {"LOT-N"}


def test_uc_20_scoped_to_tenant():
    a = _ask("wq_uc_1", {OTHER})
    assert [p["x"] for p in a.chart["series"][0]["points"]] == ["North lot"] and len(a.examples) == 1
    assert all(e["vin"] != vin(41) for e in a.examples)


def test_uc_21_fastest_lots_for_lease_returns():
    a = _ask("wq_uc_2", {ORG})
    pts = a.chart["series"][0]["points"]
    assert [p["x"] for p in pts] == ["South lot", "Central lot", "North lot"] and pts[0]["y"] == 22
    assert a.sentence.startswith("Lease returns sell fastest at South lot")
    assert a.examples[0]["vin"] == vin(72)
