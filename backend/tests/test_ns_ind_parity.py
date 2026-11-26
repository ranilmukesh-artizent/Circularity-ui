"""P9-12.11 (story NS-IND-01): the industrial pack in the full pack format. The pack file now carries every part the format
asks for (prompts and a question, the seven stages and their agents, the customer layer with the six engine gates locked, the
21 demo systems, exception types, six KPIs, two worked questions and samples that name RT-1048 and seven book cases by id)
while the engine path stays as it was: `decide_case` gives the stored route and net of all 128 book cases (RT-1048
included), by every path, in the same order. A changed number or text is a bug (golden rule 1). Synthetic data."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from di.core.db import SessionLocal
from di.repositories.live_rules import flow_version, live_pack
from di.services.cases import store
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Pack, load_pack
from tests import starting

BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = BACKEND.parent / "fixtures" / "golden"
PACKS = BACKEND / "di" / "services" / "modeler" / "packs"
BOOK: list[dict[str, Any]] = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = json.loads((Path(__file__).parent / "fixtures" / "industrial_decisions.json").read_text(encoding="utf-8"))
SEVEN = ["RT-1001", "RT-1002", "RT-1004", "RT-1006", "RT-1027", "RT-1033", "RT-1104"]
ENGINE_GATES = ["Condition & life", "Post-intervention", "Policy & certification", "Demand fit", "Economics", "Sustainability"]
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")


@pytest.fixture(scope="module", autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def _stored(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


def _decided(cid: str, *rules: CompiledRule) -> Any:
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        return decide_case(cid, load_pack("industrial"), FlowVersion(None, 1, tuple(rules)), session=s)


def test_ns_ind_01_industrial_pack_parity():
    """All 128 book cases. The stored cases are the golden file's (route and net). `decide_case` re-values a case today (the
    seeded predictor, the active model's factors) and gives what it gave before the pack got its full format
    (`fixtures/industrial_decisions.json`, taken from the unchanged pack): the same route, net and open routes."""
    assert len(BOOK) == 128 and any(c["id"] == "RT-1048" for c in BOOK)
    with SessionLocal() as s:
        stored = {c["id"]: _stored(c) for c in (store.get(s, b["id"]) for b in BOOK) if c}
    assert stored == {c["id"]: _stored(c) for c in BOOK}
    bad = []
    for c in BOOK:
        d = _decided(c["id"])
        want = BASE[c["id"]]
        got = [d.route, round(d.net, 2), [r["id"] for r in d.routes if not r["excluded"]]]
        if got != want:
            bad.append((c["id"], want, got))
    assert bad == []
    hero = _decided("RT-1048")
    assert (hero.route, hero.net) == ("redeploy", 8314.0)  # RT-1048 as test_decide_gate_order pins it


def test_ns_ind_01_pack_validates_full_schema():
    doc = json.loads((PACKS / "industrial.json").read_text(encoding="utf-8"))
    schema = json.loads((PACKS / "pack.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(doc)
    p = load_pack("industrial")
    assert isinstance(p, Pack) and p.valuer.kind == "industrial" and p.valuer.params == {}
    assert [r.id for r in p.routes] == ["redeploy", "resale", "intparts", "relase", "material", "extparts", "exit"]
    assert all(t.strip() for t in p.prompts) and len(set(p.prompts)) == 3
    assert p.clarify is not None and p.clarify.question.endswith("?") and len(p.clarify.options) == 2
    assert [s.agent for s in p.stages] == ["Intake", "Intake", "Condition", "Valuation", "Routing", "Follow-through", "Analytics"]
    assert list(p.customer_layer.editable) == ENGINE_GATES and all(v == [] for v in p.customer_layer.editable.values())
    assert p.gates == [] and p.customer_layer.params == {}  # the engine's gates are the engine's: none moves into the pack
    sources = json.loads((GOLDEN / "sources.json").read_text(encoding="utf-8"))["sources"]
    assert [s.type for s in p.data.systems] == [s["type"] for s in sources] and len(p.data.systems) == 21
    assert {s.adapter for s in p.data.systems} == {"registry"} and sum(s.system_of_record for s in p.data.systems) == 1
    assert [e.id for e in p.runtime.exception_types] == [
        "condition_deterioration",
        "delayed_approval",
        "market_price_decline",
        "capacity_constraints",
        "missing_evidence",
    ]
    assert len(p.kpis) == 6 and len(p.analytics) == 2 and p.stories == ["NS-IND-01"]
    assert all(q.query for q in p.analytics)


def test_ns_ind_01_samples_name_the_book_cases_by_id():
    p = load_pack("industrial")
    samples = (p.replay.example or {})["samples"]
    assert [s["case"] for s in samples] == ["RT-1048", *SEVEN]
    book = {c["id"] for c in BOOK}
    assert {s["case"] for s in samples} <= book
    assert all(set(s) == {"case", "title"} for s in samples)  # an id and words: no copied facts
    assert p.replay.dataset is None  # no replay dataset: the sample list changes no behaviour


def test_paths_agree_industrial():
    """`decide_case` with the live pack and flow, with the pack file and no rules, and the baseline: one route and net."""
    for cid in ["RT-1048", *SEVEN]:
        with SessionLocal() as s:
            c = store.get(s, cid)
            assert c is not None
            d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
            again = decide_case(cid, load_pack("industrial"), FlowVersion(None, 1, ()), session=s)
        assert (d.route, round(d.net, 2)) == (again.route, round(again.net, 2)) == tuple(BASE[cid][:2]), (cid, d.route, d.net)


def test_order_invariant_industrial():
    """Gates, valuation, queue plan, business rules, rank, in that order; a rule that would leave nothing open is waived and a
    rule never brings back a route the gates closed (RT-1048 and seven book cases)."""
    for cid in ["RT-1048", *SEVEN]:
        base = _decided(cid)
        assert base.trace == ORDER, cid
        open_ids = [r["id"] for r in base.routes if not r["excluded"]]
        rules = [CompiledRule(f"R-{i}", {}, "exclude", k, "no") for i, k in enumerate(open_ids)]
        w = _decided(cid, *rules)
        assert w.trace == ORDER and w.rules_applied == [], cid
        assert [r["id"] for r in w.routes if not r["excluded"]] == open_ids, cid
        assert (w.route, round(w.net, 2)) == (base.route, round(base.net, 2)), cid
