"""P9-1.5 (R19, Review Focus 3): the same case decided by intake, re-evaluation, simulation and `decide_case` gives the same
route and the same net, to the cent. The chain (P9-2.1) and replay (P9-7.2) join by extending these tests. Every test ends
with the starting state."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.agents import chain
from di.services.canonical import store as canonical
from di.services.cases import store
from di.services.cases.decide import decide_case
from tests import flowkit, starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "Customer A"
ORDER = {"kind": "lease", "id": "L-1", "renew": True, "who": "Acme Rentals", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract L-1 renews", "when": "renewal confirmed"}  # fmt: skip
FACTS = {
    "tool_fleet": {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 60, "dem": {"lease": [ORDER]}},
    "device": {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 300, "qty": 20},
}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    yield
    starting.reset()
    flowkit.reset_flows()


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _queue_row(template: str, cid: str) -> dict[str, Any]:
    page = client.get("/api/screens/modeler", params={"template": template, "org": ORG}, headers=h("planner-a"))
    assert page.status_code == 200, page.text
    return next(q for q in page.json()["queue"] if q["id"] == cid)


def _replayed(template: str, c: dict[str, Any], pack, fv, given: dict[str, Any] | None = None) -> tuple[str | None, float]:
    """The route and net a replay of the same facts, as of the same date, gets from the one decider (P9-7.2, R19)."""
    from di.core import clock
    from di.repositories.replay import Batch
    from di.services.cases.decide import decide_case as one_decider
    from di.services.replay import run as replay_run

    when = clock.now()
    given = given or FACTS[template]
    facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in given.items()}
    it = {
        "item_id": f"T-PA-{template}",
        "decided_at": when,
        "cls": given.get("cls"),
        "market": None,
        "actual_route": "redeploy" if template == "tool_fleet" else "buynow",
        "realised_value": 1.0,
        "facts": facts,
    }
    got: list = []

    def decide(*a, **k):
        got.append(one_decider(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, c["template"], ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    return got[0].route, got[0].net


def _paths_agree(template: str) -> None:
    body = {
        "org_unit_id": ORG,
        "template_key": template,
        "asset_key": f"T-PA-{template}",
        "reason": "manual",
        "facts": tool_case_facts(f"T-PA-{template}", FACTS[template]) if template == "tool_fleet" else FACTS[template],
    }
    opened = call("case.open", body, "planner-a")
    assert opened["ok"], opened
    cid = opened["output"]["case_id"]
    c = _case(cid)
    seen = {"opened": (c["recommendation"]["id"], c["recommendation"]["net"])}

    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert _case(cid)["stage"] == "reeval"
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    c = _case(cid)
    seen["reevaluated"] = (c["recommendation"]["id"], c["recommendation"]["net"])

    row = _queue_row(template, cid)
    seen["simulation"] = (row["best"], row["net"])

    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)

    with SessionLocal() as s:
        seen["replay"] = _replayed(template, c, live_pack(s, c), flow_version(s, c))  # P9-7.2: replay is a fifth path

    routes = {path[0] for path in seen.values()}
    assert len(routes) == 1, seen
    nets = [path[1] for path in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_tool_fleet():
    _paths_agree("tool_fleet")


def test_paths_agree_device():
    _paths_agree("device")


# ---------------------------------------------------------------------------------------------------------------------
# P9-3.21 (R19, TF-01 ... TF-16): twelve tool-fleet stories, each decided by intake, `case.reevaluate`, the Modeler's
# simulation queue, `decide_case`, as-of replay (where the story is a fact of the history) and the stage chain. A failure
# prints every path with its route and net, so the path that disagreed is named.
# ---------------------------------------------------------------------------------------------------------------------
pytestmark = [pytest.mark.usefixtures("no_synced_demand"), pytest.mark.usefixtures("no_synced_conflicts")]

SEEN = "2026-10-04T08:15:00+00:00"  # telematics three days before the pinned clock
KEY_CONTRACT = "FC-TFPA-KEY"
REPAIR_RECALL = {"recall_id": "RC-2026-017", "tool_class": "BRK", "serial_from": "BRK-51000", "serial_to": "BRK-51999",
                 "remedy": "repair", "affected_parts": ["Impact mechanism"], "status": "active"}  # fmt: skip
REPLACE_RECALL = {"recall_id": "RC-2026-014", "tool_class": "CRH", "serial_from": "CRH-44000", "serial_to": "CRH-44999",
                  "remedy": "replace", "affected_parts": ["Brushless motor"], "status": "active"}  # fmt: skip
SERIALS = ["CMH-PA001", "CMH-PA002", "CRH-44120", "BRK-51007", "CMH-PA005", "CMH-PA006", "CMH-PA007", "CMH-PA008",
           "CMH-PA009", "CMH-PA010", "CMH-PA011", "DCD-PA012", "BAT-PA001"]  # fmt: skip
KEYS = [*SERIALS, "FC-TEST", KEY_CONTRACT, "RC-2026-017", "RC-2026-014", "DR-PA-1"]


def _clean_canonical() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition", "recall", "repair_event"):
            for t in ("provenance", "canonical", "conflict"):
                conn.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": KEYS})  # noqa: S608


@pytest.fixture(autouse=True)
def clean_world():
    _clean_canonical()
    yield
    _clean_canonical()


def _write(source: str, facts: list[canonical.Fact]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, facts)
        s.commit()


def _worn_tool(serial: str, grade: str, hours: float = 820, damage: str | None = None) -> None:
    """Telematics (a High life class: 95% coverage) and an inspection grade from the repair-log system."""
    _write("fleet", [
        canonical.Fact("condition", serial, "run_hours", hours, resource="tools"),
        canonical.Fact("condition", serial, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", serial, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", serial, "telemetry_coverage_pct", 95, resource="tools"),
    ])  # fmt: skip
    g = {"grade": grade, "test_result": "pass", "inspection_ref": "DR-PA-1", "graded_at": "2026-10-07T03:00:00Z"}
    g |= {"damage_code": damage} if damage else {}
    _write("repairlog", [canonical.Fact("condition", serial, k, v, resource="orders") for k, v in g.items()])


def _notice(n: dict) -> None:
    _write("recall", [canonical.Fact("recall", n["recall_id"], k, v, resource="notices") for k, v in n.items()])


def _facts(cls: str, grade: str = "B", rul: int = 60, **more) -> dict[str, Any]:
    base = {"cls": cls, "grade": grade, "ft": "Repair center", "site": "Houston", "rul": rul, "dem": {"lease": [ORDER], "wo": {}}}
    return base | more


def _open_tool(serial: str, facts: dict[str, Any], **kw) -> str:
    body = {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "manual",
            "facts": tool_case_facts(serial, facts, **kw)}  # fmt: skip
    opened = call("case.open", body, "planner-a")
    assert opened["ok"], opened
    return opened["output"]["case_id"]


def _best_of(c: dict[str, Any]) -> tuple[str, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else ("none", 0.0)


def _agree_tool(cid: str, given: dict[str, Any] | None, *, story: str) -> dict[str, Any]:
    """The paths of one open case; `given` is its history facts for the replay path (None: the story is held in stored
    evidence that a history row does not carry, so the replay path does not apply). Returns the case as it was opened."""
    opened = _case(cid)
    seen = {"opened": _best_of(opened)}
    blocked = opened["recommendation"] is None  # every route excluded by a gate: nothing to submit or to decline
    if not blocked:
        assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
        assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
        assert _case(cid)["stage"] == "reeval"
        assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
        seen["reevaluated"] = _best_of(_case(cid))
    c = _case(cid)

    row = _queue_row("tool_fleet", cid)
    seen["simulation"] = (row["best"] or "none", row["net"] or 0.0)

    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route or "none", d.net or 0.0)

    if given is not None:
        with SessionLocal() as s:
            r = _replayed("tool_fleet", c, live_pack(s, c), flow_version(s, c), given)
        seen["replay"] = (r[0] or "none", r[1] or 0.0)

    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="planner-a")
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    if val and val.get("route"):  # the chain may wait for a person before the valuation
        seen["run_chain"] = (val["route"], val["net"])

    msg = f"{story}: the paths disagree: {seen}"
    assert len({p[0] for p in seen.values()}) == 1, msg
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, msg
    return opened


def test_paths_agree_tool_fleet_clean_reissue():
    # Story: a Houston combihammer, grade B, back at contract end with a renewing fleet order, a clean record: it goes out again.
    g = _facts("CMH")
    c = _agree_tool(_open_tool("CMH-PA001", g), g, story="clean re-issue")
    assert c["recommendation"] is not None and not c.get("gateHold")


def test_paths_agree_tool_fleet_contract_block():
    # Story: the line has an open damage charge (G-CON-2): every route is blocked, the case waits with no recommendation.
    g = _facts("CMH")
    line = {"damage_charge_open": True, "charge_ref": "CHG-4412"}
    c = _agree_tool(_open_tool("CMH-PA002", g, line=line), None, story="contract block")
    assert c["recommendation"] is None and c["gateHold"]["gates"] == ["G-CON-2"]


def test_paths_agree_tool_fleet_recall_replace():
    # Story: a replace recall (RC-2026-014) names this rotary hammer: only exit and a safe harvest stay open, never released.
    _notice(REPLACE_RECALL)
    c = _agree_tool(_open_tool("CRH-44120", _facts("CRH")), None, story="recall replace")
    assert {r["id"] for r in c["routes"] if not r["excluded"]} <= {"exit", "harvest"}
    assert c["recommendation"]["id"] in {"exit", "harvest"}


def test_paths_agree_tool_fleet_recall_repair_released():
    # Story: a repair recall (RC-2026-017) quarantined a breaker; Quality released it after the fix: release is open again.
    _notice(REPAIR_RECALL)
    cid = _open_tool("BRK-51007", _facts("BRK", "A"))
    assert {"release", "redeploy", "resell"}.isdisjoint(r["id"] for r in _case(cid)["routes"] if not r["excluded"])
    released = call("recall.release", {"case_id": cid, "note": "Impact mechanism replaced at the depot"}, "approver")
    assert released["ok"], released
    _agree_tool(cid, None, story="recall repair released")
    assert "release" in {r["id"] for r in _case(cid)["routes"] if not r["excluded"]}


def test_paths_agree_tool_fleet_stale_telematics():
    # Story: the tool's telematics were last seen 8 days ago (GR-13, over 7 days): reissue and pool hold, the rest stay open.
    cid = _open_tool("CMH-PA005", _facts("CMH", "B", 62), seen="2026-09-29T07:40:00+00:00")
    c = _agree_tool(cid, None, story="stale telematics")
    gate = next(x for x in c["gates"] if x["id"] == "G-TOOL-TEL")
    assert not gate["passed"] and gate["reason"] == "Telematics last seen 8 days ago"


def test_paths_agree_tool_fleet_low_life():
    # Story: no telematics, 41 months on the contract: the life estimate is a Low class (a range, 0.50 confidence);
    # re-issue and pool are shown but never recommended.
    cid = _open_tool("CMH-PA006", _facts("CMH", "B", 62), seen=None, line={"months_on_contract": 41})
    c = _agree_tool(cid, None, story="low life")
    assert c["life"]["confidence"] == "Low" and c["life"]["range"] == [0, 53], c["life"]


def test_paths_agree_tool_fleet_disagreement():
    # Story: inspection says grade A but the telematics wear index is 65: the grade/wear disagreement goes to Quality.
    _worn_tool("CMH-PA007", "A")
    c = _agree_tool(_open_tool("CMH-PA007", _facts("CMH", "B", 62), seen=SEEN), None, story="disagreement")
    assert c["disagreement"]["text"].startswith("Telematics and inspection disagree: grade A")


def test_paths_agree_tool_fleet_key_account():
    # Story: the contract is a key account (Westmark Supply): the account manager reviews the return before approval.
    _worn_tool("CMH-PA008", "A", hours=200)  # little wear: the grade and the telematics agree
    _write("fleet", [canonical.Fact("contract", KEY_CONTRACT, "customer", "Westmark Supply", resource="contracts"),
                     canonical.Fact("contract", KEY_CONTRACT, "key_account", True, resource="contracts")])  # fmt: skip
    cid = _open_tool("CMH-PA008", _facts("CMH", "A", 75), line={"contract_id": KEY_CONTRACT}, seen=SEEN)
    c = _agree_tool(cid, None, story="key account")
    assert (c["approvalRoute"]["kind"], c["approvalRoute"]["role"]) == ("person", "Account manager")


def test_paths_agree_tool_fleet_young_write_off():
    # Story: a worn grade D tool of 12 months is written off: GR-15 sends a write-off under 24 months to Service operations.
    g = _facts("CMH", "D", 6, age=12, age_months=12, dem={"lease": [], "wo": {}})
    c = _agree_tool(_open_tool("CMH-PA009", g), g, story="young write-off")
    assert c["recommendation"]["id"] in {"exit", "harvest"}
    assert (c["approvalRoute"]["kind"], c["approvalRoute"]["role"]) == ("person", "Service operations")


def test_paths_agree_tool_fleet_queue_loser():
    # Story: two returns compete for one renewing order (L-1); the one that does not get it must still agree with the queue
    # plan on every path (replay decides a return alone, so it is not one of them).
    g = _facts("CMH", "A", 75)
    a, b = _open_tool("CMH-PA010", g), _open_tool("CMH-PA011", g)
    dest = {i: ((_case(i)["recommendation"] or {}).get("dest") or {}).get("id") for i in (a, b)}
    holders = [i for i in (a, b) if dest[i] == ORDER["id"]]
    assert len(holders) == 1, dest  # the order is filled once
    loser = a if holders[0] == b else b
    _agree_tool(loser, None, story="queue loser")
    assert (_case(loser)["recommendation"] or {}).get("id") not in (None, "release")


def test_paths_agree_tool_fleet_refurb_over_600():
    # Story: a grade C core drill is refurbished at $702, over $600 (GR-14): the Fleet manager approves it.
    g = {"grade": "C", "test_result": "pass", "inspection_ref": "DR-PA-1", "graded_at": "2026-10-07T03:00:00Z"}  # no telematics
    _write("repairlog", [canonical.Fact("condition", "DCD-PA012", k, v, resource="orders") for k, v in g.items()])
    c = _agree_tool(_open_tool("DCD-PA012", _facts("DCD", "C", 46), seen=SEEN), None, story="refurb over $600")
    assert c["recommendation"]["id"] == "refurb"
    assert (c["approvalRoute"]["kind"], c["approvalRoute"]["role"]) == ("person", "Fleet manager")


def test_paths_agree_tool_fleet_battery():
    # Story: a battery pack at 76% state of health from a returned tool kit, with a pool request open and no recycler permit on
    # file: the gates leave only resale, and every path must say so (a pack has no replay row: it has no history facts yet).
    pool = {"kind": "proj", "id": "TPR-9", "who": "Houston service center", "site": "Houston", "need": 14, "rental": 140,
            "quote": "PR-9"}  # fmt: skip
    g = {"cls": "BAT", "site": "Houston", "soh": 76, "sohRead": "2026-10-28", "damaged": False, "dem": {"proj": pool}}
    c = _agree_tool(_open_tool("BAT-PA001", g), None, story="battery")
    assert c["cls"] == "BAT" and c["recommendation"]["id"] == "resell"
