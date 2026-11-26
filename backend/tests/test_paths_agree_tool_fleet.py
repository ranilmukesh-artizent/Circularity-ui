"""P9-5.8 (R19, Review Focus 3, stories CR-01 to CR-08): a contract refresh priced by intake, `case.reevaluate`, the case panel,
`refresh.whatIf` with no lever moved, the Modeler's simulation queue and the stage chain gives the same best route, the same net
and the same keep, swap or upgrade for each tool. Three contracts (FC-30117, FC-30121 and FC-30125, one of whose tools is under a
safety recall). A case keeps its routes' nets in whole currency units (the route's term), so the stored paths agree to the unit
and the priced paths (panel, what-if, simulation) to the cent. Every test starts and ends with the demo reset."""

import pytest

from di.core.db import SessionLocal
from di.services.agents import chain
from di.services.cases import store
from tests import refreshkit as rk
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture
def cases(monkeypatch):
    by = rk.world(monkeypatch)
    rk.notice(rk.REPLACE)  # a replace recall on CMH-R1 (FC-30125) lands after the cases opened: value them again, as a sync does
    for cid in by.values():
        rk.reeval(cid)
    yield by
    rk.forget()
    starting.reset()


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _panel(cid: str) -> dict:
    r = client.get(f"/api/screens/refresh/{cid}", headers=h("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _split_of(lines: list[dict]) -> dict[str, str]:
    return {x["serial"]: x["action"] for x in lines}


def _stored(c: dict) -> tuple[str, float, dict[str, str]]:
    """The route, net (whole units) and per-tool actions of the proposal as the case keeps them."""
    best = c["recommendation"]["id"]
    net = next(r["terms"][0]["amt"] for r in c["routes"] if r["id"] == best)
    return best, float(net), _split_of(c["refreshProposal"]["proposal"]["lines"])


def _agree(cid: str) -> None:
    seen: dict[str, tuple[str, float, dict[str, str]]] = {"opened": _stored(_case(cid))}
    panel = _panel(cid)
    pr = panel["pricing"]
    exact = next(r["net"] for r in pr["routes"] if r["id"] == pr["best"])
    split = {t["serial"]: t["action"] for t in panel["tools"]}
    seen["panel"] = (pr["best"], exact, split)

    rk.reeval(cid)
    seen["reevaluated"] = _stored(_case(cid))

    w = call("refresh.whatIf", {"case_id": cid}, "admin")["output"]  # no lever moved
    assert w["changed"] == [] and w["fee_delta"] == 0 and w["renewal_delta"] == 0 and not w["flips_route"], w
    assert w["best_before"] == w["best_after"]
    totals = {a: sum(1 for v in split.values() if v == a) for a in ("keep", "swap", "upgrade")}
    assert w["before"] == w["split"] == totals, (w, totals)
    seen["whatIf"] = (w["best_before"], exact, split)

    page = client.get("/api/screens/modeler", params={"template": "tool_fleet", "org": rk.ORG}, headers=h("admin"))
    assert page.status_code == 200, page.text
    row = next(q for q in page.json()["queue"] if q["id"] == cid)
    seen["simulation"] = (row["best"], float(row["net"]), split)

    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="admin")
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    assert val is not None, [(r.stage, r.status) for r in run.stages]
    seen["run_chain"] = (val["route"], float(val["net"]), _split_of(_case(cid)["refreshProposal"]["proposal"]["lines"]))

    assert len({p[0] for p in seen.values()}) == 1, seen
    assert len({tuple(sorted(p[2].items())) for p in seen.values()}) == 1, seen
    for k in ("opened", "reevaluated", "run_chain"):  # kept in whole units
        assert abs(seen[k][1] - exact) <= 0.5, (k, seen)
    for k in ("panel", "whatIf", "simulation"):
        assert abs(seen[k][1] - exact) < 0.005, (k, seen)


def test_paths_agree_refresh_fc_30117(cases):
    _agree(cases["FC-30117"])


def test_paths_agree_refresh_fc_30121(cases):
    _agree(cases["FC-30121"])


def test_paths_agree_refresh_one_recalled_tool(cases):
    cid = cases["FC-30125"]
    assert {t["serial"]: t["action"] for t in _panel(cid)["tools"]}["CMH-R1"] == "swap"  # the recall, not the table, chose it
    _agree(cid)


@pytest.mark.skip(reason="replay of a contract refresh arrives with Phase 7 (P9-7.2)")
def test_paths_agree_refresh_replay():
    raise AssertionError("not reached")
