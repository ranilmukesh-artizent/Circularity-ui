"""Plan 9, P9-11.11 (stories MR-01, MR-02 and MR-03): Compose draft and mappings for medical rental.

The first sample prompt of the medical rental pack is read and drafted by the configuration agent (P9-2.7): the reading log,
the pack's parts the draft lists (asset fields, 7 stages, 4 routes, guardrails stated, from the pack and research additions,
8 systems, 6 KPIs), the one question and its two answers (the customer rule `BR-MR-SVC` at stage 5, scoped or not). Nothing is
published: a draft is a change set that a person approves (rule 10). The drafting runs on the model through AgentLoop with
the code's checks first (R16: `FunctionModel`, no provider is reached); without a model the deterministic path answers.

MR-03: the pack's hints on the decontamination timestamp (0.79) and the preventive-maintenance code (0.73) are below the pack's
0.8 bar, so a person confirms them (`needs_person`, never pre-ticked, the model cannot lift them); the phase-8 test run
(`compose.testRun`) reports, for each choice of timestamp (cycle start or cycle end), how many past devices would have stopped
at the decontamination gate. Legal note: the decontamination rules are summarised from guidance; Kinective's Legal team reviews
them before they are relied on.
"""

# ruff: noqa: E501 - long lines in fixtures and asserts
import json
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from rapidfuzz import fuzz
from sqlalchemy import text

from di.connectors import extra, mapping_suggest
from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.config_agent import BAR, _clauses, _prep, draft_change_set, match_pack, read_text
from di.services.agents.forbidden import HELD_FOR_PERSON, forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler.pack import Pack, load_pack, pack_keys
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

ORG, PACK = "Customer A", "medical_rental"
DECON = "G-MED-DECON"


def _packs() -> list[Pack]:
    return [load_pack(k) for k in pack_keys()]


def _mr() -> Pack:
    return load_pack(PACK)


def _text() -> str:
    return _mr().prompts[0]


def _stated(pack: Pack, words: str) -> list[str]:
    """The guardrails the description states: the words of a clause are close to the guardrail's own (the matcher's bar)."""
    clauses = _clauses(words)
    return [g.id for g in pack.guardrails if any(fuzz.token_set_ratio(_prep(c), _prep(g.text)) >= BAR for c in clauses)]


def _research(pack: Pack) -> set[str]:
    return {g.id for g in pack.gates if g.params.get("research_addition")}


def _draft(answer: str | None = None, **kw: Any):
    return draft_change_set(_text(), ORG, packs=_packs(), answer=answer, **kw)


def _option(cs: Any, words: str) -> str:
    return next(o.id for o in cs.question.options if words in o.label)


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    _reset()


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM replay_batch"))
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM raw_record WHERE source_id = 'mr_decon'"))
        conn.execute(text("DELETE FROM source_connection WHERE source_id = 'mr_decon'"))
        conn.execute(text("DELETE FROM source_system WHERE id = 'mr_decon'"))
        mine = "SELECT seq FROM action_journal WHERE action LIKE 'compose.%' OR action LIKE 'replay.%'"
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


# ---------------------------------------------------------------- MR-01 the reading log and the draft
def test_mr_01_reading_log_and_draft():
    packs, words = _packs(), _text()
    reading = read_text(words, packs)
    log = {
        "word_count": reading.word_count,
        "explicit_controls": len(reading.controls),
        "matched_pack": match_pack(reading, words, packs).key,
    }
    assert log == {"word_count": len(words.split()), "explicit_controls": 2, "matched_pack": PACK}
    assert {c.kind for c in reading.controls} == {"amount", "role"}
    cs = _draft()
    pack = _mr()
    assert (cs.pack, cs.base_version, cs.by_model) == (PACK, pack.version, False)
    # what the draft lists comes from the pack
    assert pack.replay.example["asset_fields"] == ["model", "service interval", "certification", "decontamination"]
    assert (len(pack.stages), len(pack.routes)) == (7, 4)
    stated, research = _stated(pack, words), _research(pack)
    assert sorted(stated) == ["AP-MR-REPAIR", DECON]
    own = [g.id for g in pack.guardrails if g.id not in stated and g.id not in research]
    assert own == ["G-MED-SVC"] and research == {"G-MED-FSN", "G-MED-REFURB", "G-DATA-3"}
    assert len(cs.systems) == 8 and all(s.adapter for s in cs.systems)
    assert len(cs.kpis) == 6
    assert cs.question is not None and len(cs.question.options) == 2 and cs.answer is None
    assert cs.ops == [] and cs.blocked == []  # the $1,000 it states is the pack's own limit: nothing to change


