"""P9-7.5 (story X-06; registry entries I-5 and I-16): replay honours queue capacity by date.

For a pack with a queue planner (the tool fleet), a batch that has demand windows is decided per decision date in date order
through `QueuePlanner.plan`: the open demand of a day (opens_at <= d < closes_at, not yet filled) and the repair slots open
that day are what the day's returns share, and a unit a return took is not offered on a later day. `constraint_loss` is the
case-by-case net minus the planned net. Nothing here reads or writes free text, so the model-first rule (R16) has no output
to route.
Unit tests use stub deciders and the real decider over generated items; the action tests run the job through the worker.
"""

import csv
import io
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.repositories.replay import Batch
from di.services.cases.decide import Decision
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from di.services.replay import history
from di.services.replay import run as R
from tests import flowkit, starting
from tests.helpers import call

PACK, ORG = "tool_fleet", "Customer A"
FV = FlowVersion(1, 1, ())
NOW = datetime(2026, 11, 26, tzinfo=UTC)
HEAD = ["demand_id", "route", "opens_at", "closes_at", "value", "capacity"]


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def drow(n: int, **over: str) -> dict[str, str]:
    base = {"demand_id": f"D{n:03d}", "route": "release", "opens_at": "2026-05-01", "closes_at": "2026-06-01", "value": "900",
            "capacity": "2"}  # fmt: skip
    return {**base, **over}


def dcsv(rows: list[dict[str, str]], head: list[str] | None = None) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=head or [*HEAD, *(k for k in (rows[0] if rows else {}) if k not in HEAD)],
                       lineterminator="\n")  # fmt: skip
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def dem(n: int, **over: object) -> dict:
    """A stored demand row as the replay reads it."""
    base = {"demand_id": f"D{n:03d}", "route": "release", "opens_at": date(2026, 5, 1), "closes_at": date(2026, 6, 1),
            "value": 900.0, "capacity": 2}  # fmt: skip
    return base | over


