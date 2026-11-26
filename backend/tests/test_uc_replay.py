"""P9-9.15 (story UC-22; registry entries I-16 replay and I-17 publish in steps): used-car replay data and a 20 percent publish.

The generator (`replay_samples/used_cars.py`) makes 2,140 past cars from `mulberry32(1909)`; the replay of them under the
used-car flow gives the pack's modelled figures; the candidate flow is released to 20 percent of one region's cars and no
other. Every figure here is modelled, never measured. Nothing in this file reads or writes free text, so the model-first rule
(R16) has no output to route: the figures are arithmetic over the one decider's decisions. Publishing and widening a canary are
a person's (maker-checker; `rollout.` is in forbidden.py): the author's own approval is refused.
"""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.repositories import flows as flow_repo
from di.repositories import rollouts
from di.repositories.replay import Batch
from di.services.modeler.compile import FlowVersion
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import DATASETS, used_cars
from di.services.modeler.rollout import bucket
from di.services.modeler.templates import load_template
from di.services.replay import history
from di.services.replay import run as replay_run
from di.services.replay.sample import make_csv
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call

ORG = "Customer A"
NOW = datetime(2026, 11, 26, tzinfo=UTC)
FIXTURES = next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())
MAKER_TEXT = "Maker-checker: you made these changes, so you cannot widen their rollout."


# ---------------------------------------------------------------- the data
def test_uc_22_replay_rows_deterministic():
    a, b = used_cars.rows(), used_cars.rows()
    assert a == b and len(a) == 2140
    assert make_csv("used_cars", 2140) == make_csv("used_cars", 2140)
    days = Counter(r["decided_on"] for r in a)
    assert min(days) == "2026-10-24" and max(days) == "2026-11-24" and len(days) == 32
    assert min(days.values()) >= 66 and max(days.values()) <= 67  # about 67 a day
    low = [r for r in a if r["actual_route"] == "auction" and r["asset.mileage_at_return"] < 40000]
    assert len(low) == 31  # the count UC-13's plain-words guardrail needs
    assert {r["region"] for r in a} == {"RC-East", "RC-West"}
    assert set(DATASETS) >= {"used_cars"} and load_pack("used_cars").replay.dataset == "used_cars"


def test_uc_22_replay_rows_have_no_personal_column():
    cars = used_cars.rows()
    cols = {k for r in cars for k in r} | {k for r in used_cars.history_rows(cars[:5]) for k in r}
    assert history.personal_column(cols) is None
    assert all(r["vin"].startswith("SYNUC") and len(r["vin"]) == 17 for r in cars)  # a code, not a person


def test_uc_22_rows_pass_the_import():
    pack = load_pack("used_cars")
    ok_items, held = history.import_history(used_cars.history_rows(), pack, now=NOW)
    assert (len(ok_items), len(held)) == (2140, 0)
    body = (FIXTURES / "used_cars.csv").read_text(encoding="utf-8")
    assert body.startswith("# python -m di.services.replay.sample used_cars 2140\n")  # the command that made it
    assert body == make_csv("used_cars", 2140)
    from_csv, held_csv = history.import_history(history.parse_csv(body), pack, now=NOW)
    assert (len(from_csv), len(held_csv)) == (2140, 0)
    assert all(not f["at"] > i["decided_at"] for i in from_csv for f in i["facts"].values())  # no fact from the future


# ---------------------------------------------------------------- the figures
def test_uc_22_replay_figures_modelled():
    pack = load_pack("used_cars")
    items, _ = history.import_history(used_cars.history_rows(), pack, now=NOW)
    flow = FlowVersion(None, 1, ())  # the published used-car flow: the pack's gates, no business rule
    rep = replay_run.replay(Batch(1, "used_cars", ORG, 2140, 0, None, {}), items, flow, pack=pack)
    modelled = (pack.replay.example or {})["modelled"]
    assert (rep.n_items, rep.n_decided, rep.leakage, rep.data_quality) == (2140, 2140, [], [])
    assert abs(rep.straight_through_pct - modelled["straight_through_pct"]) <= 1  # 79 % straight through, +-1 point
    assert abs(rep.approvals_per_day - modelled["approvals_per_day"]) <= 1  # 9 a day
    assert abs(rep.exceptions_per_day - modelled["exceptions_per_day"]) <= 1  # 5 a day
    gross = (rep.flow_net - rep.actual_net) / rep.n_decided
    assert abs(gross - modelled["gross_per_car"]) <= 0.1 * modelled["gross_per_car"]  # +$410 a car, +-10 %
    assert rep.uplift.basis == "modelled" and "modelled" in rep.method  # every figure is an estimate, said so
    mix = {m["route"]: m for m in rep.route_mix}  # the route mix, actual against the flow, over the four channels
    assert set(mix) == {"retail", "auction", "dealer_trade", "salvage"}
    assert mix["retail"]["flow_pct"] > mix["retail"]["actual_pct"]  # the flow retails more than the past process did
    assert {f.actual for f in rep.flips} <= set(mix)  # a flip names channels, not lots


