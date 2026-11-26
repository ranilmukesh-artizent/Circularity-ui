"""P9-6.4 (R19, story DV-01): a device case decided by intake, `case.reevaluate`, the Modeler's simulation queue,
`decide_case` and the stage chain gives the same channel and the same net, to the cent. Three cases: the sample IMEI
(grade B), a grade C device and a 20-line lot. Every test ends with the starting state."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.agents import chain
from di.services.cases import store
from di.services.cases.decide import decide_case
from di.services.device import intake as device_intake
from di.services.modeler.valuers import device
from tests import flowkit, starting
from tests.device_registry import seed_registry
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

ORG = "Customer A"


def _doc(n: int, grade: str = "B", **kw) -> dict:
    when = (clock.now() - timedelta(days=5)).isoformat()
    return {
        "tradeInId": f"TI-{n:05d}", "imei": "359990000000428" if n == 428 else f"35999000{n:07d}",
        "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128},
        "quote": {"declaredGrade": grade, "amount": 410, "currency": "USD", "quotedAt": when},
        "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": when, "payoutAmount": 410,
    } | kw  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        for t in ("device_tradein", "device_price_point"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM provenance WHERE source_id = 'dvreg' AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    with engine.begin() as conn:
        for g, p in (("B", 330), ("C", 250)):
            conn.execute(
                text(
                    "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                    "VALUES ('iPhone 14|128', :g, :w, :p, 'USD', 'dvmkt')"
                ),
                {"g": g, "w": clock.now().date() - timedelta(days=3), "p": p},
            )
    yield
    starting.reset()
    flowkit.reset_flows()
    _clean()


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _open(*docs: dict) -> str:
    with SessionLocal() as s:
        for d in docs:
            lab.land_tradein(s, d, ORG)
        s.commit()
        for d in docs:  # a received device with no registry check is held (P9-6.6): these cases have a clear one
            seed_registry(d["imei"])
        (cid,) = device_intake.open_pending(s, ORG)
        s.commit()
    return cid


def _agree(cid: str) -> None:
    c = _case(cid)
    seen = {"opened": (c["recommendation"]["id"], c["recommendation"]["net"])}
    opened_bands = c["valuer"].get("inputs", {}).get("bands", {})

    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    c = _case(cid)
    seen["reevaluated"] = (c["recommendation"]["id"], c["recommendation"]["net"])
    # P9-6.10: the same band on every channel after a new valuation
    assert c["valuer"].get("inputs", {}).get("bands", {}) == opened_bands
    if c["valuer"].get("imei"):  # a device (not a lot): a band per channel the formulas price, from the feed week, no interval
        assert set(opened_bands) == {"buynow", "offers", "auction"}
        assert all(b["p10"] == b["p50"] == b["p90"] and b["feed_week"] and b["model_id"] is None for b in opened_bands.values())
        assert c["recommendation"]["id"] == device.decide(c["valuer"])["best"]["k"]
    else:
        assert opened_bands == {}

    page = client.get("/api/screens/modeler", params={"template": "device", "org": ORG}, headers=h("planner-a"))
    assert page.status_code == 200, page.text
    row = next(q for q in page.json()["queue"] if q["id"] == cid)
    seen["simulation"] = (row["best"], row["net"])

    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)

    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="planner-a")
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    if val:  # the chain may wait for a person before the valuation
        seen["run_chain"] = (val["route"], val["net"])

    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_device_sample_imei():
    _agree(_open(_doc(428)))


def test_paths_agree_device_grade_c():
    _agree(_open(_doc(429, "C", imei="359990000000429")))


def test_paths_agree_device_bulk_lot():
    _agree(_open(*[_doc(n, "B" if n % 4 else "C", bulk=True, batchId="BATCH-0020") for n in range(100, 120)]))
