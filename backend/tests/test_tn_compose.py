"""Plan 9, P9-10.11 (stories TN-01 and TN-02, registry entry I-13): the Compose draft from the telecom prompt.

The configuration agent reads the pack's first sample prompt, matches `telecom_network`, drafts the change set and asks the
pack's one question (firmware). The reading log, the guardrail groups and the answer's rule are code; a model drafts first
when the router has one (R16) and the checks win. Every model here is a `FunctionModel`: no test reaches a provider. Pure
except the drafter (a session for the run record) and the `compose.start` action, which only ever makes a draft: nothing is
published or approved here (maker-checker, `forbidden.py`).
Legal note: the export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.config_agent import ChangeSet, draft_change_set, guardrail_groups, match_pack, read_text
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler.overlay import apply_overlay
from di.services.modeler.pack import Pack, load_pack, pack_keys
from tests.helpers import call
from tests.test_tn_routing import decide, sample

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

PACK = load_pack("telecom_network")
TEXT = PACK.prompts[0]
ORG = "Customer A"
RULE = "Upgrade firmware before redeploy"


def _packs() -> list[Pack]:
    return [load_pack(k) for k in pack_keys()]


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM agent_proposal WHERE agent = 'recover-config' OR requested_by = 'planner-a'"))
        conn.execute(text("DELETE FROM agent_run WHERE agent = 'recover-config'"))
        mine = "SELECT seq FROM action_journal WHERE action LIKE 'compose.%' OR action LIKE 'overlay.%'"
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    _reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _published() -> tuple[int, int]:
    with engine.connect() as conn:
        packs = conn.execute(text("SELECT count(*) FROM pack_version WHERE key = 'telecom_network'")).scalar_one()
        overlays = conn.execute(text("SELECT count(*) FROM customer_overlay")).scalar_one()
    return int(packs), int(overlays)


def _answers(cs: ChangeSet) -> dict[str, str]:
    assert cs.question is not None
    return {o.label: o.id for o in cs.question.options}


def test_tn_01_reading_log_and_draft():
    before = _published()
    packs = _packs()
    reading = read_text(TEXT, packs)
    assert reading.word_count == len(TEXT.split()) and reading.by_model is False
    assert [c.text for c in reading.controls] == ["Export-control check before any resale"] and reading.controls[
        0
    ].kind == "check"
    assert reading.explicit_controls == 1  # the stated check is the "1 explicit control" the reading log says (smoke P9-10)
    match = match_pack(reading, TEXT, packs)
    assert (match.key, match.nearest_only) == ("telecom_network", False)

    cs = draft_change_set(TEXT, ORG, packs=packs, answer=None)
    assert cs.pack == "telecom_network" and cs.by_model is False and cs.ops == [] and cs.blocked == []
    # the pack's parts the draft lists: asset fields, 7 stages, 5 routes, 6 KPIs, 8 systems that all have adapters
    assert {"model", "site", "serial"} <= set(PACK.data.min_fields)
    mapped = {m["canonical"] for m in PACK.data.mappings if m.get("canonical")}
    assert {"asset.hw_revision", "asset.export_class"} <= mapped  # revision and export class
    assert PACK.valuer.params["params"]["firmware_major_gap_for_upgrade"] == 2  # firmware
    assert any(g.id == "G-NET-CFG" and "onfiguration" in g.text for g in PACK.guardrails)  # configuration
    assert len(PACK.stages) == 7 and len(PACK.routes) == 5
    assert len(cs.systems) == 8 and all(s.adapter for s in cs.systems)
    assert len(cs.kpis) == 6
    # 1 stated + 2 pack guardrails, the research additions listed apart (the shared downstream gates are not the pack's own)
    groups = guardrail_groups(TEXT, PACK)
    assert [g.id for g in groups.stated] == ["G-NET-EXP"]
    assert [g.id for g in groups.pack] == ["G-NET-INV", "G-NET-CFG"]
    assert [g.id for g in groups.research] == ["G-NET-COV", "G-BAT-4"]
    assert [g.id for g in groups.shared] == ["G-DS-1", "G-WEEE-2"]
    # one question (firmware), nothing answered, nothing published
    assert cs.question is not None and cs.question.text == PACK.clarify.question  # type: ignore[union-attr]
    assert list(_answers(cs)) == ["Yes, always upgrade first", "Only for core sites"]
    assert cs.answer is None and _published() == before


def test_tn_01_compose_start_makes_only_a_draft():
    before = _published()
    out = ok(call("compose.start", {"org_unit_id": ORG, "text": TEXT}, "planner-a"))
    cs = out["change_set"]
    assert out["status"] == "draft" and cs["pack"] == "telecom_network" and cs["by_model"] is False
    assert len(cs["systems"]) == 8 and len(cs["kpis"]) == 6 and cs["question"] is not None
    assert [c["kind"] for c in out["reading"]["controls"]] == ["check"]
    assert _published() == before


def test_tn_02_firmware_answer_scopes_rule():
    always_id, core_id = (_answers(draft_change_set(TEXT, ORG, packs=[PACK], answer=None))[k] for k in
                          ("Yes, always upgrade first", "Only for core sites"))  # fmt: skip
    always = draft_change_set(TEXT, ORG, packs=[PACK], answer=always_id)
    core = draft_change_set(TEXT, ORG, packs=[PACK], answer=core_id)
    for cs in (always, core):  # the answer is the rule's origin: not an assumption, and the question is closed
        assert cs.question is None and cs.assumed == [] and len(cs.ops) == 1
        (op,) = cs.ops
        assert op.op == "add_step" and op.step == RULE and op.stage == "decide" and "BR-TN-FW" in op.note
        assert op.when[0].fact == "asset.firmware_major_gap" and op.when[0].value == 2
    assert (always.answer, core.answer) == (always_id, core_id)
    assert len(always.ops[0].when) == 1  # no scope: every site
    assert [(c.fact, c.value) for c in core.ops[0].when[1:]] == [("asset.site_kind", "core")]

    # TN-S8 (firmware two behind) at an edge site: `always` adds the upgrade step, `core_only` does not; at a core site both do
    edge = sample("TN-S8")
    core_site = sample("TN-S8") | {"asset.site_kind": "core"}

    def steps(cs: ChangeSet, case: dict[str, Any]) -> list[str]:
        d = decide(case, [], pack=apply_overlay(PACK, cs.ops))
        return [s["step"] for s in d.required_steps if s["step"] == RULE]

    assert steps(always, edge) == [RULE] and steps(core, edge) == []
    assert steps(always, core_site) == [RULE] and steps(core, core_site) == [RULE]
    assert decide(edge, [], pack=PACK).required_steps == []  # no answer, no rule


# ---------------------------------------------------------------- the model drafts first, the checks win (R16)
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


def _draft(**over: Any) -> dict[str, Any]:
    names = [s.name for s in PACK.data.systems]
    return {"pack": "telecom_network", "ops": [], "assumed": [], "kpis": [k.label for k in PACK.kpis], "systems": names,
            "question": None} | over  # fmt: skip


def test_tn_01_model_draft_passes_checks():
    runtime.set_loop(_scripted(_draft()))
    cs = draft_change_set(TEXT, ORG, packs=_packs(), answer=None, drafter=_drafter())
    assert cs.by_model is True and cs.pack == "telecom_network"
    assert len(cs.systems) == 8 and all(s.adapter for s in cs.systems) and len(cs.kpis) == 6
    assert cs.question is not None and cs.question.text == PACK.clarify.question  # type: ignore[union-attr]  # the pack's
    # a model's step is accepted when it applies; the answer's rule is the pack's option
    when = [{"fact": "asset.region", "op": "eq", "value": "US"}]
    step = {"id": "op-1", "op": "add_step", "stage": "decide", "step": "Network lead signs off", "when": when,
            "owner_role": "network_asset_manager"}  # fmt: skip
    runtime.set_loop(_scripted(_draft(ops=[step], assumed=["op-1"])))
    core_id = _answers(draft_change_set(TEXT, ORG, packs=[PACK], answer=None))["Only for core sites"]
    cs = draft_change_set(TEXT, ORG, packs=_packs(), answer=core_id, drafter=_drafter())
    assert cs.by_model is True and [o.step for o in cs.ops] == ["Network lead signs off", RULE]
    assert cs.assumed == ["op-1"]  # the model marked its own step; the answer's rule is not an assumption


def test_tn_01_model_skip_of_the_wipe_check_is_blocked():
    skip = {"id": "op-1", "op": "shortcut", "stage": "match", "to": "value", "when": []}  # skips `condition`: G-NET-CFG
    runtime.set_loop(_scripted(_draft(ops=[skip])))
    cs = draft_change_set(TEXT, ORG, packs=_packs(), answer=None, drafter=_drafter())
    assert cs.by_model is True and [o for o in cs.ops if o.op == "shortcut"] == []
    assert [b.guardrail for b in cs.blocked] == [next(g.text for g in PACK.guardrails if g.id == "G-NET-CFG")]


def test_tn_01_refused_model_draft_retries_once_then_the_deterministic_path():
    bad = {"id": "op-1", "op": "add_approver", "target": "GR-NOPE", "role": "Planner"}
    seen: list[int] = []
    runtime.set_loop(_scripted(_draft(ops=[bad]), seen))
    cs = draft_change_set(TEXT, ORG, packs=_packs(), answer=None, drafter=_drafter())
    assert len(seen) == 2 and cs.by_model is False  # the first try and one retry with the error
    assert cs == draft_change_set(TEXT, ORG, packs=_packs(), answer=None)


def test_tn_01_no_model_gives_the_deterministic_draft():
    plain = draft_change_set(TEXT, ORG, packs=_packs(), answer=None)
    assert plain == draft_change_set(TEXT, ORG, packs=_packs(), answer=None, drafter=_drafter()) and plain.by_model is False
