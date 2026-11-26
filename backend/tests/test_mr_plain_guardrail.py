"""Plan 9, P9-11.14 (story MR-11): "Retiring a device younger than 5 years needs approval from clinical engineering", in words.

The rental fleet director states a guardrail in plain words. The configuration agent (P9-2.7) reads the sentence (a model first,
R16, here a `FunctionModel`; the deterministic reading when no model answers) into one typed overlay operation, `add_approver` in
its new-guardrail shape (shared with P9-10.14): an Approval guardrail `AP-MR-RETIRE5` at the decide stage (stage 5), when the route
is retire and `asset.age_years < 5`, approved by `clinical_engineering`. Code checks what the words became against the pack and
wins over the model: an id the pack already has, an approver or route the pack does not have, or words the description does not
contain are refused (one retry, then the words alone answer), never an operation. The history counts the 11 past retirements of a
device under 5 years old (*modelled*, a sample). The guardrail is the customer's overlay, so it goes through maker-checker like any
overlay; no agent approves it (golden rule 10: `overlay.approve` is in `forbidden.py`). Once published, MR-S8 (a 4-year-old
monitor whose repair exceeds its residual value) is held for clinical engineering with an item in My work. Compliance wording of
the pack is reviewed by Kinective's Legal team before it is relied on.
"""

# ruff: noqa: E501 - long lines in fixtures and asserts
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.repositories.replay import Batch
from di.services.actions.overlays import MAKER_CHECKER
from di.services.agents import runtime
from di.services.agents.config_agent import draft_change_set
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.modeler import plain_guardrail
from di.services.modeler import plain_words_medical_rental as words
from di.services.modeler.compile import FlowVersion
from di.services.modeler.gates import conds_hold
from di.services.modeler.overlay import AddApprover, OverlayError, apply_overlay, ops_json, parse_ops, rebase
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import medical_rental as M
from di.services.replay import run
from tests.helpers import call, client, h
from tests.test_medical_rental_paths import (  # noqa: F401 - `fresh` is the module's autouse fixture
    SCENARIOS,
    _get,
    _open,
    _write,
    fresh,
    tag,
)

models.ALLOW_MODEL_REQUESTS = False

ORG, PACK = "Customer A", "medical_rental"
SENTENCE = "Retiring a device younger than 5 years needs approval from clinical engineering"
NOW = datetime(2026, 11, 24, tzinfo=UTC)
WHEN = {"all": [{"route": "retire"}, {"fact": "asset.age_years", "op": "lt", "value": 5.0}]}
NEW = {"guardrail_id": "AP-MR-RETIRE5", "type": "Approval", "stage": "decide", "when": WHEN, "approver": "clinical_engineering"}


def _packs() -> list:
    """What `compose.start` gives the agent when the pack is named: that pack alone (the sentence is about its guardrails)."""
    return [load_pack(PACK)]


def _draft(words_: str = SENTENCE, **kw: Any):
    return draft_change_set(words_, ORG, packs=_packs(), answer=None, **kw)


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


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


def _model_op(**over: Any) -> dict[str, Any]:
    return {"id": "op-1", "op": "add_approver", "text": SENTENCE, **NEW, **over}


def _model(*ops: dict[str, Any]) -> dict[str, Any]:
    return {"pack": PACK, "ops": list(ops), "assumed": [], "kpis": [], "systems": [], "question": None}


@pytest.fixture
def no_model():
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)


def _new_ops(cs: Any) -> list[AddApprover]:
    return [o for o in cs.ops if isinstance(o, AddApprover) and o.guardrail_id is not None]


def _the_op(cs: Any) -> AddApprover:
    got = _new_ops(cs)
    assert len(got) == 1, cs.ops
    return got[0]


# ---------------------------------------------------------------- the sentence places the guardrail
def test_mr_11_sentence_places_approval_guardrail(no_model):
    cs = _draft()
    assert cs.pack == PACK and cs.by_model is False and cs.blocked == [] and cs.assumed == []
    op = _the_op(cs)
    assert op.model_dump(mode="json", exclude={"id", "by", "note", "target", "role"}) == {
        "op": "add_approver",
        "text": SENTENCE,
        **NEW,
    }
    pack = load_pack(PACK)
    assert [s.key for s in pack.stages].index(op.stage or "") == 4  # stage 5 of 7
    placed = apply_overlay(pack, cs.ops)
    g = next(x for x in placed.guardrails if x.id == "AP-MR-RETIRE5")
    assert (g.type, g.locked, g.owner, g.approvers) == ("Approval", False, "clinical_engineering", ["clinical_engineering"])
    d = next(x for x in placed.diversions if x.guardrail_id == "AP-MR-RETIRE5")
    assert (d.kind, d.route, d.stage) == ("approval", "retire", "decide")
    assert d.when == [{"fact": "asset.age_years", "op": "lt", "value": 5.0}]
    assert all(a == b for a, b in zip(pack.guardrails, placed.guardrails, strict=False))  # the pack's own guardrails, untouched
    assert "AP-MR-RETIRE5" not in [x.id for x in pack.guardrails]  # apply_overlay never changes the pack given


