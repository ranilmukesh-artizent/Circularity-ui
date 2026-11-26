"""P9-2.7 (I-13, story X-02): the configuration agent reads a description, matches a pack, asks one question and drafts a
change set of typed overlay operations that a person approves through the overlay maker-checker (golden rule 10).

The pure part (`di.services.agents.config_agent`) is tested with explicit pack lists (fixtures/packs hold a recall check
and the tests build a locked repair guardrail, because the shipped packs do not have them yet). The actions run through the
pipeline, so this file uses `no_synced_conflicts`. Every model is a `FunctionModel`: no test reaches a provider (R16)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.config_agent import ChangeSet, ChangeSetError, draft_change_set, match_pack, read_text
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler.pack import GuardParam, Pack, PackGuardrail, load_pack, pack_keys, parse_pack
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "packs"
DESC = "We lease cordless tools to building sites. Repairs over $500 go to the fleet manager. Markets DE and FR."
UNKNOWN = "We refurbish laptops from corporate lease ends"


def _packs() -> list[Pack]:
    return [load_pack(k) for k in pack_keys()]


def _with_prompts() -> list[Pack]:
    return [p for p in _packs() if all(p.prompts)]


def _fleet() -> Pack:
    """Tool fleet with a safety recall check (compliance, at Match and verify) and a locked repair guardrail at $600."""
    base = parse_pack(json.loads((FIXTURES / "recall_test.json").read_text(encoding="utf-8")))
    repair = PackGuardrail(
        id="GR-R1", text="Repairs over $600 go to the fleet manager", owner="Fleet desk", type="Threshold", stage="value",
        locked=True, param=GuardParam(field="limit", value=600, stricter="lower", min=100, max=2000),
    )  # fmt: skip
    return base.model_copy(update={"guardrails": [*base.guardrails, repair]})


def _device_blacklist() -> Pack:
    base = load_pack("device")
    check = PackGuardrail(
        id="GR-D7", text="Device blacklist and lock check", owner="Quality", type="Compliance", stage="match", locked=True
    )  # fmt: skip
    return base.model_copy(update={"guardrails": [*base.guardrails, check]})


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    _reset()


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM config_change_set"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM agent_proposal WHERE agent = 'recover-config'"))
        conn.execute(text("DELETE FROM agent_run WHERE agent = 'recover-config'"))
        mine = (
            "SELECT seq FROM action_journal WHERE action LIKE 'overlay.%' OR action LIKE 'config.%' OR action LIKE 'proposal.%'"
        )
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608
        conn.execute(text("DELETE FROM domain_event WHERE type = 'proposal.held' AND payload->>'agent' = 'recover-config'"))


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


# ---------------------------------------------------------------- the reading
def test_x_02_reading_log_counts_and_controls():
    r = read_text(DESC)
    assert r.word_count == 19  # the plan says 17; the text has 19 words (Repairs over $500 go to the fleet manager: 8)
    amounts = [c for c in r.controls if c.kind == "amount"]
    assert [(c.text, c.value) for c in amounts] == [("Repairs over $500", 500.0)]
    assert [c.value for c in r.controls if c.kind == "market"] == [["DE", "FR"]]
    assert r.unit == "tool" and r.by_model is False


def test_x_02_reading_percent_condition_and_unit():
    r = read_text("Never list a device below 60% of its forecast price. New tool under 3 months: skip the recall check.")
    assert [c.value for c in r.controls if c.kind == "percent"] == [60.0]
    assert any(c.kind == "condition" and "3 month" in str(c.value) for c in r.controls)


def test_x_02_matches_pack_for_sample_prompts():
    packs = _with_prompts()
    assert {"tool_fleet", "device"} <= {p.key for p in packs}
    for p in packs:
        for prompt in p.prompts:
            m = match_pack(read_text(prompt), prompt, packs)
            assert (m.key, m.nearest_only) == (p.key, False), (p.key, prompt, m)


def test_x_02_unknown_industry_nearest_and_question():
    packs = [
        p for p in _with_prompts() if p.clarify
    ]  # the packs that carry a clarifying question (the later packs may have none)
    m = match_pack(read_text(UNKNOWN), UNKNOWN, packs)
    assert m.nearest_only is True and m.key in {p.key for p in packs}
    cs = draft_change_set(UNKNOWN, "Customer A", packs=packs, answer=None)
    assert cs.pack == m.key and cs.question is not None and len(cs.question.options) == 2


# ---------------------------------------------------------------- the change set
def test_x_02_assumed_items_marked():
    packs = [load_pack("tool_fleet")]
    cs = draft_change_set(DESC, "Customer A", packs=packs, answer="skip")
    assert cs.question is None and cs.answer == "skip"
    defaults = [o for o in cs.ops if o.op == "add_approver"]
    assert defaults and {o.id for o in defaults} <= set(cs.assumed)
    chosen = draft_change_set(
        DESC, "Customer A", packs=packs, answer=draft_change_set(DESC, "x", packs=packs, answer=None).question.options[0].id
    )
    assert chosen.assumed == []  # an answer is not an assumption


def test_x_02_blocked_skip_refused_and_named():
    fleet = _fleet()
    cs = draft_change_set("New tool under 3 months: skip the recall check.", "Customer A", packs=[fleet], answer="skip")
    assert not [o for o in cs.ops if o.op == "shortcut"]
    assert len(cs.blocked) == 1 and "recall" in cs.blocked[0].guardrail.lower()
    dev = _device_blacklist()
    cs = draft_change_set("Quote under $50: skip the blacklist check.", "Customer A", packs=[dev], answer="skip")
    assert not [o for o in cs.ops if o.op == "shortcut"]
    assert len(cs.blocked) == 1 and "blacklist" in cs.blocked[0].guardrail.lower()


def test_x_02_tighten_accepted_weaken_refused():
    fleet = _fleet()
    cs = draft_change_set("Repairs over $500 go to the fleet manager.", "Customer A", packs=[fleet], answer="skip")
    t = [o for o in cs.ops if o.op == "tighten"]
    assert len(t) == 1 and (t[0].target, t[0].field, t[0].value, t[0].seen) == ("GR-R1", "limit", 500, 600)
    assert cs.blocked == []
    cs = draft_change_set("Repairs over $900 go to the fleet manager.", "Customer A", packs=[fleet], answer="skip")
    assert not [o for o in cs.ops if o.op == "tighten"]
    assert len(cs.blocked) == 1 and "weakens locked guardrail" in cs.blocked[0].text
    assert cs.blocked[0].guardrail == "Repairs over $600 go to the fleet manager"


def test_x_02_percent_tightens_device_floor():
    cs = draft_change_set(
        "Never list a device below 60% of its forecast price.", "Customer A", packs=[load_pack("device")], answer="skip"
    )
    t = [o for o in cs.ops if o.op == "tighten"]
    assert [(o.target, o.value, o.seen) for o in t] == [("GR-D2", 0.6, 0.55)]


def test_x_02_never_code():
    schema = ChangeSet.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "pack",
        "base_version",
        "ops",
        "rules",
        "assumed",
        "blocked",
        "systems",
        "kpis",
        "question",
        "answer",
        "by_model",
        "outline",
    }
    names = json.dumps(schema).lower()
    assert not any(f'"{w}"' in names for w in ("code", "script", "function", "expression"))
    ops = json.dumps(schema["$defs"]).lower()
    assert '"code"' not in ops and '"script"' not in ops


def test_x_02_validation_error_names_the_op(monkeypatch):
    pack = load_pack("tool_fleet")
    bad = pack.model_copy(update={"clarify": pack.clarify.model_copy(update={"options": [
        pack.clarify.options[0].model_copy(update={"adds": json.dumps([{"id": "op-1", "op": "add_approver", "target": "GR-NOPE", "role": "X"}])}),  # noqa: E501
        pack.clarify.options[1],
    ]})})  # fmt: skip
    with pytest.raises(ChangeSetError) as e:
        draft_change_set("We lease tools.", "Customer A", packs=[bad], answer="skip")
    assert e.value.code == "validation_error" and e.value.op_id == "op-1"


# ---------------------------------------------------------------- the actions
BODY = {"text": DESC, "org_unit_id": "Customer A"}


def _prompt1() -> dict:
    return {"text": load_pack("tool_fleet").prompts[0], "org_unit_id": "Customer A"}


def test_x_02_exactly_one_question():
    r = ok(call("config.read", _prompt1(), "planner-a"))
    assert r["match"]["key"] == "tool_fleet" and r["match"]["nearest_only"] is False
    assert r["match"]["name"] == load_pack("tool_fleet").name  # the pack file's own name, for the screen
    assert r["pack_names"]["tool_fleet"] == r["match"]["name"] and len(r["pack_names"]) >= 8  # derived from the pack files
    assert r["question"]["text"] and len(r["question"]["options"]) == 2
    qid = r["question"]["options"][0]["id"]
    assert call("config.draft", _prompt1(), "planner-a")["error"]["code"] == "validation_error"  # unanswered
    d = ok(call("config.draft", {**_prompt1(), "answer": qid, "answer2": "skip"}, "planner-a"))
    assert d["change_set"]["question"] is None and d["change_set"]["answer"] == qid
    assert isinstance(d["proposal_id"], int) and isinstance(d["change_set_id"], int)


def test_x_02_text_over_4000_refused():
    r = call("config.read", {"text": "x " * 2100, "org_unit_id": "Customer A"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"


def _pending() -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT id, agent, action, status, requested_by, input FROM agent_proposal WHERE agent = 'recover-config' ORDER BY id"  # noqa: E501
            )
        ).mappings()
        return [dict(r) for r in rows]


def test_x_02_held_for_maker_checker():
    q = ok(call("config.read", _prompt1(), "planner-a"))["question"]["options"][0]["id"]
    d = ok(call("config.draft", {**_prompt1(), "answer": q}, "planner-a"))
    rows = _pending()
    assert len(rows) == 1 and (rows[0]["agent"], rows[0]["action"], rows[0]["status"]) == (
        "recover-config",
        "overlay.save",
        "pending",
    )
    assert rows[0]["id"] == d["proposal_id"] and rows[0]["requested_by"] == "planner-a"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM customer_overlay")).scalar_one() == 0  # nothing saved yet
    own = call("proposal.accept", {"id": d["proposal_id"]}, "planner-a")
    assert own["ok"] is False and own["error"]["code"] == "conflict"  # the person the agent acted for only rejects
    acc = ok(call("proposal.accept", {"id": d["proposal_id"]}, "admin"))
    assert acc["status"] == "accepted"
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT status, maker FROM customer_overlay WHERE pack_key = 'tool_fleet' AND org_unit_id = 'Customer A'")
        ).first()
    assert row is not None and row.status == "draft"
    # the agent cannot approve or publish it, whatever the headers say
    for action in ("overlay.approve", "overlay.submit"):
        r = client.post(
            f"/api/actions/{action}", json={"pack_key": "tool_fleet", "org_unit_id": "Customer A"},
            headers={**h("approver"), "X-Circularity-Preparer": "recover-config", "X-Circularity-Confirmed": "true"},
        ).json()  # fmt: skip
        assert r["ok"] is False
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM customer_overlay WHERE pack_key = 'tool_fleet'")).scalar_one() == "draft"


def test_config_draft_tenant_boundary():
    q = ok(call("config.read", _prompt1(), "planner-a"))["question"]["options"][0]["id"]
    r = call("config.draft", {**_prompt1(), "answer": q}, "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    r = call("config.read", _prompt1(), "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"


# ---------------------------------------------------------------- the model drafts first, the checks win (decision of 25 Nov)
APPROVER = {"id": "op-1", "op": "add_approver", "target": "GR-05", "role": "Planner"}


def _scripted(output: dict[str, Any], seen: list[int] | None = None) -> PydanticAILoop:
    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _draft(**over: Any) -> dict[str, Any]:
    return {"pack": "tool_fleet", "ops": [APPROVER], "assumed": [], "kpis": [], "systems": [], "question": None, **over}


def _drafter():
    from di.services.actions.pipeline import SYSTEM, CallContext
    from di.services.agents.playbooks import pack_author

    with SessionLocal() as s:
        return pack_author.make_drafter(CallContext(actor=SYSTEM, session=s))


def test_x_02_model_draft_accepted_and_stored():  # (a)
    runtime.set_loop(_scripted(_draft(kpis=["Tools back in service"])))
    d = ok(call("config.draft", {**_prompt1(), "answer": "skip"}, "planner-a"))
    cs = d["change_set"]
    assert cs["by_model"] is True and cs["kpis"] == ["Tools back in service"]
    assert [(o["op"], o["target"]) for o in cs["ops"] if o["op"] == "add_approver"] == [("add_approver", "GR-05")]
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT pack, ops, proposal_id FROM config_change_set WHERE id = :i"), {"i": d["change_set_id"]}
        ).one()
    assert row.pack == "tool_fleet" and row.proposal_id == d["proposal_id"] and any(o["op"] == "add_approver" for o in row.ops)
    assert ok(call("config.read", _prompt1(), "planner-a"))["reading"]["by_model"] is True
    assert len(_pending()) == 1  # still one proposal held for a person (rule 10)


def test_x_02_model_draft_weakening_locked_guardrail_is_blocked():  # (b)
    weak = {"id": "op-2", "op": "tighten", "target": "GR-R1", "field": "limit", "value": 900, "seen": 600}
    runtime.set_loop(_scripted(_draft(ops=[weak, APPROVER])))
    cs = draft_change_set(
        "Repairs over $900 go to the fleet manager.", "Customer A", packs=[_fleet()], answer="skip", drafter=_drafter()
    )
    assert cs.by_model is True and not [o for o in cs.ops if o.op == "tighten"]
    assert [b.guardrail for b in cs.blocked] == ["Repairs over $600 go to the fleet manager"]
    assert "weakens locked guardrail" in cs.blocked[0].text
    # a control read_text found overrides the model's value for the same field
    ok500 = {"id": "op-2", "op": "tighten", "target": "GR-R1", "field": "limit", "value": 550, "seen": 600}
    runtime.set_loop(_scripted(_draft(pack="tool_fleet", ops=[ok500])))
    cs = draft_change_set(
        "Repairs over $500 go to the fleet manager.", "Customer A", packs=[_fleet()], answer="skip", drafter=_drafter()
    )
    assert [o.value for o in cs.ops if o.op == "tighten"] == [500]


def test_x_02_invalid_op_retried_once_then_deterministic():  # (c)
    bad = {"id": "op-1", "op": "add_approver", "target": "GR-NOPE", "role": "Planner"}
    seen: list[int] = []
    runtime.set_loop(_scripted(_draft(ops=[bad]), seen))
    packs = [load_pack("tool_fleet")]
    cs = draft_change_set(DESC, "Customer A", packs=packs, answer="skip", drafter=_drafter())
    assert len(seen) == 2  # the first try and one retry with the error
    assert cs.by_model is False and cs == draft_change_set(DESC, "Customer A", packs=packs, answer="skip")


def test_x_02_model_question_beats_pack_clarify():  # (d)
    question = {"text": "Who signs off a repair?", "options": [{"id": "plan", "label": "The planner", "ops": [APPROVER]},
                                                               {"id": "none", "label": "Nobody", "ops": []}]}  # fmt: skip
    runtime.set_loop(_scripted(_draft(ops=[], question=question)))
    packs = [load_pack("tool_fleet")]
    cs = draft_change_set(DESC, "Customer A", packs=packs, answer=None, drafter=_drafter())
    assert cs.by_model and cs.question is not None and cs.question.text == "Who signs off a repair?"
    assert [o.id for o in cs.question.options] == ["plan", "none"] and cs.question.text != packs[0].clarify.question
    cs = draft_change_set(DESC, "Customer A", packs=packs, answer="plan", drafter=_drafter())
    assert cs.question is None and [o.op for o in cs.ops if o.op == "add_approver"] == ["add_approver"] and cs.assumed == []
    # no question from the model: the pack's clarify is the fallback
    runtime.set_loop(_scripted(_draft(ops=[])))
    cs = draft_change_set(DESC, "Customer A", packs=packs, answer=None, drafter=_drafter())
    assert cs.by_model and cs.question is not None and cs.question.text == packs[0].clarify.question


def test_x_02_no_model_gives_the_deterministic_result():  # (e)
    packs = [load_pack("tool_fleet")]
    plain = draft_change_set(DESC, "Customer A", packs=packs, answer="skip")
    with_drafter = draft_change_set(DESC, "Customer A", packs=packs, answer="skip", drafter=_drafter())  # the loop has no model
    assert plain == with_drafter and plain.by_model is False
    r = ok(call("config.read", BODY, "planner-a"))
    assert r["reading"]["by_model"] is False and r["match"]["key"] == "tool_fleet"
    with SessionLocal() as s:  # a run that no model took part in leaves no row
        assert s.execute(text("SELECT count(*) FROM agent_run WHERE agent = 'recover-config'")).scalar_one() == 0


def _every_pack() -> list[Pack]:
    from di.services.modeler.pack import load_pack, pack_keys

    return [load_pack(k) for k in pack_keys()]


def test_ui_a2_every_pack_file_matches_its_own_sample_prompts():
    """The list is derived from the pack files: a new pack must be found by its own prompts, not by another pack's unit word."""
    packs = _every_pack()
    assert len(packs) >= 8
    for p in packs:
        for prompt in (q for q in p.prompts if q):
            m = match_pack(read_text(prompt), prompt, packs)
            assert (m.key, m.nearest_only) == (p.key, False), (p.key, prompt, m)


def test_ui_a2_one_generic_word_is_not_a_perfect_match():
    """'asset' is industrial's unit: a text that only contains it must not score 100 for industrial."""
    packs = _every_pack()
    text = "Please keep the asset register tidy"
    m = match_pack(read_text(text), text, packs)
    assert m.score < 100, m
    itad = "IT asset disposition: wipe laptops and certify data destruction"
    m = match_pack(read_text(itad), itad, packs)
    assert (m.key, m.nearest_only) == ("itad", False)


def test_ui_a2_text_no_pack_describes_is_nearest_only():
    packs = _every_pack()
    for desc in ("We sell coffee beans to cafes", "We roast and ship coffee to cafes across the region"):
        m = match_pack(read_text(desc), desc, packs)
        assert m.nearest_only is True and m.score < 60, (desc, m)
