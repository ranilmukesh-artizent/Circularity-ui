"""P9-8.20 (G C7-C10; story X-10 enabler; registry entries I-7, I-17): the Compose agent mapping, approve and publish steps.

`compose.setStageAgents` stores the seven stage settings as typed `stageAgent.set` operations (and one `param.set` for the
confidence threshold) beside the overlay's operations; `compose.publish` is a person's commit on an approved composition: it
needs a replay report and starts P9-7.3's canary through the pipeline as the same person; `compose.history` reads the versions
and the journal. Every model is absent here (the deterministic path, R16): the one wording, the summary of the replay report,
is covered with a `FunctionModel` in the last tests."""

# ruff: noqa: E501 - long lines in fixtures and asserts
import json
from decimal import Decimal

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents import chain, runtime
from di.services.agents.forbidden import forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.agents.stage_context import StageContext
from di.services.modeler.pack import load_pack
from tests import flowkit, starting
from tests.helpers import call, client, h
from tests.test_composition import ORG, ROW, SID, _prompt, _row, _set_steps, ok
from tests.test_rollout import shadow_flow

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

NEEDS_REPORT = "Run the replay before publishing."
BOUNDS = "The confidence threshold is between 65 % and 85 %."
REPORT = {
    "run_id": 1, "batch_id": 1, "flow_ver": "draft", "n_items": 40, "n_held_rows": 2, "n_decided": 38, "days": 20,
    "route_mix": [{"route": "redeploy", "actual_pct": 40.0, "flow_pct": 55.0}, {"route": "resell", "actual_pct": 60.0, "flow_pct": 45.0}],
    "straight_through_pct": 62.5, "approvals_per_day": 3.2, "exceptions_per_day": 0.4,
    "uplift": {"primary": 2.8, "band80": [-1.0, 5.4], "band95": [-2.0, 6.5], "secondary": 2.1, "bias": 1.0,
               "conservative": 2.1, "basis": "modelled"},
}  # fmt: skip
STAGES = [st.key for st in load_pack("tool_fleet").stages]