def test_mr_11_model_reads_the_words_and_code_checks_them():
    runtime.set_loop(_scripted(_model(_model_op())))
    cs = _draft(drafter=_drafter())
    assert cs.by_model is True and cs.blocked == []
    op = _the_op(cs)
    assert (op.guardrail_id, op.approver) == ("AP-MR-RETIRE5", "clinical_engineering")
    runtime.set_loop(None)


def test_mr_11_the_words_win_over_the_model_for_the_same_guardrail():
    """The code read `AP-MR-RETIRE5` in the sentence: the model's copy (another age) is dropped, the guardrail is placed once."""
    other = {"all": [{"route": "retire"}, {"fact": "asset.age_years", "op": "lt", "value": 50.0}]}
    runtime.set_loop(_scripted(_model(_model_op(when=other))))
    cs = _draft(drafter=_drafter())
    assert cs.by_model is True
    assert _the_op(cs).when is not None and _the_op(cs).when.model_dump(mode="json") == WHEN


def test_mr_11_model_cannot_replace_a_guardrail_of_the_pack():
    """A new approval that takes the id of a guardrail of the pack (a locked compliance one, or its repair approval) is refused
    by the overlay: one retry, then the words alone answer."""
    for gid in ("G-MED-DECON", "AP-MR-REPAIR"):
        seen: list[int] = []
        runtime.set_loop(_scripted(_model(_model_op(guardrail_id=gid)), seen))
        cs = _draft("Every device needs sign-off", drafter=_drafter())
        assert len(seen) == 2 and cs.by_model is False and _new_ops(cs) == [], gid
    runtime.set_loop(None)


def test_mr_11_model_cannot_name_a_role_a_route_or_words_the_description_lacks():
    for over in (
        {"guardrail_id": "AP-MR-BOARD", "approver": "the board"},
        {"guardrail_id": "AP-MR-SCRAP", "when": {"all": [{"route": "scrap"}]}},
        {"guardrail_id": "AP-MR-FREE", "text": "Anything goes without approval"},
    ):
        seen: list[int] = []
        runtime.set_loop(_scripted(_model(_model_op(**over)), seen))
        cs = _draft(drafter=_drafter())
        assert len(seen) == 2 and cs.by_model is False, over  # the first try, one retry with the error, then the words alone
        assert _the_op(cs).guardrail_id == "AP-MR-RETIRE5"
    runtime.set_loop(None)


def test_mr_11_a_sentence_that_removes_an_approval_places_nothing(no_model):
    cs = _draft("Retiring a device younger than 5 years does not need approval from clinical engineering")
    assert _new_ops(cs) == []
    assert _draft("We rent infusion pumps to hospitals").ops == []


def test_mr_11_the_guardrail_cannot_be_said_twice_or_over_a_pack_guardrail(no_model):
    pack = apply_overlay(load_pack(PACK), _draft().ops)
    with pytest.raises(OverlayError) as e:  # the id is taken: the overlay refuses a second one
        apply_overlay(pack, _draft().ops)
    assert e.value.code == "duplicate"
    own = _the_op(_draft()).model_copy(update={"guardrail_id": "G-MED-DECON"})
    with pytest.raises(OverlayError) as e2:
        apply_overlay(load_pack(PACK), [own])
    assert e2.value.code == "duplicate"
    nobody = _the_op(_draft()).model_copy(update={"approver": "nobody"})
    with pytest.raises(OverlayError) as e3:
        apply_overlay(load_pack(PACK), [nobody])
    assert e3.value.code == "unknown_target"


def test_mr_11_an_op_is_stored_as_json_and_read_back(no_model):
    ops = _draft().ops
    assert parse_ops(ops_json(ops)) == ops
    pack = load_pack(PACK)
    assert [o.id for o in rebase(pack, pack, ops).ops] == ["op-1"]


