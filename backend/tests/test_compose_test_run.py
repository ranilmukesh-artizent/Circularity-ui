"""P9-8.19 (G C6; story X-10 enabler; registry entry I-16): the Compose test run puts the org's past items through the draft
flow and shows where cases stopped. A read: it writes no case, journal or shadow row and never publishes or approves.

The grouping is pure (`di.services.modeler.stop_reasons`); the action builds the traces from `decide_case` results (R19). The
plain-language "why it stopped" runs on the model through AgentLoop with code-checked facts (R16): tests use a `FunctionModel`
(accepted, refused then deterministic, retried then accepted) and no model."""

# ruff: noqa: E501 - long lines in fixtures and asserts
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import replay as replay_repo
from di.services.agents import runtime
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases.decide import decide_case
from di.services.modeler import stop_reasons as sr
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from di.services.replay import run as replay_run
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG, PACK = "Customer A", "tool_fleet"
CSV = (
    next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())
    / "tool_fleet_returns.csv"
)
GRADE_ROW = ["GRADE", "", "condition.grade", "", "code:grade"]
TABLES = ("case_record", "case_stage_log", "action_journal", "shadow_decision", "work_item", "replay_run", "composition_version")


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM replay_batch"))
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        conn.execute(text("DELETE FROM customer_overlay"))
        mine = "SELECT seq FROM action_journal WHERE action LIKE 'compose.%' OR action LIKE 'replay.%'"
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path
    yield
    runtime.set_loop(None)
    _reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _composition() -> int:
    return ok(call("compose.start", {"org_unit_id": ORG, "text": load_pack(PACK).prompts[0], "pack_key": PACK}, "planner-a"))[
        "id"
    ]


def _import(rows: int | None = None) -> int:
    body = CSV.read_text(encoding="utf-8")
    if rows is not None:
        lines = [x for x in body.splitlines() if not x.startswith("#")]
        body = "\n".join(lines[: rows + 1]) + "\n"
    return ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": body}, "planner.a"))["id"]


def _map_grade(cid: int) -> None:
    """The accepted mapping row that brings condition.grade (the page work of P9-8.18 fills `steps.mapping.fields`)."""
    body = {"fields": [{"source_id": "repairlog", "row": GRADE_ROW, "state": "accepted"}]}
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE composition SET steps = jsonb_set(steps, ARRAY['mapping'], steps->'mapping' || CAST(:b AS jsonb)) WHERE id = :i"
            ),
            {"b": json.dumps(body), "i": cid},
        )


def _run(cid: int, **extra: Any) -> dict:
    return ok(call("compose.testRun", {"id": cid, **extra}, "planner-a"))


def _counts() -> dict[str, int]:
    with SessionLocal() as s:
        return {t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar() or 0 for t in TABLES}  # noqa: S608 - fixed names


# ---------------------------------------------------------------- the pure grouping
def _t(i: int, stage: str | None = None, reason: str | None = None) -> sr.Trace:
    return sr.Trace(f"I{i}", stage, reason)


def test_x_10_group_counts_reached_and_stopped_by_stage():
    traces = [_t(1), _t(2), _t(3, "condition", "missing_field:condition.grade"), _t(4, "condition", "missing_field:condition.grade"),
              _t(5, "receive", "guardrail:G-TOOL-REC"), _t(6, "decide", "threshold:decide")]  # fmt: skip
    stops = {s.stage: s for s in sr.group(traces)}
    assert [s.stage for s in sr.group(traces)] == ["receive", "match", "condition", "value", "decide"]
    assert (stops["receive"].reached, stops["receive"].stopped) == (6, 1)
    assert (stops["match"].reached, stops["match"].stopped) == (5, 0)
    assert (stops["condition"].reached, stops["condition"].stopped) == (5, 2)
    assert stops["condition"].reasons == [("missing_field:condition.grade", 2)]
    assert stops["condition"].examples["missing_field:condition.grade"] == ["I3", "I4"]
    assert (stops["decide"].reached, stops["decide"].stopped) == (3, 1)


def test_x_10_sentence_is_composed_from_the_counts():
    traces = [_t(i) for i in range(163)] + [_t(1000 + i, "condition", "missing_field:condition.grade") for i in range(21)]
    traces += [_t(2000 + i, "receive", "guardrail:G-TOOL-REC") for i in range(16)]
    line = sr.sentence(sr.group(traces), 200, 163, {"receive": "Intake", "condition": "Condition"})
    assert line == (
        "200 past items: 163 reached a decision; 16 held at Intake (guardrail G-TOOL-REC: 16); "
        "21 stopped at Condition (missing field condition.grade: 21)"
    )


def test_x_10_check_text_refuses_invented_numbers_and_names():
    facts = "200 past items: 21 stopped at Condition (missing field condition.grade: 21)"
    assert sr.check_text("Twenty-one stopped; 21 lack condition.grade.", facts) == []
    assert "99" in sr.check_text("99 stopped.", facts)[0]
    assert "G-NOPE" in sr.check_text("Guardrail G-NOPE held them.", facts)[0]
    assert sr.check_text("  ", facts) == ["Write a short explanation."]


