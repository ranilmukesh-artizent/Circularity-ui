"""Set up's agents step and the Agents page are one thing (28 Nov 2026): the stage settings of an approved composition
(`compose.setStageAgents`) are what the stage chain runs with for that pack and org unit, `compose.history` names the registry
agents that run each pack stage (`runs_as`), and the Agents screen lists the setups under their pack.

No model is involved (the deterministic path): the settings are data. With no approved composition the chain reads the pack
alone, as before.
"""

# ruff: noqa: E501 - long lines in fixtures and asserts
import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import compositions
from di.services.actions import compose as compose_actions
from di.services.agents import chain, runtime
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler import compose as core
from di.services.modeler.pack import load_pack
from tests import flowkit, starting
from tests.helpers import call, client, h
from tests.test_composition import ORG, ok
from tests.test_composition_publish import _reset, approved, draft, stages

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

CASE = "RT-1048"  # industrial, owned by Customer A


def _clean_runs() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    starting.reset()
    flowkit.reset_flows()
    _clean_runs()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path
    yield
    runtime.set_loop(None)
    _reset()
    _clean_runs()
    flowkit.reset_flows()
    starting.reset()


def _insert(pack: str, org: str, status: str, settings: list[dict]) -> int:
    """A composition row as `compose.approve` leaves it, for a pack whose Describe step these tests do not walk."""
    steps = core.new_steps() | {"agents": {"state": "done", "settings": settings}}
    with SessionLocal() as s:
        cid = s.execute(
            text(
                "INSERT INTO composition (org_unit_id, pack_key, base_version, text, reading, change_set, steps, status, "
                "created_by, editors, created_at, updated_at) VALUES (:o, :p, :v, 't', '{}'::jsonb, '{}'::jsonb, "
                "CAST(:s AS jsonb), :st, 'planner-a', :ed, now(), now()) RETURNING id"
            ),
            {"o": org, "p": pack, "v": load_pack(pack).version, "s": json.dumps(steps), "st": status, "ed": ["planner-a"]},
        ).scalar_one()
        s.commit()
    return int(cid)


def _settings(threshold: float = 0.8, **by_stage: dict) -> list[dict]:
    return [{"stage": k, "agent_id": k.title(), "threshold": threshold, **v} for k, v in by_stage.items()]


# ---------------------------------------------------------------- the pure part
def test_stage_defs_without_settings_is_the_pack():
    for key in ("industrial", "tool_fleet", "device"):
        pack = load_pack(key)
        assert chain.stage_defs(pack, []) == chain.stage_defs(pack) == chain.stage_defs(pack, ())
        assert all(d.value_limit is None and d.bulk_limit is None for d in chain.stage_defs(pack))


def test_stage_defs_takes_autonomy_threshold_and_limits_from_the_settings():
    pack = load_pack("tool_fleet")
    settings = _settings(
        0.8,
        condition={"autonomy": "recommend"},
        decide={"autonomy": "limits", "limits": {"value_limit": 600, "bulk_limit": 10}},
        receive={"autonomy": "alone", "limits": {"value_limit": 5}},  # limits count only for Act within limits
    )
    base = {d.id: d for d in chain.stage_defs(pack)}
    got = {d.id: d for d in chain.stage_defs(pack, settings)}
    assert (got["condition"].autonomy, got["condition"].threshold) == ("recommend", 0.8)
    d = got["disposition"]
    assert (d.autonomy, d.threshold, d.value_limit, d.bulk_limit) == ("limits", 0.8, Decimal(600), 10)
    assert (got["intake"].autonomy, got["intake"].threshold, got["intake"].value_limit) == ("alone", 0.8, None)
    # the lifecycle stages take the receive stage's threshold, their autonomy stays the D1 default
    assert got["transit"].threshold == 0.8 and got["transit"].autonomy == base["transit"].autonomy
    # a stage the settings do not name is as the pack has it; the registry agent of a stage never changes
    assert got["valuation"] == base["valuation"]
    assert [x.agent_id for x in got.values()] == list(chain.AGENT_IDS.values())
    assert compose_actions.with_stage_settings is core.with_stage_settings  # the re-export