def _counts() -> dict[str, int]:
    with SessionLocal() as s:
        return {
            t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()  # noqa: S608 - fixed names
            for t in ("customer_overlay", "pack_version", "action_journal")
        }


def test_mr_01_nothing_is_published():
    before = _counts()
    cid = ok(call("compose.start", {"org_unit_id": ORG, "text": _text(), "pack_key": PACK}, "planner-a"))["id"]
    got = ok(call("compose.get", {"id": cid}, "planner-a"))
    assert got["status"] == "draft" and got["reading"]["by_model"] is False
    assert got["change_set"]["question"]["options"] and got["change_set"]["pack"] == PACK
    after = _counts()
    assert (after["customer_overlay"], after["pack_version"]) == (
        before["customer_overlay"],
        before["pack_version"],
    )  # no overlay saved, no version made


def _scripted(output: dict[str, Any], seen: list[int] | None = None) -> PydanticAILoop:
    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _drafter():
    from di.services.actions.pipeline import SYSTEM, CallContext
    from di.services.agents.playbooks import pack_author

    with SessionLocal() as s:
        return pack_author.make_drafter(CallContext(actor=SYSTEM, session=s))


def _model(**over: Any) -> dict[str, Any]:
    return {"pack": PACK, "ops": [], "assumed": [], "kpis": [], "systems": [], "question": None, **over}


def test_mr_01_model_draft_passes_checks():
    """A model draft that keeps the pack's parts is accepted (by_model), and every check still ran: the question and the
    systems of the deterministic path stand when the model leaves them out."""
    plain = _draft()
    runtime.set_loop(_scripted(_model(kpis=["Fleet utilisation"], systems=[s.name for s in plain.systems])))
    cs = _draft(drafter=_drafter())
    assert cs.by_model is True and cs.pack == PACK and cs.kpis == ["Fleet utilisation"]
    assert [s.name for s in cs.systems] == [s.name for s in plain.systems] and all(s.adapter for s in cs.systems)
    assert cs.question is not None and cs.question.text == plain.question.text  # the pack's question is the fallback
    assert cs.ops == [] and cs.blocked == []


def test_mr_01_model_cannot_weaken_the_repair_limit_or_skip_decontamination():
    weaker = {
        "id": "op-1",
        "op": "tighten",
        "target": "AP-MR-REPAIR",
        "field": "intervention.repair_estimate",
        "value": 4000,
        "seen": 1000,
    }
    skip = {"id": "op-2", "op": "shortcut", "stage": "receive", "to": "condition", "when": []}  # past the decontamination stage
    runtime.set_loop(_scripted(_model(ops=[weaker, skip])))
    cs = _draft(drafter=_drafter())
    assert cs.by_model is True and cs.ops == []  # neither is an operation: the checks win over the model
    assert len(cs.blocked) == 2 and any("weakens" in b.text for b in cs.blocked)
    assert any("compliance" in b.text.lower() for b in cs.blocked)


def test_mr_01_invalid_model_draft_retried_once_then_deterministic():
    bad = {"id": "op-1", "op": "add_approver", "target": "G-NOPE", "role": "Planner"}
    seen: list[int] = []
    runtime.set_loop(_scripted(_model(ops=[bad]), seen))
    cs = _draft(drafter=_drafter())
    assert len(seen) == 2  # the first try, one retry with the error
    assert cs.by_model is False and cs == _draft()


def test_mr_01_no_model_gives_the_deterministic_draft():
    assert _draft(drafter=_drafter()) == _draft() and _draft().by_model is False


def test_mr_01_assumed_items_marked():
    """An answer is the person's; a skipped question is filled in by the agent and marked assumed until confirmed (X-02)."""
    skipped = _draft("skip")
    assert skipped.question is None and skipped.answer == "skip"
    assert [(r.id, r.assumed) for r in skipped.rules] == [("BR-MR-SVC", True)]  # the first option, marked until confirmed
    first = _draft().question.options[0].id
    assert [(r.id, r.assumed) for r in _draft(first).rules] == [("BR-MR-SVC", False)] and _draft(first).assumed == []


