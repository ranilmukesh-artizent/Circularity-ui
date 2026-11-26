"""P9-9.12 (UC-01, UC-02, X-02; I-13): the configuration agent drafts the used-car pack from its first sample prompt. The
counts below are the no-key path and the checks every model draft passes (R16): a draft never publishes or approves itself
(maker-checker, golden rule 10). Everything the agent lists comes from the pack file; the question's answer adds a business
rule with its origin, and a rule that applies to a car changes the channel only through the one decider.

The draft is stored in a composition (`compose.start`, `compose.answer`); the rules of a change set are shown to the person
and are not published by it. Models are `FunctionModel`s: no test reaches a provider."""

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents import runtime
from di.services.agents.config_agent import ChangeSet, compiled_rule, draft_change_set, read_text, rule_applies
from di.services.agents.playbooks import pack_author
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases import car_facts
from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from tests import flowkit
from tests import ucfixtures as uc
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

ORG = "Customer A"
YES = "yes_if_repair_is_under_the_recon_limit"  # the pack's option ids are slugs of its labels
NO = "no_send_them_to_auction"


def _pack():
    return load_pack("used_cars")


def _text() -> str:
    return _pack().prompts[0]


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        conn.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    flowkit.reset_flows()
    _clean()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path
    yield
    runtime.set_loop(None)
    _clean()
    uc.finish()
    flowkit.reset_flows()


def _count(table: str) -> int:
    with SessionLocal() as s:
        return int(s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608 - a fixed table name


def _start() -> dict[str, Any]:
    return uc.ok(call("compose.start", {"org_unit_id": ORG, "text": _text(), "pack_key": "used_cars"}, "planner-a"))


def test_uc_01_reading_log_and_draft():
    before = {t: _count(t) for t in ("pack_version", "decision_flow_version", "customer_overlay")}
    out = _start()
    cs = out["change_set"]
    assert out["status"] == "draft" and out["pack_key"] == "used_cars" and out["text"] == _text()
    assert out["reading"]["word_count"] == len(_text().split())
    assert out["reading"]["explicit_controls"] == 1  # "Reconditioning over $2,500 needs the used-car manager": one limit
    o = cs["outline"]
    assert o["asset_fields"] == ["VIN", "mileage", "title", "finance", "damage history"]
    assert len(o["stages"]) == 7 and len(o["routes"]) == 4
    assert o["stated"] == ["AP-UC-RECON"] and o["from_pack"] == ["G-VEH-TITLE", "G-VEH-RECALL"]
    assert o["research_additions"] == ["G-VEH-ODO", "G-VEH-BRAND", "G-VEH-SALV"]
    assert len(cs["systems"]) == 8 and sum(s["adapter"] for s in cs["systems"]) == 7
    assert [s["name"] for s in cs["systems"] if not s["adapter"]] == ["Legacy body-shop system"]
    assert len(cs["kpis"]) == 6
    q = cs["question"]
    assert q["text"] == "Should cars with minor hail damage still be considered for retail?" and len(q["options"]) == 2
    assert cs["rules"] == [] and cs["by_model"] is False
    after = {t: _count(t) for t in before}
    assert after == before  # nothing published, nothing held for approval
    assert _count("agent_proposal") == 0


def test_uc_01_assumed_items_marked():
    p = _pack()
    cs = draft_change_set(_text(), ORG, packs=[p], answer=None)
    o = cs.outline
    assert "AP-UC-RECON" not in o.assumed  # stated in the text
    assert set(o.assumed) == {"G-VEH-TITLE", "G-VEH-RECALL", "G-VEH-ODO", "G-VEH-BRAND", "G-VEH-SALV"}
    assert {g.id for g in p.guardrails} == set(o.assumed) | set(o.stated)  # every guardrail is stated or marked assumed
    skipped = draft_change_set(_text(), ORG, packs=[p], answer="skip")
    assert [(r.id, r.assumed) for r in skipped.rules] == [("BR-UC-HAIL", True)]  # the pack's default, until confirmed
    chosen = draft_change_set(_text(), ORG, packs=[p], answer=YES)
    assert [(r.id, r.assumed) for r in chosen.rules] == [("BR-UC-HAIL", False)]  # an answer is not an assumption


def test_uc_01_reading_does_not_count_a_passing_mention_of_finance():
    r = read_text(_text(), [_pack()])
    assert r.explicit_controls == 1 and r.word_count == len(_text().split())


def _hail_car() -> dict[str, Any]:
    """VIN ...030: a clean petrol SUV with hail damage and a recon estimate of 900, as the planner opens it."""
    uc.write_car(30, 1, recon=900)
    payload = uc.records(30, 1, recon=900)["uc_insp"][1]
    uc.write("uc_insp", "inspections", {**payload, "hailDamage": True})
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": uc.vin_key(ORG, uc.vin(30)), "reason": "lease_end",
            "facts": {"vin": uc.vin(30), "mileage": 38000, "return_date": "2026-10-03"}}  # fmt: skip
    return uc.get(uc.ok(call("case.open", body, "planner-a"))["case_id"])