# ---------------------------------------------------------------- the action
def test_compose_test_run_groups_stops():
    cid = _composition()
    _import(40)
    out = _run(cid, limit=40)
    cond = next(s for s in out["stages"] if s["stage"] == "condition")
    assert cond["reasons"][0]["reason"] == "missing_field:condition.grade"
    assert cond["reasons"][0]["count"] == out["sample"] == 40 and cond["stopped"] == 40
    assert cond["reasons"][0]["examples"] and out["decided"] == 0
    assert out["text"].startswith(
        "40 past items: 0 reached a decision; 40 stopped at Condition (missing field condition.grade: 40)"
    )
    assert out["by_model"] is False
    _map_grade(cid)  # the draft now brings the grade: nothing stops for it
    again = _run(cid, limit=40)
    reasons = [r["reason"] for s in again["stages"] for r in s["reasons"]]
    assert "missing_field:condition.grade" not in reasons and again["decided"] > 0
    assert all(r.partition(":")[0] in ("guardrail", "threshold", "no_route", "held_record") for r in reasons)
    assert again["decided"] + sum(s["stopped"] for s in again["stages"]) == again["total"]


def test_compose_test_run_limit_and_held_rows():
    cid = _composition()
    body = CSV.read_text(encoding="utf-8").splitlines()
    rows = [x for x in body if not x.startswith("#")]
    bad = rows[1].split(",")
    bad[4] = "scrap"  # an actual route the pack does not have: held at import
    bid = ok(
        call(
            "replay.import",
            {"pack": PACK, "org_unit_id": ORG, "csv": "\n".join([rows[0], ",".join(bad), *rows[2:12]]) + "\n"},
            "planner.a",
        )
    )["id"]
    out = _run(cid, limit=5, batch_id=bid)
    assert out["sample"] == 5 and out["total"] == 6
    receive = next(s for s in out["stages"] if s["stage"] == "receive")
    assert [r["reason"] for r in receive["reasons"]] == ["held_record:route"] and receive["reasons"][0]["count"] == 1


def test_compose_test_run_needs_a_batch_and_a_person_who_may_see_it():
    cid = _composition()
    r = call("compose.testRun", {"id": cid}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "not_found"
    _import(5)
    r = call("compose.testRun", {"id": cid}, "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    r = call("compose.testRun", {"id": cid, "limit": 0}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"


def test_compose_test_run_writes_nothing():
    cid = _composition()
    _import(30)
    _map_grade(cid)
    before = _counts()
    _run(cid)
    _run(cid, limit=10)
    assert _counts() == before


def test_compose_test_run_uses_decide_case():
    cid = _composition()
    bid = _import(30)
    _map_grade(cid)
    out = _run(cid)
    assert out["decisions"], out
    pack = load_pack(PACK)
    fv = FlowVersion(None, 0, ())
    with SessionLocal() as s:
        items = {str(it["item_id"]): it for it in replay_repo.ok_items(s, bid)}
    for d in out["decisions"]:
        it = items[d["item_id"]]
        facts, _ = replay_run.as_of_facts(it)
        want = decide_case(replay_run.case_input(it, facts, pack), pack, fv, as_of=it["decided_at"])
        assert d["route"] == want.route, d["item_id"]


# ---------------------------------------------------------------- the wording runs on the model, the code checks it (R16)
def _scripted(outputs: list[Any], seen: list[int]) -> PydanticAILoop:
    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        seen.append(1)
        out = outputs[min(len(seen) - 1, len(outputs) - 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _facts_sentence(cid: int) -> str:
    return _run(cid, limit=20)["text"]


def test_compose_test_run_model_wording_accepted():
    cid = _composition()
    _import(20)
    det = _facts_sentence(cid)
    seen: list[int] = []
    runtime.set_loop(_scripted([{"summary": "Every item stopped early. " + det}], seen))
    out = _run(cid, limit=20)
    assert out["by_model"] is True and out["text"].startswith("Every item stopped early.") and len(seen) == 1
    assert out["stages"] == _run(cid, limit=20)["stages"]  # the counts are the code's, whatever the model says


def test_compose_test_run_model_invented_number_retried_then_deterministic():
    cid = _composition()
    _import(20)
    det = _facts_sentence(cid)
    seen: list[int] = []
    runtime.set_loop(_scripted([{"summary": "About 999 items stopped."}], seen))
    out = _run(cid, limit=20)
    assert out["by_model"] is False and out["text"] == det and len(seen) == 2  # one retry, then the composed sentence


def test_compose_test_run_model_refused_once_then_accepted():
    cid = _composition()
    _import(20)
    det = _facts_sentence(cid)
    seen: list[int] = []
    runtime.set_loop(_scripted([{"summary": "About 999 items stopped."}, {"summary": det}], seen))
    out = _run(cid, limit=20)
    assert out["by_model"] is True and out["text"] == det and len(seen) == 2