# ---------------------------------------------------------------- MR-02 the service answer scopes the rule
def _rule(cs: Any) -> Any:
    assert [r.id for r in cs.rules] == ["BR-MR-SVC"] and cs.ops == [], (cs.rules, cs.ops)
    assert cs.rules[0].origin is not None and cs.rules[0].origin.kind == "answer"
    assert cs.rules[0].origin.kind == "answer" and cs.rules[0].origin.question == "svc"  # where the rule came from: the question key
    return cs.rules[0]


def test_mr_02_service_answer_scopes_rule():
    asked = _draft()
    always = _rule(_draft(_option(asked, "always")))
    assert (always.stage, always.action, always.path) == ("decide", "require", "service_rerent")
    assert all(c.fact != "request.days" for c in always.when)  # every rental
    over = _rule(_draft(_option(asked, "30 days")))
    days = [c for c in over.when if c.fact == "request.days"]
    assert over.stage == "decide" and [(c.op, c.value) for c in days] == [("gt", 30.0)]  # "... and request.days > 30"
    assert over.when[: len(always.when)] == always.when  # the same scope, narrowed
    stages = [s.key for s in _mr().stages]
    assert stages.index(over.stage) == 4  # stage 5 of 7
    assert _draft(_option(asked, "always")).assumed == [] and _draft(_option(asked, "always")).question is None


def test_mr_02_model_draft_answer_adds_the_packs_rule_not_the_models():
    """The model's draft has no field for a rule: the rule an answer adds is the pack's own option, checked and the same."""
    asked = _draft()
    runtime.set_loop(_scripted(_model()))
    cs = _draft(_option(asked, "30 days"), drafter=_drafter())
    assert cs.by_model is True and any(c.fact == "request.days" and c.op == "gt" for c in _rule(cs).when)
    assert cs.rules == _draft(_option(asked, "30 days")).rules


def test_mr_02_answer_through_the_action_stays_a_draft():
    cid = ok(call("compose.start", {"org_unit_id": ORG, "text": _text(), "pack_key": PACK}, "planner-a"))["id"]
    qs = ok(call("compose.get", {"id": cid}, "planner-a"))["change_set"]["question"]["options"]
    pick = next(o["id"] for o in qs if "30 days" in o["label"])
    got = ok(call("compose.answer", {"id": cid, "answer": pick}, "planner-a"))
    assert got["status"] == "draft" and got["change_set"]["question"] is None
    assert [r["id"] for r in got["change_set"]["rules"]] == ["BR-MR-SVC"] and got["change_set"]["ops"] == []
    assert call("compose.submit", {"id": cid}, "planner-a")["ok"] is False  # steps are not done: nothing goes to approval


# ---------------------------------------------------------------- MR-03 the two mappings that need a person
SAMPLE = {"cycleId": "DC-1", "tag": "SYN-MR-IP-0001", "method": "standard", "enhanced": False,
          "cycleStartedAt": "2026-03-19T07:30:00+00:00", "cycleEndedAt": "2026-03-19T10:30:00+00:00", "operatorRef": "OP-01", "result": "pass"}  # fmt: skip
BIOMED = {
    "serviceId": "S-1",
    "tag": "SYN-MR-IP-0001",
    "pmCode": "PM-B2",
    "pmDoneAt": "2026-03-01",
    "certificationExpiry": "2027-01-01",
}


def _proposals(source: str, sample: dict[str, Any], **kw: Any) -> dict[str, Any]:
    recs = [sample]
    profiles = [mapping_suggest.profile(recs, f) for f in mapping_suggest.field_paths(recs)]
    out = mapping_suggest.suggest(profiles, recs, mapping_suggest.canonical_fields(), source_id=source, **kw)
    return {p.field: p for p in out}


def test_mr_03_decon_timestamp_and_pm_code_need_a_person():
    decon = _proposals("mr_decon", SAMPLE)["cycleEndedAt"]
    assert (decon.target, decon.confidence, decon.needs_person, decon.band) == ("condition.decon_ended_at", 0.79, True, "check")
    assert decon.reason == "two timestamps; the end of the cycle was chosen"
    pm = _proposals("mr_biomed", BIOMED)["pmCode"]
    assert (pm.target, pm.confidence, pm.needs_person, pm.band) == ("condition.pm_code", 0.73, True, "check")
    assert pm.reason == "meaning taken from the service manual"
    assert _proposals("mr_decon", SAMPLE)["result"].needs_person is False  # no hint, nothing to confirm
    assert _proposals("mr_decon", SAMPLE)["cycleStartedAt"].needs_person is False
    plain = {p.field: p for p in _proposals("sap", SAMPLE).values()}  # a source with no hint is as before
    assert plain["cycleEndedAt"].confidence != 0.79 and not plain["cycleEndedAt"].needs_person