def test_agents_of_inverts_the_chain_tables():
    assert chain.agents_of("receive") == ["stage-lease", "stage-return", "stage-transit", "stage-intake"]
    assert chain.agents_of("condition") == ["stage-condition"]
    assert chain.agents_of("match") == ["stage-demand", "stage-fit"]
    assert chain.agents_of("close") == ["stage-outcome", "stage-reconcile"]
    every = [a for k in ("receive", "condition", "match", "value", "decide", "execute", "close") for a in chain.agents_of(k)]
    assert every == list(chain.AGENT_IDS.values())


# ---------------------------------------------------------------- the read
def test_approved_stage_settings_reads_the_newest_approved_or_published():
    with SessionLocal() as s:
        assert compositions.approved_stage_settings(s, "tool_fleet", ORG) == []
    cid = draft()
    ok(call("compose.setStageAgents", {"id": cid, "stages": stages(), "threshold": 0.8}, "planner-a"))
    with SessionLocal() as s:
        assert compositions.approved_stage_settings(s, "tool_fleet", ORG) == []  # a draft sets nothing
    first = _insert("tool_fleet", ORG, "approved", _settings(0.7, condition={"autonomy": "recommend"}))
    with SessionLocal() as s:
        got = compositions.approved_stage_settings(s, "tool_fleet", ORG)
        assert [(x["stage"], x["autonomy"], x["threshold"]) for x in got] == [("condition", "recommend", 0.7)]
        assert compositions.approved_stage_settings(s, "tool_fleet", "Customer B") == []  # exactly that org unit
        assert compositions.approved_stage_settings(s, "industrial", ORG) == []  # exactly that pack
    newer = _insert("tool_fleet", ORG, "published", _settings(0.85, decide={"autonomy": "alone"}))
    _insert("tool_fleet", ORG, "submitted", _settings(0.66, decide={"autonomy": "recommend"}))  # not approved: ignored
    assert newer > first
    with SessionLocal() as s:
        got = compositions.approved_stage_settings(s, "tool_fleet", ORG)
        assert [(x["stage"], x["autonomy"], x["threshold"]) for x in got] == [("decide", "alone", 0.85)]


def test_approved_composition_through_the_actions_is_read():
    cid = approved(condition="recommend")
    with SessionLocal() as s:
        got = {x["stage"]: x for x in compositions.approved_stage_settings(s, "tool_fleet", ORG)}
        row = [r for r in compositions.setups(s) if r["composition_id"] == cid]
    assert got["condition"]["autonomy"] == "recommend" and got["decide"]["limits"] == {"value_limit": 600, "bulk_limit": 10}
    assert [(r["org_unit_id"], r["pack_key"], r["status"]) for r in row] == [(ORG, "tool_fleet", "approved")]


# ---------------------------------------------------------------- run time
def _drive(monkeypatch) -> tuple[dict, list]:
    seen: list = []
    real = runtime.invoke

    def spy(action, i, ctx):
        seen.append((action, ctx.preparer, ctx.stage))
        return real(action, i, ctx)

    monkeypatch.setattr(runtime, "invoke", spy)
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", CASE, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
        recs = {r.stage: r for r in chain.records_of(s, run_id)}
    return recs, seen


def test_chain_without_a_setup_runs_as_the_pack_says(monkeypatch):
    _insert("industrial", "Customer B", "approved", _settings(0.8, condition={"autonomy": "recommend"}))  # another org's
    _insert("industrial", ORG, "submitted", _settings(0.8, condition={"autonomy": "recommend"}))  # not approved
    recs, seen = _drive(monkeypatch)
    want = {d.id: d for d in chain.stage_defs(load_pack("industrial"))}
    assert all((r.autonomy, r.threshold) == (want[k].autonomy, want[k].threshold) for k, r in recs.items())
    st = next(c for a, _p, c in seen if a == "decision.submit")
    assert (st.autonomy, st.threshold, st.value_limit, st.bulk_limit) == ("limits", 0.75, None, None)


