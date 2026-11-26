# ruff: noqa: E501 - SQL strings and long lines in the docstring
"""Plan 9, P9-10.13 (story TN-20; registry entries I-16 and I-17): the telecom replay history and the 20 percent publish.

The history is `di.services.modeler.replay_samples.telecom_network` (1,260 units over 20 days, `mulberry32(1404)`) and its fixture
file `fixtures/replay/telecom_network.csv`. The replay is the one of plan 9 (`di.services.replay.run`, I-16) with every unit decided
by the one decider (R19); the figures are labelled *modelled*. Publishing is the rollout of P9-7.3 (I-17): a person other than the
flow's maker starts a canary of v1.0 on one region at 20 percent. Every number is code and no text is read or written here, so
the model-first rule (R16) has no output to route.
Legal note: export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import flows as flow_repo
from di.repositories import rollouts
from di.services.modeler import replay_samples
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import telecom_network as G
from di.services.modeler.templates import template_of_pack
from di.services.replay import telecom as T
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call

ORG = "Customer A"
FIXTURES = next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())


@pytest.fixture(scope="module")
def data() -> list[dict[str, str]]:
    return G.rows()


@pytest.fixture(scope="module")
def modelled(data):
    return T.replay(T.items(data))


def test_tn_20_replay_figures_modelled(modelled):
    f = modelled.figures()
    assert modelled.basis == f["basis"] == "modelled"
    assert f["units"] == 1260 and modelled.report.days == 14  # 20 calendar days, 14 business days
    assert 83 <= f["straight_through_pct"] <= 85
    assert 5 <= f["approvals_per_day"] <= 7
    assert 3 <= f["exceptions_per_day"] <= 5
    assert 990_000 <= f["new_spend_avoided"] <= 1_210_000  # $1.1M +- 10 %
    assert modelled.report.n_decided == len(modelled.decided) == 1260


def test_tn_20_rows_deterministic(data):
    assert G.rows() == data and replay_samples.DATASETS["telecom_network"]() == data
    assert len(data) == 1260 and len({r["item_id"] for r in data}) == 1260
    assert G.resales_of_current_cards(data) == 14  # TN-14 needs exactly these
    days = {r["decided_at"][:10] for r in data}
    assert min(days) == "2026-11-05" and max(days) == "2026-11-24" and len(days) == 20
    assert all(sum(r["decided_at"].startswith(d) for r in data) == 63 for d in days)
    text_ = (FIXTURES / "telecom_network.csv").read_text(encoding="utf-8")
    assert text_ == G.csv_text(data) and text_.splitlines()[0] == f"# {G.COMMAND}"
    assert not {"name", "email", "phone", "address"} & set(data[0])  # no personal column


# ---------------------------------------------------------------- the 20 percent publish
@pytest.fixture
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM rollout"))
            s.execute(text("DELETE FROM replay_run"))
            s.execute(text("DELETE FROM replay_batch"))
            s.execute(
                text(
                    "DELETE FROM decision_flow_version WHERE flow_id IN (SELECT id FROM decision_flow WHERE template_key = 'telecom_network')"
                )
            )
            s.execute(text("DELETE FROM decision_flow WHERE template_key = 'telecom_network'"))
            s.commit()

    clean()
    starting.reset()
    flowkit.reset_flows()
    yield
    clean()
    flowkit.reset_flows()
    starting.reset()


def telecom_flow(maker: str = "planner-a") -> int:
    """Customer A's flow of the telecom pack in shadow: v1 published, its draft v2 (one rule) made by `maker` and approved by
    another, with a replay of the draft done. The pack is imported (not one of the three forkable templates), so the row is laid
    as `flow.fork` and `flow.approve` leave it."""
    g = default_flow(template_of_pack(load_pack("telecom_network")))
    with SessionLocal() as s:
        fid = s.execute(
            text(
                "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, dver, maker, checker, draft, published) "
                "VALUES ('telecom_network', :o, 'Telecom network', 'shadow', 1, 2, :m, 'approver', CAST(:d AS jsonb), "
                "CAST(:g AS jsonb)) RETURNING id"
            ),
            {"o": ORG, "m": maker, "d": json.dumps(with_rule(g, "TN-R1", "prefer", "redeploy", {})), "g": json.dumps(g)},
        ).scalar_one()
        s.execute(
            text(
                "INSERT INTO decision_flow_version (flow_id, ver, graph, published_by) VALUES (:f, 1, CAST(:g AS jsonb), 'system')"
            ),
            {"f": fid, "g": json.dumps(g)},
        )
        s.commit()
    with SessionLocal() as s:
        bid = s.execute(
            text(
                "INSERT INTO replay_batch (pack, org_unit_id, rows, held, created_by) "
                "VALUES ('telecom_network', :o, 1260, 0, 't') RETURNING id"
            ),
            {"o": ORG},
        ).scalar_one()
        dver = flow_repo.get_flow(s, fid).dver
        s.execute(
            text(
                "INSERT INTO replay_run (batch_id, flow_id, flow_ver, dver, status, created_by) "
                "VALUES (:b, :f, 'draft', :d, 'done', 't')"
            ),
            {"b": bid, "f": fid, "d": dver},
        )
        s.commit()
    return int(fid)


def test_tn_20_publish_one_region_20_percent(fresh):
    fid = telecom_flow()
    refused = call("rollout.startCanary", {"flow_id": fid, "region": "North", "share": 20}, "planner-a")
    assert not refused.get("ok")  # the maker cannot publish their own changes
    out = ok(call("rollout.startCanary", {"flow_id": fid, "region": "North", "share": 20}, "approver"))
    assert (out["stage"], out["region"], out["share"]) == ("canary", "North", 20)
    north = [{"id": f"TN-N{k:03d}", "market": "North"} for k in range(100)]
    south = [{"id": f"TN-S{k:03d}", "market": "South"} for k in range(100)]
    with SessionLocal() as s:
        f = flow_repo.get_flow(s, fid)
        got_n = [rollouts.version_for(s, c, f) for c in north]
        got_s = [rollouts.version_for(s, c, f) for c in south]
        s.commit()
        counts = rollouts.arm_counts(s, fid)
        journaled = s.execute(text("SELECT count(*) FROM rollout_assignment WHERE case_id LIKE 'TN-N%'")).scalar_one()
        other = s.execute(text("SELECT count(*) FROM rollout_assignment WHERE case_id LIKE 'TN-S%'")).scalar_one()
    on_new = [g for g in got_n if g == ("draft", "canary")]
    assert 15 <= len(on_new) <= 25  # 20 of 100 North cases +- 5
    assert all(g in (("draft", "canary"), (1, "control")) for g in got_n)
    assert all(g == (1, "out") for g in got_s)  # the other region stays on the published version
    assert counts == {"canary": len(on_new), "control": 100 - len(on_new)} and journaled == 100 and other == 0