def test_mr_03_model_cannot_lift_a_hinted_mapping():
    """The reranker (model) may prefer another field; the pack's hint, a person's to confirm, wins over it."""

    def other(_field: Any, candidates: list[tuple[str, float]], /):
        pick = next(t for t, _ in candidates if t != "condition.decon_ended_at")
        return mapping_suggest.RerankAnswer(target=pick, rule="copy", why="Looks like another field.")

    p = _proposals("mr_decon", SAMPLE, rerank=other)["cycleEndedAt"]
    assert (p.target, p.confidence, p.needs_person) == ("condition.decon_ended_at", 0.79, True)


def test_mr_03_mapping_suggest_action_carries_the_flag():
    with SessionLocal() as s:
        sid = extra.register(s, "mr_decon", ORG)
        s.execute(
            text(
                "INSERT INTO raw_record (source_id, resource, ext_id, payload) VALUES (:s, 'cycles', 'DC-1', CAST(:p AS jsonb))"
            ),
            {"s": sid, "p": json.dumps(SAMPLE)},
        )
        s.commit()
    rows = {r["field"]: r for r in ok(call("mapping.suggest", {"source_id": sid}, "developer"))["rows"]}
    assert (rows["cycleEndedAt"]["target"], rows["cycleEndedAt"]["confidence"], rows["cycleEndedAt"]["needs_person"]) == (
        "condition.decon_ended_at", 0.79, True,
    )  # fmt: skip
    assert rows["cycleEndedAt"]["band"] == "check" and rows["result"]["needs_person"] is False


def test_mr_03_a_choice_on_it_stays_a_persons():
    assert "mapping.decide" in HELD_FOR_PERSON and forbidden("mapping.answerOwner") and not forbidden("mapping.askOwner")


# ---------------------------------------------------------------- MR-03 the test run per choice of timestamp
HEAD = (
    "item_id,class,decided_at,reason,actual_route,realised_value,cost_logistics,cost_refurb,cost_test,cost_fees,market,"
    "fact.decon_started_at,fact.decon_started_at.at,fact.decon_ended_at,fact.decon_ended_at.at,fact.checked_in_at,fact.checked_in_at.at"
)
CHECK_IN, DECIDED = "2026-03-19T08:00:00+00:00", "2026-03-20T09:00:00+00:00"


def _device(n: int, start: str, end: str) -> str:
    known = "2026-03-19T12:00:00+00:00"
    return (f"MR-H{n:03d},infusion_pump,{DECIDED},sample decision,rerent,120.00,5,0,2,1,East,"
            f"2026-03-19T{start}:00+00:00,{known},2026-03-19T{end}:00+00:00,{known},{CHECK_IN},{known}")  # fmt: skip


def _history() -> str:
    """20 past devices, checked in at 08:00: 12 whose cycle began before check-in and ended after (the start is too early),
    3 whose cycle ended before check-in (stopped under either choice), 5 that began and ended after it."""
    rows = [_device(n, "07:30", "10:30") for n in range(12)]
    rows += [_device(12 + n, "05:00", "07:00") for n in range(3)]
    rows += [_device(15 + n, "08:30", "11:30") for n in range(5)]
    return HEAD + "\n" + "\n".join(rows) + "\n"


def test_mr_03_timestamp_choice_changes_stops():
    cid = ok(call("compose.start", {"org_unit_id": ORG, "text": _text(), "pack_key": PACK}, "planner-a"))["id"]
    ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": _history()}, "planner.a"))
    out = ok(call("compose.testRun", {"id": cid}, "planner-a"))
    (report,) = out["mapping_choices"]
    assert (report["gate"], report["devices"]) == (DECON, 20)
    stopped = {c["id"]: c["stopped"] for c in report["choices"]}
    assert stopped == {"cycle_start": 15, "cycle_end": 3}  # both counts shown; the start stops more
    assert stopped["cycle_start"] > stopped["cycle_end"]
    assert {c["id"]: c["field"] for c in report["choices"]} == {"cycle_start": "cycleStartedAt", "cycle_end": "cycleEndedAt"}
    assert "15 of 20" in report["text"] and "3 of 20" in report["text"]
    assert "15 of 20" in out["text"]  # the plain-language line carries the counts the code computed


def test_mr_03_no_report_for_a_pack_without_the_gate():
    from di.services.modeler import mapping_choices

    assert mapping_choices.report([], load_pack("tool_fleet")) == []
