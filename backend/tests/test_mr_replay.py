"""P9-11.13 (story MR-20; registry entries I-16 and I-17): the medical pack's replay history and the 20 percent publish.

The history is invented by `replay_samples.medical_rental` (mulberry32(1606)); every figure is a counterfactual estimate, so
`modelled`. The numbers come from code (the replay measures); no text is read or written here, so R16 has no output to route.
Publishing stays a person's: the canary is started by someone other than the flow's author (maker-checker).
"""

import csv
import io
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import flows as flow_repo
from di.repositories import rollouts
from di.repositories.replay import Batch
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import DATASETS
from di.services.modeler.replay_samples import medical_rental as M
from di.services.replay import run
from tests import flowkit, starting
from tests.flowkit import ok
from tests.helpers import call

FIXTURES = next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())
NOW = datetime(2026, 11, 24, tzinfo=UTC)
ORG = "Customer A"


@pytest.fixture(scope="module")
def history():
    pack = load_pack("medical_rental")
    rows = M.rows()
    its = M.items(rows, pack, NOW)
    batch = Batch(1, "medical_rental", ORG, len(its), 0, None, {})
    return rows, its, M.replay(batch, its, FlowVersion(1, 1, ()), pack, run.replay)


def test_mr_20_rows_deterministic():
    a, b = M.rows(), M.rows()
    assert a == b and len(a) == 1880
    assert M.csv_text(a) == (FIXTURES / "medical_rental.csv").read_text(encoding="utf-8")  # the shipped file is the generator's
    days = {r["decided_at"][:10] for r in a}
    assert min(days) == "2026-10-28" and max(days) == "2026-11-23" and len(days) == 27
    per_day = Counter(r["decided_at"][:10] for r in a)
    assert all(65 <= n <= 75 for n in per_day.values())  # about 70 a day
    young = [r for r in a if r["actual_route"] == "retire" and int(r["fact.age_years"]) < 5]
    assert len(young) == 11  # MR-11
    head = next(csv.reader(io.StringIO(M.csv_text(a).split("\n", 1)[1])))
    assert not any(w in h.lower() for h in head for w in ("name", "address", "patient", "email", "phone", "dob"))
    assert DATASETS["medical_rental"] == M.__name__
    assert M.csv_text(a).startswith(f"# {M.COMMAND}\n")


def test_mr_20_replay_figures_modelled(history):
    _rows, its, (report, fig) = history
    pack = load_pack("medical_rental")
    assert len(its) == 1880 and report.n_decided == 1880 and report.days == 19  # business days of the 27
    assert {k: v["basis"] for k, v in fig.items()} == dict.fromkeys(M.FIGURE_NAMES, "modelled")
    v = {k: x["value"] for k, x in fig.items()}
    assert abs(v["straight_through_pct"] - 83) <= 1
    assert abs(v["approvals_per_day"] - 7) <= 1
    assert abs(v["exceptions_per_day"] - 5) <= 1
    assert abs(v["utilisation_points"] - 6) <= 1
    stated = (pack.replay.example or {})["modelled"]
    assert stated["devices"] == 1880 and stated["straight_through_pct"] == 83
    mix = {m["route"]: m for m in report.route_mix}  # route mix, actual against flow: the flow moves devices to other routes
    assert set(mix) == {"rerent", "service_rerent", "refurbish", "retire"}
    assert mix["service_rerent"]["actual_pct"] > mix["service_rerent"]["flow_pct"]
    assert 90 < sum(m["flow_pct"] for m in mix.values()) <= 100.5  # the rest is held for a person (no route yet)


def test_mr_20_the_replay_decides_a_row_as_decide_case_does(history):
    """Replay and the live decider give one route and one net for the same facts (R19)."""
    from di.services.cases.decide import decide_case

    _rows, its, _ = history
    pack = load_pack("medical_rental")
    got: list = []

    def decide(*a, **k):
        got.append(decide_case(*a, **k))
        return got[-1]

    sample = its[:12]
    run.replay(Batch(1, "medical_rental", ORG, 12, 0, None, {}), sample, FlowVersion(1, 1, ()), pack=pack, decide=decide)
    assert len(got) == 12
    again: list = []
    run.replay(Batch(1, "medical_rental", ORG, 12, 0, None, {}), sample, FlowVersion(1, 1, ()), pack=pack,
               decide=lambda *a, **k: again.append(decide_case(*a, **k)) or again[-1])  # fmt: skip
    assert [(d.route, d.net) for d in got] == [(d.route, d.net) for d in again]
    assert all(d.route is None or d.route in {r.id for r in pack.routes} | {r["id"] for r in d.routes} for d in got)


def test_mr_20_facts_are_dated_before_the_decision(history):
    _rows, its, _ = history
    assert all(f["at"] < it["decided_at"] for it in its for f in it["facts"].values())
    assert all(it["decided_at"].date() >= date(2026, 10, 28) for it in its)


@pytest.fixture
def clean():
    def wipe() -> None:
        with SessionLocal() as s:
            for t in ("rollout", "replay_run", "replay_batch"):
                s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed table names
            s.commit()

    wipe()
    starting.reset()
    flowkit.reset_flows()
    yield
    wipe()
    flowkit.reset_flows()
    starting.reset()


def test_mr_20_publish_one_region_20_percent(clean):
    """v1.0 goes to the East region at 20 percent; the author cannot start it, someone else does (maker-checker).

    `flow.fork` takes only the three template keys (`TEMPLATE_KEYS`), so no stored flow of the medical pack exists to publish
    yet: the step's settings (`M.CANARY`) go through the real action on a flow that can be forked, and the assignment is
    checked on the medical settings alone."""
    from tests.test_rollout import MAKER_TEXT, replay_done, shadow_flow

    step = M.CANARY
    assert (step["version"], step["region_key"], step["region"], step["share"]) == ("1.0", "region", "East", 20)
    fid = shadow_flow("tool_fleet", maker="admin")
    replay_done(fid, real=False)
    body = {"flow_id": fid, "region": step["region"], "region_key": step["region_key"], "share": step["share"]}
    refused = call("rollout.startCanary", body, "admin")  # the author
    assert not refused.get("ok") and refused["error"]["code"] == "conflict" and refused["error"]["message"] == MAKER_TEXT
    out = ok(call("rollout.startCanary", body, "approver"))
    assert (out["stage"], out["region_key"], out["region"], out["share"]) == ("canary", "region", "East", 20)
    with SessionLocal() as s:
        rows = rollouts.rollouts_of(s, fid)
        r = rows[0]
        assert [(x.region, x.share, x.stage) for x in rows] == [("East", 20, "canary")]
        east = [rollouts.version_for(s, {"id": f"MR-E{k:04d}", "owner": ORG, "region": "East"}, flow_repo.get_flow(s, fid))
                for k in range(400)]  # fmt: skip
        west = [rollouts.version_for(s, {"id": f"MR-W{k:04d}", "owner": ORG, "region": "West"}, flow_repo.get_flow(s, fid))
                for k in range(100)]  # fmt: skip
        s.commit()
    share = sum(1 for _v, arm in east if arm == "canary") / 400
    assert 0.12 <= share <= 0.28 and r.share == 20  # 20 percent of one region, within sampling
    assert all(arm != "canary" for _v, arm in west)  # no other region