# ---------------------------------------------------------------- the history counts it
def test_mr_11_replay_counts_11(no_model):
    """Over the 1,880 devices of the sample history exactly 11 retirements are of a device under 5 years old (*modelled*)."""
    pack = apply_overlay(load_pack(PACK), _draft().ops)
    rows = M.rows()
    its = M.items(rows, pack, NOW)
    assert len([r for r in rows if r["actual_route"] == "retire" and int(r["fact.age_years"]) < 5]) == 11
    assert plain_guardrail.would_change(_the_op(_draft()), words.history_items(its), pack) == 11  # by the route taken
    report, _fig = M.replay(Batch(1, PACK, ORG, len(its), 0, None, {}), its, FlowVersion(1, 1, ()), pack, run.replay)
    assert report.n_decided == 1880  # the pack with the guardrail replays as before (the facts of a history row are short names)


# ---------------------------------------------------------------- maker-checker, then live
def _save(ops: list, maker: str = "admin") -> dict[str, Any]:
    body = {"pack_key": PACK, "org_unit_id": ORG}
    _ok(call("overlay.save", body | {"ops": ops_json(ops)}, maker))
    _ok(call("overlay.submit", body, maker))
    return body


def test_mr_11_maker_checker_then_live(no_model):
    body = _save(_draft().ops)
    with SessionLocal() as s:
        assert "AP-MR-RETIRE5" not in [g.id for g in live_pack(s, {"template": PACK, "owner": ORG}).guardrails]  # in review
    refused = call("overlay.approve", body, "admin")  # the maker
    assert refused["ok"] is False and refused["error"]["message"] == MAKER_CHECKER
    assert "overlay.approve".startswith(FORBIDDEN_ACTIONS)
    agent = client.post(
        "/api/actions/overlay.approve", json=body, headers=h("approver") | {"X-Circularity-Preparer": "coordinator"}
    )
    assert agent.status_code == 403 and agent.json()["error"]["code"] == "approval_required", agent.json()
    _ok(call("overlay.approve", body, "approver"))  # a different person
    with SessionLocal() as s:
        assert "AP-MR-RETIRE5" in [g.id for g in live_pack(s, {"template": PACK, "owner": ORG}).guardrails]
    c = _open(8, **SCENARIOS["MR-S8"])  # MR-S8: a 4-year-old monitor, repair over its residual value; four requests open
    assert c["recommendation"]["id"].startswith("rerent"), c["recommendation"]["id"]
    assert "AP-MR-RETIRE5" not in [x["id"] for x in c.get("approvalHolds", [])]  # it keeps the device: the guardrail is on retire
    in_service = (clock.now() - timedelta(days=1461)).date().isoformat()  # 4 years in service, as the asset system serves it
    _write("mr_assets", "devices", {"tag": tag(8), "deviceClass": "patient_monitor", "model": "IP-200", "serial": 2008,
                                    "org_unit_id": ORG, "inServiceDate": in_service})  # fmt: skip
    _write("mr_rental", "demand", {"tag": tag(8), "depot": {"latitude": 40.0, "longitude": -75.0}, "requests": [], "forecast": [],
                                   "org_unit_id": ORG})  # fmt: skip
    with SessionLocal() as s:  # no request is open any more: the device is retired (re-evaluated, as a person asks)
        c2 = cases.get(s, c["id"], for_update=True)
        assert c2 is not None
        intake.revalue(s, c2)
        cases.save(s, c2)
        s.commit()
    c = _get(c["id"])
    assert c["recommendation"] is not None and c["recommendation"]["id"] == "retire", c["recommendation"]
    holds = [x for x in c["approvalHolds"] if x["id"] == "AP-MR-RETIRE5"]
    assert len(holds) == 1 and holds[0]["owner"] == "clinical_engineering" and holds[0]["route"] == "retire", c["approvalHolds"]
    assert holds[0]["action"] == "Retire and harvest when repair exceeds residual value"
    with engine.connect() as conn:
        items = conn.execute(
            text("SELECT owner_role, action FROM work_item WHERE case_id = :c AND type = 'AP-MR-RETIRE5' AND status = 'open'"),
            {"c": c["id"]},
        ).all()
    assert [(i.owner_role, i.action) for i in items] == [("Approver", "Retire and harvest when repair exceeds residual value")]
    assert "decision.approve".startswith(FORBIDDEN_ACTIONS)
    assert _get(c["id"])["approval"] is None  # nobody approved it: it waits for clinical engineering


def test_mr_11_the_age_bound_is_strict(no_model):
    pack = apply_overlay(load_pack(PACK), _draft().ops)
    d = next(x for x in pack.diversions if x.guardrail_id == "AP-MR-RETIRE5")

    def under(age: float) -> bool:
        return conds_hold(d.when, {"asset": {"age_years": age}}, pack)

    assert under(4) and under(4.9) and not under(5) and not under(7)
    assert (
        plain_guardrail.read_clause("Retiring a device older than 8 years needs approval from clinical engineering", pack)
        is not None
    )