def at(day: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def item(n: int, day: str, route: str = "release", grade: str = "A", cls: str = "CMH") -> dict:
    return {
        "item_id": f"T{n:03d}", "decided_at": at(day), "cls": cls, "market": "US", "actual_route": route,
        "realised_value": 100.0, "costs": {}, "facts": {"condition": {"value": grade, "at": at("2026-04-01")}},
    }  # fmt: skip


def batch(n: int) -> Batch:
    return Batch(1, PACK, ORG, n, 0, None, {})


# ---------------------------------------------------------------- the demand file
def test_x_06_demand_rows_are_checked_and_held_with_reasons():
    rows = [
        drow(1), drow(2, route="scrap"), drow(3, closes_at="2026-04-01"), drow(1), drow(5, route="harvest"),
        drow(6, capacity="0"), drow(7, value=""), drow(8, opens_at="soon"),
    ]  # fmt: skip
    got, held = history.import_demand(rows, load_pack(PACK), seen=())
    assert [g["demand_id"] for g in got] == ["D001"]
    assert [h["held_reason"] for h in held] == [
        f"Route 'scrap' is not a route of {PACK}.",
        "Demand closes before it opens.",
        "Duplicate demand_id.",
        "Route 'harvest' takes no demand window.",
        "Capacity is a whole number of at least 1.",
        "No demand value.",
        "No valid window date.",
    ]
    assert got[0]["opens_at"] == date(2026, 5, 1) and got[0]["capacity"] == 2 and got[0]["value"] == 900.0
    _, again = history.import_demand([drow(1)], load_pack(PACK), seen={"D001"})  # an append sees the ids of the batch
    assert [h["held_reason"] for h in again] == ["Duplicate demand_id."]


def test_x_06_demand_header_refusals():
    pack = load_pack(PACK)
    with pytest.raises(history.HistoryRefused, match="Column capacity is missing"):
        history.import_demand([{k: v for k, v in drow(1).items() if k != "capacity"}], pack, seen=())
    with pytest.raises(history.HistoryRefused, match="looks like personal data"):
        history.import_demand([drow(1) | {"customer_email": "x"}], pack, seen=())
    with pytest.raises(history.HistoryRefused, match="no rows"):
        history.import_demand([], pack, seen=())


# ---------------------------------------------------------------- the replay by date
class Spy:
    """A decider that answers every case with the same decision and keeps what it was asked with, per decision date."""

    def __init__(self, net: float = 100.0) -> None:
        self.asked: list[tuple[str, int, list[str], int]] = []  # (day, queue size, units offered, slots)
        self.net = net

    def __call__(self, case, pack, flow_ver, as_of=None, *, queue=None, planner=None, **_):
        offered = sorted(getattr(planner, "offered", []))
        slots = getattr(planner, "slots", -1)
        self.asked.append((as_of.date().isoformat(), len(queue or []), offered, slots))
        routes = [{"id": "release", "net": self.net, "p10": self.net - 5, "p90": self.net + 5, "excluded": False}]
        return Decision(
            case_id=case["id"], pack_key=PACK, pack_version="1", flow_ver=1, route="release", net=self.net, routes=routes,
            recommendation=routes[0], gates=[], diversions=[], rules_applied=[], waived=False, preferred=None, plan=None,
            required_steps=[], hold=None, trace=(), as_of=as_of,
        )  # fmt: skip


def planned(spy: Spy) -> list[tuple[str, int, list[str], int]]:
    """The calls made with the day's queue (the planned decision), not the one-return case-by-case ones."""
    return [a for a in spy.asked if a[1] > 1 or a[3] != 1]


def test_x_06_items_are_decided_per_date_in_date_order_with_the_demand_open_that_day():
    items = [item(1, "2026-05-20"), item(2, "2026-05-04"), item(3, "2026-05-04"), item(4, "2026-07-01")]
    spy = Spy()
    rows = [dem(1, closes_at=date(2026, 5, 10), capacity=1), dem(2, opens_at=date(2026, 5, 15), capacity=1)]
    R.replay(batch(4), items, FV, pack=load_pack(PACK), decide=spy, demand=rows)
    days = [a[0] for a in planned(spy)]
    assert days == ["2026-05-04", "2026-05-04", "2026-05-20", "2026-07-01"]
    by_day = {a[0]: a[2] for a in planned(spy)}
    assert by_day["2026-05-04"] == ["D001"]  # D002 opens on the 15th; the closing day is not open (d < closes_at)
    assert by_day["2026-05-20"] == ["D002"]  # D001 closed on the 10th
    assert by_day["2026-07-01"] == []  # both windows are over
    assert {a[1] for a in planned(spy) if a[0] == "2026-05-04"} == {2}  # the day's returns are planned together


def test_x_06_a_filled_demand_unit_is_not_offered_again():
    items = [item(1, "2026-05-04"), item(2, "2026-05-05"), item(3, "2026-05-06")]

    spy = Spy()
    rows = [dem(1, capacity=2)]
    plans: list[list[str]] = []

    def decide(case, pack, flow_ver, as_of=None, *, queue=None, planner=None, **kw):
        d = spy(case, pack, flow_ver, as_of, queue=queue, planner=planner, **kw)
        if planner is not None and getattr(planner, "slots", -1) != 1:
            plans.append(sorted(planner.offered))
            planner.took(case["id"], ["D001", "D001.1"][len(plans) - 1] if len(plans) < 3 else None)  # the plan hands out a unit
        return d

    R.replay(batch(3), items, FV, pack=load_pack(PACK), decide=decide, demand=rows)
    assert plans[0] == ["D001", "D001.1"]  # two units, one per capacity
    assert plans[1] == ["D001.1"]  # the first was filled on the 4th
    assert plans[2] == []  # both are filled by the 6th: a filled row is not offered again


def test_x_06_repair_slots_are_the_open_refurb_capacity_of_the_day():
    items = [item(1, "2026-05-04"), item(2, "2026-06-10")]
    spy = Spy()
    rows = [dem(1, route="refurb", capacity=3, closes_at=date(2026, 6, 1))]
    R.replay(batch(2), items, FV, pack=load_pack(PACK), decide=spy, demand=rows)
    assert [(a[0], a[3]) for a in planned(spy)] == [("2026-05-04", 3), ("2026-06-10", 0)]  # no window open on the 10th: no slot


def test_x_06_without_demand_rows_replay_is_unchanged():
    spy = Spy()
    rep = R.replay(batch(2), [item(1, "2026-05-04"), item(2, "2026-05-05")], FV, pack=load_pack(PACK), decide=spy, demand=[])
    assert all(a[1] == 0 and a[3] == -1 for a in spy.asked)  # decided one at a time as before, no planner given
    assert rep.constraint_loss == 0.0


def test_x_06_constraint_loss_is_case_by_case_minus_planned():
    """The case-by-case decision (each return alone, every unit on offer) is worth more than the planned one when returns
    compete for one unit: the loss is the difference of the two sums."""

    class Alone(Spy):
        def __call__(self, case, pack, flow_ver, as_of=None, *, queue=None, planner=None, **kw):
            d = super().__call__(case, pack, flow_ver, as_of, queue=queue, planner=planner, **kw)
            return d if len(queue or []) > 1 else _with_net(d, 300.0)  # alone, each return takes the unit at 300

    def _with_net(d: Decision, net: float) -> Decision:
        import dataclasses

        rt = [{**r, "net": net, "p10": net - 5, "p90": net + 5} for r in d.routes]
        return dataclasses.replace(d, net=net, routes=rt, recommendation=rt[0])

    spy = Alone(net=100.0)  # planned: 100 each; alone: 300 each
    rep = R.replay(batch(3), [item(k, "2026-05-04") for k in range(1, 4)], FV, pack=load_pack(PACK), decide=spy,
                   demand=[dem(1, capacity=1)])  # fmt: skip
    assert rep.constraint_loss == 600.0 and rep.n_decided == 3


# ---------------------------------------------------------------- the real decider
def test_x_06_real_decider_planned_never_beats_case_by_case():
    items = [item(k, "2026-05-04", grade="A") for k in range(1, 5)] + [item(9, "2026-05-06", grade="B", cls="CRH")]
    rows = [dem(1, capacity=1, value=1200.0), dem(2, route="refurb", capacity=1), dem(3, route="resell", capacity=1, value=500.0)]
    rep = R.replay(batch(5), items, FV, pack=load_pack(PACK), demand=rows)
    assert rep.n_decided == 5
    assert rep.constraint_loss >= 0.0
    plain = R.replay(batch(5), items, FV, pack=load_pack(PACK))
    assert plain.constraint_loss == 0.0


def test_x_06_real_decider_units_taken_once():
    """Four returns of one class on one day, one lease unit: at most one of them can be placed on it."""
    items = [item(k, "2026-05-04", grade="A") for k in range(1, 5)]
    rep = R.replay(batch(4), items, FV, pack=load_pack(PACK), demand=[dem(1, capacity=1, value=1500.0)])
    assert rep.n_decided == 4
    assert rep.constraint_loss > 0.0


# ---------------------------------------------------------------- the action and the job
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


def history_csv(rows: int = 6) -> str:
    p = load_pack(PACK)
    head = ["item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "cost_logistics", "cost_refurb",
            "cost_test", "cost_fees", "market", "fact.condition", "fact.condition.at"]  # fmt: skip
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(head)
    for k in range(rows):
        w.writerow([f"T{k:03d}", p.classes[0].id, f"2026-05-0{4 + k % 2}", "x", p.routes[k % 3].id, "120", 5, 10, 2, 3, "US",
                    "AB"[k % 2], "2026-04-30T08:00:00"])  # fmt: skip
    return out.getvalue()


def import_batch(pack: str = PACK, csv_text: str | None = None) -> int:
    return ok(call("replay.import", {"pack": pack, "org_unit_id": ORG, "csv": csv_text or history_csv()}, "planner.a"))["id"]


def test_x_06_import_demand_stores_good_rows_and_holds_the_rest(fresh):
    bid = import_batch()
    rows = [drow(1), drow(2, route="scrap"), drow(3, closes_at="2026-04-01"), drow(1)]
    out = ok(call("replay.importDemand", {"batch_id": bid, "csv": dcsv(rows)}, "planner.a"))
    assert (out["demand_rows"], out["demand_held"]) == (1, 3)
    assert [h["held_reason"] for h in out["held_demand"]] == [
        f"Route 'scrap' is not a route of {PACK}.", "Demand closes before it opens.", "Duplicate demand_id.",
    ]  # fmt: skip
    again = ok(call("replay.importDemand", {"batch_id": bid, "csv": dcsv([drow(1), drow(4)])}, "planner.a"))
    assert (again["demand_rows"], again["demand_held"]) == (2, 4)  # appended; D001 repeats
    with SessionLocal() as s:
        n = s.execute(text("SELECT count(*) FROM replay_demand WHERE batch_id = :b AND status = 'ok'"), {"b": bid}).scalar_one()
    assert n == 2


def test_x_06_import_demand_refusals(fresh):
    bid = import_batch()
    body = {"batch_id": bid, "csv": dcsv([drow(1)])}
    r = call("replay.importDemand", body, "exec")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert r["error"]["message"] == "The Executive view reads replay reports; a Planner or Admin runs them."
    r = call("replay.importDemand", body, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    r = call("replay.importDemand", {"batch_id": 999999, "csv": dcsv([drow(1)])}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "not_found"
    r = call("replay.importDemand", {"batch_id": bid, "csv": dcsv([drow(1) | {"customer_email": "x"}])}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error" and "personal data" in r["error"]["message"]
    r = call("replay.importDemand", {"batch_id": bid, "csv": dcsv([], HEAD)}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    device = import_batch("device", _device_csv())
    r = call("replay.importDemand", {"batch_id": device, "csv": dcsv([drow(1)])}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error" and "no queue planner" in r["error"]["message"]


def _device_csv() -> str:
    p = load_pack("device")
    head = ["item_id", "class", "decided_at", "reason", "actual_route", "realised_value"]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(head)
    w.writerow(["D1", p.classes[0].id, "2026-05-04", "x", p.routes[0].id, "100"])
    return out.getvalue()


def test_x_06_replay_job_reports_the_constraint_loss(fresh):
    bid = import_batch()
    ok(call("replay.importDemand", {"batch_id": bid, "csv": dcsv([drow(1, capacity="1"), drow(2, route="refurb", capacity="1")])},
            "planner.a"))  # fmt: skip
    fid = ok(call("flow.fork", {"template_key": PACK, "org_unit_id": ORG}, "planner-a"))["flow_id"]
    out = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
    while worker.run_once():
        pass
    done = ok(call("replay.report", {"run_id": out["run_id"]}, "planner.a"))
    assert done["status"] == "done", done
    assert done["report"]["n_decided"] == 6 and done["report"]["constraint_loss"] >= 0.0