# ---------------------------------------------------------------- publish in steps
@pytest.fixture
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM rollout"))
            s.execute(text("DELETE FROM replay_run"))
            s.execute(text("DELETE FROM replay_batch"))
            s.commit()

    clean()
    starting.reset()
    flowkit.reset_flows()
    yield
    clean()
    flowkit.reset_flows()
    starting.reset()


def own_flow(maker: str = "planner-a") -> int:
    """Customer A's own used-car decision flow, published at version 1 with the template's default graph. `flow.fork` knows only
    the industrial, tool-fleet and device templates (`TEMPLATE_KEYS`), so the row is seeded here, the way the fork writes it."""
    with SessionLocal() as s:
        fid = s.execute(
            text(
                "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published, updated_at) "
                "VALUES ('used_cars', :o, 'Used cars', 'pub', 1, CAST(:g AS jsonb), now()) RETURNING id"
            ),
            {"o": ORG, "g": json.dumps(default_flow(load_template("used_cars")))},
        ).scalar_one()
        s.commit()
    return int(fid)


def used_car_flow(maker: str = "planner-a") -> int:
    """Customer A's own used-car flow with a draft (one rule) approved into shadow; `maker` saved and submitted it."""
    fid = own_flow()
    g = with_rule(default_flow(load_template("used_cars")), "UC-R1", "exclude", "dealer_trade", {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, maker))
    ok(call("flow.submit", {"flow_id": fid}, maker))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    return fid


def replay_done(fid: int) -> None:
    """A replay of the flow's draft over the first cars of the sample history, through the worker."""
    body = used_cars.make_csv(60)
    bid = ok(call("replay.import", {"pack": "used_cars", "org_unit_id": ORG, "csv": body}, "planner.a"))["id"]
    ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
    while worker.run_once():
        pass


def start(fid: int, user: str = "approver") -> dict:
    body = {"flow_id": fid, "region_key": "region", "region": "RC-West", "share": 20}
    return call("rollout.startCanary", body, user)


def pick_salt(fid: int, ids: list[str], low: int = 17, high: int = 23) -> None:
    """The canary's salt is random per database; fix one under which these cars fall about 20 percent into the canary, so the
    check does not depend on the draw."""
    for k in range(500):
        salt = f"uc-22-{k}"
        if low <= sum(bucket(i, str(fid), salt) < 20 for i in ids) <= high:
            with SessionLocal() as s:
                s.execute(text("UPDATE rollout SET salt = :s"), {"s": salt})
                s.commit()
            return
    raise AssertionError("no salt gives the share")


def versions(fid: int, cars: list[dict]) -> list[tuple]:
    with SessionLocal() as s:
        f = flow_repo.get_flow(s, fid)
        out = [rollouts.version_for(s, c, f) for c in cars]
        s.commit()
    return out


def test_uc_22_publish_one_region_20_percent(fresh):
    fid = used_car_flow()
    replay_done(fid)
    out = ok(start(fid))
    assert (out["stage"], out["region_key"], out["region"], out["share"]) == ("canary", "region", "RC-West", 20)
    assert (out["candidate_ver"], out["base_ver"]) == (2, 1)  # the candidate against the version in use
    west = [{"id": f"UC-W{k:03d}", "region": "RC-West"} for k in range(100)]
    east = [{"id": f"UC-E{k:03d}", "region": "RC-East"} for k in range(100)]
    pick_salt(fid, [c["id"] for c in west])
    got_west, got_east = versions(fid, west), versions(fid, east)
    assert all(g in (("draft", "canary"), (1, "control")) for g in got_west)  # the candidate, or the version in use
    canary = [g for g in got_west if g[1] == "canary"]
    assert 15 <= len(canary) <= 25  # 20 of 100, +-5
    assert all(g == (1, "out") for g in got_east)  # RC-East keeps the old version, whatever its bucket
    with SessionLocal() as s:  # both arms are journaled (Review Focus 10): an assignment per RC-West case, none for RC-East
        assert rollouts.arm_counts(s, fid) == {"canary": len(canary), "control": 100 - len(canary)}
        assert s.execute(text("SELECT count(*) FROM rollout_assignment WHERE case_id LIKE 'UC-W%'")).scalar_one() == 100
        assert not s.execute(text("SELECT 1 FROM rollout_assignment WHERE case_id LIKE 'UC-E%'")).first()
    assert versions(fid, west) == got_west  # a case keeps its arm


def test_uc_22_author_cannot_publish(fresh):
    fid = own_flow()  # the Admin is the author
    g = with_rule(default_flow(load_template("used_cars")), "UC-R1", "exclude", "dealer_trade", {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "admin"))
    ok(call("flow.submit", {"flow_id": fid}, "admin"))
    own = call("flow.approve", {"flow_id": fid}, "admin")  # the author's own approve
    assert own["ok"] is False and own["error"]["code"] == "conflict", own
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    replay_done(fid)
    mine = start(fid, "admin")  # the author cannot release it either
    assert mine["ok"] is False and mine["error"] == {"code": "conflict", "message": MAKER_TEXT}
    with SessionLocal() as s:
        assert rollouts.active_rollout(s, fid) == []
    assert ok(start(fid))["stage"] == "canary"  # a different person may
    assert call("rollout.widen", {"flow_id": fid, "share": 40}, "admin")["error"]["message"] == MAKER_TEXT