def _channel(cs: ChangeSet, case: dict[str, Any]) -> str | None:
    """The channel the one decider gives the case once the change set's rules that apply to it are in the flow."""
    with SessionLocal() as s:
        facts: Mapping[str, Any] = {
            f"{m}.{k}": v for m, data in car_facts.records(s, str(case["assetId"])).items() for k, v in data.items()
        }
        rules = tuple(c for r in cs.rules if rule_applies(r, facts) and (c := compiled_rule(r)) is not None)
        d = decide_case(case["id"], live_pack(s, case), FlowVersion(None, 0, rules), session=s)
    return d.route


def test_uc_02_answer_adds_hail_rule():
    out = _start()
    cid = out["id"]
    done = uc.ok(call("compose.answer", {"id": cid, "answer": YES}, "planner-a"))["change_set"]
    assert done["question"] is None and done["answer"] == YES
    (rule,) = done["rules"]
    assert (rule["id"], rule["stage"], rule["stage_no"]) == ("BR-UC-HAIL", "decide", 5)
    assert rule["origin"] == {"kind": "answer", "question": "hail"}
    assert (rule["action"], rule["path"], rule["assumed"]) == ("allow", "retail", False)
    assert rule["text"] == "hail damage under the recon limit stays retail-eligible"
    assert [(c["fact"], c["op"], c["value"]) for c in rule["when"]] == [
        ("condition.hail_damage", "eq", True), ("condition.recon_estimate", "lte", 2500.0)
    ]  # fmt: skip
    assert done["ops"] == []  # a business rule is not an overlay operation
    cs = ChangeSet.model_validate(done)
    car = _hail_car()
    assert (_channel(cs, car) or "").startswith("retail")  # hail, recon 900: still a retail lot
    assert _count("agent_proposal") == 0 and _count("customer_overlay") == 0


def test_uc_02_other_answer_sends_hail_to_auction():
    out = _start()
    done = uc.ok(call("compose.answer", {"id": out["id"], "answer": NO}, "planner-a"))["change_set"]
    (rule,) = done["rules"]
    assert (rule["id"], rule["stage_no"], rule["action"], rule["path"]) == ("BR-UC-HAIL-AUCTION", 5, "require", "auction")
    assert rule["origin"] == {"kind": "answer", "question": "hail"}
    car = _hail_car()
    assert _channel(ChangeSet(pack="used_cars", base_version="x"), car) != "auction"  # no rule: the car is not sent there
    assert _channel(ChangeSet.model_validate(done), car) == "auction"


def _scripted(output: dict[str, Any]) -> PydanticAILoop:
    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _drafter():
    with SessionLocal() as s:
        return pack_author.make_drafter(CallContext(actor=SYSTEM, session=s))


def test_uc_01_model_draft_passes_checks():
    kpis = ["Gross per car", "Days in stock"]
    runtime.set_loop(_scripted({"pack": "used_cars", "ops": [], "assumed": [], "kpis": kpis, "systems": [], "question": None}))
    p = _pack()
    plain = draft_change_set(_text(), ORG, packs=[p], answer=None)
    cs = draft_change_set(_text(), ORG, packs=[p], answer=None, drafter=_drafter())
    assert cs.by_model is True and cs.kpis == kpis and cs.pack == "used_cars"
    assert cs.question is not None and cs.question.text == p.clarify.question  # the model gave none: the pack's is the fallback
    assert cs.outline == plain.outline  # what the pack holds is code's, not the model's
    done = draft_change_set(_text(), ORG, packs=[p], answer=YES, drafter=_drafter())
    assert done.by_model is True
    assert done.rules == draft_change_set(_text(), ORG, packs=[p], answer=YES).rules  # the model never writes a rule


def test_uc_01_model_draft_naming_another_pack_falls_back():
    runtime.set_loop(_scripted({"pack": "no_such_pack", "ops": [], "assumed": [], "kpis": [], "systems": [], "question": None}))
    p = _pack()
    cs = draft_change_set(_text(), ORG, packs=[p], answer=None, drafter=_drafter())
    assert cs.by_model is False and cs == draft_change_set(_text(), ORG, packs=[p], answer=None)