def test_chain_runs_with_the_stage_settings_of_the_orgs_setup(monkeypatch):
    _insert(
        "industrial", ORG, "approved",
        _settings(
            0.8, receive={"autonomy": "alone"}, condition={"autonomy": "recommend"},
            decide={"autonomy": "limits", "limits": {"value_limit": 600, "bulk_limit": 10}},
        ),
    )  # fmt: skip
    recs, seen = _drive(monkeypatch)
    assert (recs["intake"].autonomy, recs["intake"].threshold) == ("alone", 0.8)
    assert (recs["condition"].autonomy, recs["condition"].threshold) == ("recommend", 0.8)
    assert recs["valuation"].threshold == 0.75  # a stage the setup does not name keeps the pack's
    preparer, st = next((p, c) for a, p, c in seen if a == "decision.submit")
    assert preparer == "stage-disposition"  # the registry agent of the stage is the chain's, whatever the label says
    assert (st.autonomy, st.threshold, st.value_limit, st.bulk_limit) == ("limits", 0.8, Decimal(600), 10)


# ---------------------------------------------------------------- compose.history: runs_as
def test_history_names_the_registry_agents_of_each_stage():
    cid = approved()
    out = ok(call("compose.history", {"id": cid}, "approver"))
    rows = {r["stage"]: r for r in out["stages"]}
    assert set(out["stages"][0]) == {"stage", "label", "agent_id", "autonomy", "limits", "runs_as"}
    assert rows["receive"]["runs_as"][-1] == {"id": "stage-intake", "name": "Intake agent", "enabled": True, "autonomy": "act"}
    assert [a["id"] for a in rows["receive"]["runs_as"]] == chain.agents_of("receive")
    assert [a["id"] for a in rows["condition"]["runs_as"]] == ["stage-condition"]
    assert all(set(a) == {"id", "name", "enabled", "autonomy"} for r in out["stages"] for a in r["runs_as"])
    with SessionLocal() as s:  # the composition wrote nothing to the registry
        assert set(s.execute(text("SELECT autonomy FROM agent_identity WHERE id LIKE 'stage-%'")).scalars()) == {"act"}


def test_runs_as_lists_an_agent_the_registry_does_not_hold():
    assert compose_actions._runs_as("condition", {}) == [
        {"id": "stage-condition", "name": None, "enabled": False, "autonomy": None}
    ]


# ---------------------------------------------------------------- the Agents screen: setups
def test_agents_screen_lists_the_setups_under_their_pack():
    before = {p["key"]: p for p in client.get("/api/screens/agents", headers=h("admin")).json()["packs"]}
    assert all(p["setups"] == [] for p in before.values())
    cid = approved(condition="recommend")
    _insert("tool_fleet", ORG, "draft", _settings(0.7, condition={"autonomy": "alone"}))  # a draft is not a setup
    packs = {p["key"]: p for p in client.get("/api/screens/agents", headers=h("admin")).json()["packs"]}
    assert packs["industrial"]["setups"] == [] and packs["tool_fleet"]["stages"] == before["tool_fleet"]["stages"]
    (setup,) = packs["tool_fleet"]["setups"]
    assert (setup["composition_id"], setup["org_unit_id"], setup["status"]) == (cid, ORG, "approved")
    assert set(setup) == {"composition_id", "org_unit_id", "status", "stages"}
    assert [s["stage"] for s in setup["stages"]] == list(chain.AGENT_IDS)
    by = {s["stage"]: s for s in setup["stages"]}
    assert by["condition"] == {"stage": "condition", "agent": "stage-condition", "autonomy": "recommend", "threshold": 0.8}
    assert {s["threshold"] for s in setup["stages"]} == {0.8}
    newer = _insert("tool_fleet", "Customer B", "published", _settings(0.7, decide={"autonomy": "alone"}))
    got = client.get("/api/screens/agents", headers=h("developer")).json()["packs"]
    setups = next(p for p in got if p["key"] == "tool_fleet")["setups"]
    assert [(x["composition_id"], x["status"]) for x in setups] == [(newer, "published"), (cid, "approved")]  # newest first
