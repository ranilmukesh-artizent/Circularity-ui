"""P9-7.2 (story X-06; registry entry I-16): the as-of replay of a history batch and its four measures.

Every number is arithmetic (di.services.replay.measures) over decisions made by the one decider (R19); nothing here reads or
writes free text, so the model-first rule (R16) has no output to route: a flip's reason is composed from the decision's own
gate result. Unit tests drive `replay` with stub deciders; the action tests run the job through the worker on the database.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.repositories.replay import Batch
from di.services.actions.registry import ActionError
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import load_template
from di.services.replay import history, measures
from di.services.replay import run as R
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call

PACK, ORG = "tool_fleet", "Customer A"
FV = FlowVersion(1, 1, ())
FIXTURES = next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())


def at(day: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def batch(n: int = 10) -> Batch:
    return Batch(1, PACK, ORG, n, 0, None, {})


def item(n: int, route: str, decided: str = "2026-05-04", realised: float = 100.0, **facts: object) -> dict:
    return {
        "item_id": f"T{n:03d}", "decided_at": at(decided), "cls": "CMH", "market": "US", "actual_route": route,
        "realised_value": realised, "costs": {}, "facts": {k: {"value": v, "at": at("2026-04-01")} for k, v in facts.items()},
    }  # fmt: skip


def route(rid: str, net: float, spread: float = 50.0, **over: object) -> dict:
    return {"id": rid, "net": net, "p10": net - spread, "p90": net + spread, "excluded": False} | over


def decision(chosen: str | None, routes: list[dict], **over: object) -> Decision:
    rec = next((r for r in routes if r["id"] == chosen), None)
    base = {
        "case_id": "x", "pack_key": PACK, "pack_version": "1", "flow_ver": 1, "route": chosen,
        "net": rec["net"] if rec else 0.0, "routes": routes, "recommendation": rec, "gates": [], "diversions": [],
        "rules_applied": [], "waived": False, "preferred": None, "plan": None, "required_steps": [], "hold": None,
        "trace": (), "as_of": None,
    }  # fmt: skip
    return Decision(**(base | over))  # type: ignore[arg-type]


CONFIDENT = [route("redeploy", 500), route("refurb", 100), route("resell", 50), route("harvest", 20), route("exit", 5)]
CLOSE = [route("redeploy", 500), route("refurb", 480), route("resell", 50), route("harvest", 20), route("exit", 5)]


def stub(plan: dict[str, Decision]):
    """A decider that answers each item (by the case id) with its prepared decision."""

    def decide(case, pack, flow_ver, as_of=None, **_):
        return plan[case["id"]]

    return decide


# ---------------------------------------------------------------- as of
def test_x_06_as_of_has_no_future_facts():
    it = item(1, "redeploy", decided="2026-10-01")
    it["facts"] = {
        "grade": [{"value": "B", "at": at("2026-09-28")}, {"value": "D", "at": at("2026-10-03")}],
        "rul": {"value": "60", "at": at("2026-09-01")},
    }
    known, leaked = R.as_of_facts(it)
    assert known == {"grade": "B", "rul": "60"}
    assert leaked == [{"item_id": "T001", "fact": "grade", "fact_at": at("2026-10-03").isoformat(),
                       "decided_at": at("2026-10-01").isoformat()}]  # fmt: skip

    seen: list[dict] = []

    def decide(case, pack, flow_ver, as_of=None, **_):
        seen.append(case)
        return decision("redeploy", CONFIDENT)

    rep = R.replay(batch(1), [it], FV, pack=load_pack(PACK), decide=decide)
    assert seen[0]["grade"] == "B" and seen[0]["rul"] == 60
    assert [(x["fact"], x["fact_at"][:10]) for x in rep.leakage] == [("grade", "2026-10-03")]

    with pytest.raises(ActionError) as e:
        R.assert_no_future({"grade": {"value": "D", "at": at("2026-10-03")}}, at("2026-10-01"))
    assert e.value.code == "validation_error"
    assert e.value.message == (
        f"Fact grade is dated {at('2026-10-03').isoformat()}, after the decision date {at('2026-10-01').isoformat()}: "
        "a replay uses only facts known at the time."
    )
    R.assert_no_future({"grade": {"value": "B", "at": at("2026-09-28")}}, at("2026-10-01"))


def test_x_06_route_mix_actual_vs_flow():
    actual = ["redeploy"] * 4 + ["refurb"] * 3 + ["exit"] * 3
    chosen = ["redeploy"] * 6 + ["refurb"] * 3 + ["exit"]
    items = [item(k, a) for k, a in enumerate(actual)]
    plan = {f"T{k:03d}": decision(c, CONFIDENT) for k, c in enumerate(chosen)}
    rep = R.replay(batch(), items, FV, pack=load_pack(PACK), decide=stub(plan))
    assert rep.route_mix == [  # in the pack's route order
        {"route": "refurb", "actual_pct": 30.0, "flow_pct": 30.0},
        {"route": "redeploy", "actual_pct": 40.0, "flow_pct": 60.0},
        {"route": "exit", "actual_pct": 30.0, "flow_pct": 10.0},
    ]
    assert rep.n_decided == 10 and rep.agreement_pct == 60.0  # items 0-3, 6 and 9 chose the route that was taken


def test_x_06_straight_through_definition(monkeypatch):
    monkeypatch.setattr(R, "pack_value_limit", lambda _pack: Decimal(1000))
    plan = {}
    for k in range(10):
        if k < 2:  # low confidence: the two best routes' intervals overlap
            plan[f"T{k:03d}"] = decision("redeploy", CLOSE)
        elif k == 2:  # an approval limit: the net is above it
            plan[f"T{k:03d}"] = decision("redeploy", [route("redeploy", 2000), route("refurb", 100)])
        else:
            plan[f"T{k:03d}"] = decision("redeploy", CONFIDENT)
    items = [item(k, "redeploy") for k in range(10)]
    rep = R.replay(batch(), items, FV, pack=load_pack(PACK), decide=stub(plan))
    assert rep.straight_through_pct == 70.0


def test_x_06_approvals_exceptions_per_day():
    days = ["2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08"]  # Monday to Friday
    items = [item(k, "redeploy", decided=days[k // 2]) for k in range(10)]
    plan = {}
    for k in range(10):  # all ten need an approval (low confidence); five also raise an exception (a hold)
        plan[f"T{k:03d}"] = decision("redeploy", CLOSE, hold={"gate": "G-CON-2"} if k % 2 else None)
    rep = R.replay(batch(), items, FV, pack=load_pack(PACK), decide=stub(plan))
    assert rep.days == 5
    assert (rep.approvals_per_day, rep.exceptions_per_day) == (2.0, 1.0)


def test_x_06_business_days_skip_weekends():
    assert measures.business_days(at("2026-05-04").date(), at("2026-05-17").date()) == 10  # two Mon-Fri weeks
    assert measures.business_days(at("2026-05-09").date(), at("2026-05-10").date()) == 1  # a weekend: at least one day


def _uplift_items(n: int = 30):
    items, plan = [], {}
    for k in range(n):
        items.append(item(k, "refurb", realised=80.0 + k))
        best = "redeploy" if k % 3 else "refurb"
        plan[f"T{k:03d}"] = decision(best, [route("redeploy", 100 + 7 * (k % 5)), route("refurb", 90 + (k % 4))])
    return items, plan


def test_x_06_uplift_bootstrap_band_deterministic():
    items, plan = _uplift_items()
    a = R.replay(batch(30), items, FV, pack=load_pack(PACK), decide=stub(plan)).uplift
    b = R.replay(batch(30), items, FV, pack=load_pack(PACK), decide=stub(plan)).uplift
    assert a == b
    assert a.band95[0] <= a.band80[0] <= a.primary <= a.band80[1] <= a.band95[1]
    assert a.conservative == min(a.primary, a.secondary) and a.basis == "modelled"
    assert R.bootstrap_band([1.0, 2.0, 3.0, 4.0]) == R.bootstrap_band([1.0, 2.0, 3.0, 4.0])


def test_x_06_uplift_arithmetic():
    rows = [
        {"actual_net": 100.0, "flow_net": 120.0, "realised": 90.0, "agree": True},
        {"actual_net": 100.0, "flow_net": 100.0, "realised": 110.0, "agree": True},
        {"actual_net": 50.0, "flow_net": 80.0, "realised": 40.0, "agree": False},
    ]
    u = measures.uplift(rows)
    assert u["primary"] == round(100 * 50 / 250, 2)  # sum(flow - actual) / sum(|actual|)
    assert u["bias"] == 1.0  # median(0.9, 1.1)
    assert u["secondary"] == round(100 * (300 - 240) / 240, 2)  # sum(flow x bias - realised) / sum(|realised|)
    assert u["conservative"] == min(u["primary"], u["secondary"])


def test_x_06_excluded_actual_route_is_listed():
    routes = [route("redeploy", 500), route("resell", 300, excluded=True, failReason="Recall check: quarantined")]
    rep = R.replay(batch(1), [item(0, "resell")], FV, pack=load_pack(PACK), decide=stub({"T000": decision("redeploy", routes)}))
    assert rep.flips[0].actual == "resell" and rep.flips[0].flow == "redeploy" and rep.flips[0].delta == 200.0
    assert rep.flips[0].reason == "actual route excluded by Recall check: quarantined"


def test_x_06_a_valuer_refusal_is_data_quality_not_a_crash():
    bad = item(0, "redeploy", grade="Z")  # not a grade of the tool fleet
    rep = R.replay(batch(1), [bad], FV, pack=load_pack(PACK))
    assert rep.n_decided == 0 and rep.n_items == 1
    assert rep.data_quality[0]["reason"].startswith("Not decided: ")


def test_x_06_both_sides_same_valuer():
    """The actual side's net is the net the same decision gives that route: the flip's delta is flow net minus it."""
    pack = load_pack(PACK)
    it = item(1, "exit", grade="B", rul=60)
    known, _ = R.as_of_facts(it)
    d = decide_case(R.case_input(it, known, pack), pack, FV, as_of=it["decided_at"])
    actual_net = next(r["net"] for r in d.routes if r["id"] == "exit")
    rep = R.replay(batch(1), [it], FV, pack=pack)
    assert rep.n_decided == 1
    if d.route != "exit":
        assert rep.flips[0].delta == round(d.net - actual_net, 2)
    assert rep.uplift.primary == round(100 * (d.net - actual_net) / abs(actual_net), 2)


@pytest.mark.parametrize(("pack", "name"), [("tool_fleet", "tool_fleet_returns.csv"), ("device", "device.csv")])
def test_x_06_replay_of_the_sample_history_decides_every_item(pack: str, name: str):
    now = datetime(2026, 11, 1, tzinfo=UTC)
    p = load_pack(pack)
    ok_items, held = history.import_history(history.parse_csv((FIXTURES / name).read_text(encoding="utf-8")), p, now=now)
    assert not held
    rep = R.replay(Batch(1, pack, ORG, 120, 0, None, {}), ok_items, FV, pack=p)
    assert (rep.n_items, rep.n_decided, rep.data_quality) == (120, 120, [])
    assert sum(m["flow_pct"] for m in rep.route_mix) == pytest.approx(100.0, abs=0.2)
    assert rep.leakage == [] and 0 <= rep.straight_through_pct <= 100


# ---------------------------------------------------------------- the actions and the job
@pytest.fixture
def fresh():
    starting.reset()
    flowkit.reset_flows()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM replay_run"))
        s.execute(text("DELETE FROM replay_batch"))
        s.commit()
    flowkit.reset_flows()
    starting.reset()


def as_csv(rows: int = 10, pack: str = PACK) -> str:
    p = load_pack(pack)
    head = ["item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "cost_logistics", "cost_refurb",
            "cost_test", "cost_fees", "market", "fact.condition", "fact.condition.at"]  # fmt: skip
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(head)
    for k in range(rows):
        w.writerow([f"T{k:03d}", p.classes[0].id, f"2026-05-0{4 + k % 5}", "x", p.routes[k % 3].id, "120", 5, 10, 2, 3, "US",
                    "BCAD"[k % 4], "2026-04-30T08:00:00"])  # fmt: skip
    return out.getvalue()


def import_batch(user: str = "planner.a") -> int:
    return ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": as_csv()}, user))["id"]


def own_flow(pack: str = PACK) -> int:
    """The org's own flow of the pack (a fork of the workspace default), which only the org's people may reach."""
    return ok(call("flow.fork", {"template_key": pack, "org_unit_id": ORG}, "planner-a"))["flow_id"]


def drain() -> None:
    while worker.run_once():
        pass


def test_x_06_replay_job_runs_async(fresh):
    bid, fid = import_batch(), own_flow()
    out = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
    assert out["status"] == "queued"
    queued = ok(call("replay.report", {"run_id": out["run_id"]}, "planner.a"))
    assert (queued["status"], queued["report"]) == ("queued", None)
    drain()
    done = ok(call("replay.report", {"run_id": out["run_id"]}, "planner.a"))
    assert done["status"] == "done" and done["flow_ver"] == "1" and done["dver"] is None
    rep = done["report"]
    assert (rep["n_items"], rep["n_decided"], rep["run_id"], rep["batch_id"]) == (10, 10, out["run_id"], bid)
    assert rep["days"] == 5 and rep["uplift"]["basis"] == "modelled"
    assert ok(call("replay.runs", {"flow_id": fid}, "planner.a"))["runs"][0]["status"] == "done"
    assert ok(call("replay.report", {"run_id": out["run_id"]}, "exec"))["status"] == "done"  # the Executive reads


def test_x_06_replay_runs_the_draft_when_there_is_one(fresh):
    bid, fid = import_batch(), own_flow()
    live = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
    graph = with_rule(default_flow(load_template(PACK)), "TF-C", "exclude", "redeploy", {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": graph}, "planner-a"))
    draft = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
    pinned = ok(call("replay.run", {"batch_id": bid, "flow_id": fid, "flow_ver": "1"}, "planner.a"))
    drain()
    reports = {k: ok(call("replay.report", {"run_id": v["run_id"]}, "planner.a")) for k, v in
               {"live": live, "draft": draft, "pinned": pinned}.items()}  # fmt: skip
    assert (reports["live"]["flow_ver"], reports["draft"]["flow_ver"], reports["pinned"]["flow_ver"]) == ("1", "draft", "1")
    assert reports["draft"]["dver"] == 2 and reports["live"]["dver"] is None
    flow_pct = lambda r: {m["route"]: m["flow_pct"] for m in r["report"]["route_mix"]}  # noqa: E731
    assert flow_pct(reports["draft"]).get("redeploy", 0) == 0  # the draft's rule excludes the route
    assert flow_pct(reports["live"]) == flow_pct(reports["pinned"])


def test_x_06_run_refusals(fresh):
    bid, fid = import_batch(), own_flow()
    r = call("replay.run", {"batch_id": bid, "flow_id": fid}, "exec")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert r["error"]["message"] == "The Executive view reads replay reports; a Planner or Admin runs them."
    r = call("replay.run", {"batch_id": bid, "flow_id": fid, "flow_ver": "draft"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error" and "no draft" in r["error"]["message"]
    r = call("replay.run", {"batch_id": bid, "flow_id": fid, "flow_ver": "9"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "not_found"
    other = own_flow("device")
    r = call("replay.run", {"batch_id": bid, "flow_id": other}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    r = call("replay.run", {"batch_id": 999999, "flow_id": fid}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "not_found"


def test_replay_run_tenant_boundary(fresh):
    bid, fid = import_batch(), own_flow()
    run_id = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))["run_id"]
    r = call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    r = call("replay.report", {"run_id": run_id}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM replay_run")).scalar_one() == 1