def _reset() -> None:
    with engine.begin() as conn:
        for t in ("rollout", "replay_run", "replay_batch", "composition_version", "composition", "customer_overlay"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
        mine = (
            "SELECT seq FROM action_journal WHERE action LIKE 'compose.%' OR action LIKE 'overlay.%' OR action LIKE 'rollout.%'"
        )
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    starting.reset()
    flowkit.reset_flows()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path
    yield
    runtime.set_loop(None)
    _reset()
    flowkit.reset_flows()
    starting.reset()


def stages(autonomy: str = "limits", **by_stage: str) -> list[dict]:
    pack = load_pack("tool_fleet")
    rows = []
    for st in pack.stages:
        a = by_stage.get(st.key, autonomy)
        rows.append(
            {"stage": st.key, "agent_id": st.agent, "autonomy": a}
            | ({"limits": {"value_limit": 600, "bulk_limit": 10}} if a == "limits" else {})
        )
    return rows


def draft(user: str = "planner-a") -> int:
    out = ok(call("compose.start", {"org_unit_id": ORG, "text": _prompt(), "pack_key": "tool_fleet"}, user))
    ok(call("compose.answer", {"id": out["id"], "answer": out["change_set"]["question"]["options"][0]["id"]}, user))
    _set_steps(out["id"], {"mapping": {"fields": [{"source_id": SID, "row": ROW, "state": "accepted"}]}})
    return int(out["id"])


def approved(user: str = "planner-a", **by_stage: str) -> int:
    cid = draft(user)
    ok(call("compose.setStageAgents", {"id": cid, "stages": stages(**by_stage), "threshold": 0.8}, user))
    for step in ("describe", "mapping", "agents"):
        ok(call("compose.markStep", {"id": cid, "step": step}, user))
    ok(call("compose.submit", {"id": cid}, user))
    ok(call("compose.approve", {"id": cid}, "approver"))
    return cid


def with_report(fid: int, report: dict | None = REPORT) -> None:
    """A done replay of the flow's draft with its report, stored as the replay job leaves it."""
    with SessionLocal() as s:
        bid = s.execute(
            text(
                "INSERT INTO replay_batch (pack, org_unit_id, rows, held, created_by) VALUES ('tool_fleet', :o, 0, 0, 't') RETURNING id"
            ),
            {"o": ORG},
        ).scalar_one()
        dver = s.execute(text("SELECT dver FROM decision_flow WHERE id = :f"), {"f": fid}).scalar_one()
        s.execute(
            text(
                "INSERT INTO replay_run (batch_id, flow_id, flow_ver, dver, status, report, created_by) "
                "VALUES (:b, :f, 'draft', :d, 'done', CAST(:r AS jsonb), 't')"
            ),
            {"b": bid, "f": fid, "d": dver, "r": json.dumps(report)},
        )
        s.commit()


def publish(cid: int, region: str = ORG, share: int | None = None, user: str = "approver") -> dict:
    return call("compose.publish", {"id": cid, "region": region} | ({"share": share} if share is not None else {}), user)


# ---------------------------------------------------------------- compose.setStageAgents
def test_compose_stage_agents_threshold_bounds():
    cid = draft()
    for bad in (0.60, 0.90):
        r = call("compose.setStageAgents", {"id": cid, "stages": stages(), "threshold": bad}, "planner-a")
        assert r["ok"] is False and r["error"]["code"] == "validation_error" and r["error"]["message"] == BOUNDS, r
    assert _row(cid)["steps"]["agents"].get("settings") is None
    out = ok(call("compose.setStageAgents", {"id": cid, "stages": stages(), "threshold": 0.80}, "planner-a"))
    row = _row(cid)
    ops = row["change_set"]["stage_ops"]
    assert [o["op"] for o in ops].count("stageAgent.set") == len(STAGES) == 7
    assert [o for o in ops if o["op"] == "param.set"] == [
        {"id": "sa-8", "op": "param.set", "path": "confidence_threshold", "value": 0.8}
    ]
    assert [s["stage"] for s in row["steps"]["agents"]["settings"]] == STAGES
    assert {s["threshold"] for s in row["steps"]["agents"]["settings"]} == {0.8} and out["threshold"] == 0.8
    assert row["steps"]["agents"]["settings"][0]["limits"] == {"value_limit": 600, "bulk_limit": 10}
    assert (
        row["change_set"]["ops"] == ok(call("compose.get", {"id": cid}, "planner-a"))["change_set"]["ops"]
    )  # the overlay's own ops stay


def test_compose_stage_agents_refuses_what_the_pack_does_not_have():
    cid = draft()
    one = stages()[0]
    cases = [
        ([{**one, "autonomy": "full"}], "autonomy"), ([{**one, "stage": "launch"}], "stage"), ([one, one], "twice"), ([], "stage"),
        ([{**one, "agent_id": ""}], "agent"), ([{**one, "limits": {"value_limit": -1}}], "limit"),
    ]  # fmt: skip
    for rows, word in cases:
        r = call("compose.setStageAgents", {"id": cid, "stages": rows, "threshold": 0.75}, "planner-a")
        assert r["ok"] is False and r["error"]["code"] == "validation_error" and word in r["error"]["message"].lower(), (rows, r)
    ok(call("compose.markStep", {"id": cid, "step": "describe"}, "planner-a"))
    assert (
        call("compose.setStageAgents", {"id": cid, "stages": stages(), "threshold": 0.75}, "approver")["error"]["code"]
        == "out_of_scope"
    )


def test_compose_stage_agents_locked_after_submit_and_in_tenant():
    cid = approved()
    r = call("compose.setStageAgents", {"id": cid, "stages": stages(), "threshold": 0.75}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    other = int(
        ok(call("compose.start", {"org_unit_id": "Customer B", "text": _prompt(), "pack_key": "tool_fleet"}, "admin"))["id"]
    )
    r = call("compose.setStageAgents", {"id": other, "stages": stages(), "threshold": 0.75}, "planner-a")
    assert r["error"]["code"] == "tenant_boundary"


# ---------------------------------------------------------------- compose.publish
def test_compose_publish_needs_replay_report():
    cid = approved()
    fid = shadow_flow("tool_fleet", "planner-a")
    r = publish(cid)
    assert r["ok"] is False and r["error"]["code"] == "conflict" and r["error"]["message"] == NEEDS_REPORT, r
    with_report(fid, None)  # a done run that holds no report is no report
    assert publish(cid)["error"]["message"] == NEEDS_REPORT
    assert _row(cid)["status"] == "approved"


def test_compose_publish_needs_an_approved_composition_and_a_flow():
    cid = draft()
    r = publish(cid)
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "approved" in r["error"]["message"]
    done = approved()
    r = publish(done)  # approved, but the org has no decision flow in shadow
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "shadow" in r["error"]["message"], r
    fid = shadow_flow("tool_fleet", "planner-a")
    with_report(fid)
    assert publish(done, share=100)["error"]["code"] == "validation_error"
    assert publish(done, share=0)["error"]["code"] == "validation_error"
    assert call("compose.publish", {"id": done, "region": " "}, "approver")["error"]["code"] == "validation_error"


def test_compose_publish_starts_canary():
    cid = approved()
    fid = shadow_flow("tool_fleet", "planner-a")
    with_report(fid)
    out = ok(publish(cid, ORG, 20))
    assert (
        out["status"] == "published"
        and out["rollout"]["stage"] == "canary"
        and (out["rollout"]["region"], out["rollout"]["share"]) == (ORG, 20)
    )
    assert out["report"]["straight_through_pct"] == 62.5 and out["report"]["uplift"]["band80"] == [-1.0, 5.4]
    row = _row(cid)
    assert row["status"] == "published" and row["published_by"] == "approver" and row["steps"]["publish"]["state"] == "done"
    rollout = ok(call("rollout.get", {"flow_id": fid}, "approver"))
    assert rollout["stage"] == "canary" and [(r["region"], r["share"]) for r in rollout["rollouts"]] == [(ORG, 20)]
    with SessionLocal() as s:
        acts = list(
            s.execute(
                text(
                    "SELECT action, actor FROM action_journal WHERE action IN ('compose.publish', 'rollout.startCanary') ORDER BY seq"
                )
            )
        )
        versions = list(
            s.execute(
                text("SELECT status FROM composition_version WHERE composition_id = :c ORDER BY version"), {"c": cid}
            ).scalars()
        )
    assert acts == [("rollout.startCanary", "approver"), ("compose.publish", "approver")] or acts == [
        ("compose.publish", "approver"),
        ("rollout.startCanary", "approver"),
    ]
    assert versions[-1] == "published"
    again = publish(cid)
    assert again["ok"] is False and again["error"]["code"] == "conflict"  # published once


def test_compose_publish_default_share_is_twenty():
    cid = approved()
    with_report(shadow_flow("tool_fleet", "planner-a"))
    assert ok(publish(cid))["rollout"]["share"] == 20


def test_compose_publish_agent_refused():
    assert forbidden("compose.publish") and forbidden("compose.setStageAgents") is False
    cid = approved()
    with_report(shadow_flow("tool_fleet", "planner-a"))
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/compose.publish", json={"id": cid, "region": ORG}, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    assert _row(cid)["status"] == "approved"
    with SessionLocal() as s:
        assert not s.execute(text("SELECT 1 FROM rollout")).first()


def test_compose_publish_tenant_boundary():
    cid = approved()
    with_report(shadow_flow("tool_fleet", "planner-a"))
    r = publish(cid, "Customer B")  # an org unit that is not under the composition's own
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert _row(cid)["status"] == "approved"
    assert ok(publish(cid, "FR"))["rollout"]["region"] == "FR"  # a market is a case fact, not an org unit


def test_compose_publish_maker_cannot_publish_their_own_flow_rollout():
    cid = approved()
    fid = shadow_flow("tool_fleet", "admin")  # the publisher made the flow's changes: the rollout's maker-checker refuses
    with_report(fid)
    r = publish(cid, user="admin")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "Maker-checker" in r["error"]["message"], r
    assert _row(cid)["status"] == "approved"
    with SessionLocal() as s:
        assert not s.execute(text("SELECT 1 FROM rollout")).first()


def test_compose_recommend_stage_holds():
    cid = approved(condition="recommend")
    with_report(shadow_flow("tool_fleet", "planner-a"))
    ok(publish(cid))
    settings = _row(cid)["steps"]["agents"]["settings"]
    from di.services.actions.compose import with_stage_settings

    pack = with_stage_settings(load_pack("tool_fleet"), settings)
    defn = next(d for d in chain.stage_defs(pack) if d.id == "condition")
    assert (defn.autonomy, defn.threshold) == ("recommend", 0.8)
    st = StageContext(
        stage="condition",
        autonomy=defn.autonomy,
        confidence=0.99,
        threshold=defn.threshold,
        value=Decimal(100),
        value_limit=None,
        bulk_limit=None,
    )
    with SessionLocal() as s:
        pc = load_context(s)
        ctx = CallContext(
            actor=Actor(account=policy.account("planner-a", pc), ctx=pc), session=s, preparer="stage-condition", stage=st
        )
        r = invoke("decision.submit", {"case_id": "RT-1048"}, ctx)
        s.commit()
    assert r["ok"] is True and "held" in r["output"], r
    assert [x["reason"] for x in r["output"]["reasons"]] == ["autonomy"]
    assert r["output"]["reasons"][0]["detail"] == "Condition is set to Recommend only"


# ---------------------------------------------------------------- compose.history
def test_compose_history_lists_versions_and_journal():
    cid = approved()
    h0 = ok(call("compose.history", {"id": cid}, "approver"))
    assert [v["status"] for v in h0["versions"]] == ["submitted", "approved"] and h0["versions"][-1]["by"] == "approver"
    assert all(v["at"] for v in h0["versions"]) and h0["publish"]["report"] is None and h0["publish"]["flow_status"] != "shadow"
    assert {"compose.start", "compose.submit", "compose.approve"} <= {j["action"] for j in h0["journal"]}
    assert all(j["actor"] and j["at"] for j in h0["journal"])
    assert [r["stage"] for r in h0["stages"]] == STAGES and h0["threshold"] == 0.8
    assert {r["autonomy"] for r in h0["stages"]} == {"limits"} and h0["stages"][0]["limits"] == {
        "value_limit": 600,
        "bulk_limit": 10,
    }
    fresh_stages = ok(call("compose.history", {"id": draft()}, "planner-a"))
    assert fresh_stages["threshold"] == 0.75 and [r["stage"] for r in fresh_stages["stages"]] == STAGES
    fid = shadow_flow("tool_fleet", "planner-a")
    with_report(fid)
    pre = ok(call("compose.history", {"id": cid}, "approver"))["publish"]
    assert (
        pre["flow_id"] == fid
        and pre["flow_stage"] == "shadow"
        and pre["report"]["straight_through_pct"] == 62.5
        and pre["rollouts"] == []
    )
    ok(publish(cid))
    post = ok(call("compose.history", {"id": cid}, "approver"))
    assert [v["status"] for v in post["versions"]][-1] == "published"
    assert {"compose.publish", "rollout.startCanary"} <= {j["action"] for j in post["journal"]}
    assert [(r["region"], r["share"]) for r in post["publish"]["rollouts"]] == [(ORG, 20)] and post["publish"][
        "flow_stage"
    ] == "canary"
    assert call("compose.history", {"id": cid}, "exec")["error"]["code"] == "out_of_scope"


# ---------------------------------------------------------------- the wording (R16)
def _model(words: list[str]):
    seen = iter(words)

    def fn(_m, info: AgentInfo) -> ModelResponse:
        tool = next(t for t in info.output_tools)
        return ModelResponse(parts=[ToolCallPart(tool.name, {"summary": next(seen)})])

    return FunctionModel(fn)


def _run_with(model, words: list[str]) -> dict:
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: _model(words) if model else None))
    cid = approved()
    with_report(shadow_flow("tool_fleet", "planner-a"))
    return ok(publish(cid))


def test_compose_publish_wording_accepted_from_the_model():
    out = _run_with(True, ["The replay put 62.5 % of items straight through, with 3.2 approvals a day."])
    assert out["by_model"] is True and out["text"].startswith("The replay put 62.5 %")


def test_compose_publish_wording_refused_then_retried_then_kept():
    out = _run_with(True, ["Straight through 99 %.", "It will surely pay 12345."])
    assert out["by_model"] is False and "62.5" in out["text"] and "12345" not in out["text"]


def test_compose_publish_wording_retried_then_accepted():
    out = _run_with(True, ["Straight through 99 %.", "Straight through is 62.5 %."])
    assert out["by_model"] is True and out["text"] == "Straight through is 62.5 %."


def test_compose_publish_wording_without_a_model_is_composed_from_the_report():
    out = _run_with(False, [])
    assert out["by_model"] is False and "62.5" in out["text"] and "3.2" in out["text"] and "0.4" in out["text"]
