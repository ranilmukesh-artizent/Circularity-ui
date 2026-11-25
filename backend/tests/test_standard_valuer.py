"""P9-1.9 (I-21, R19, story X-01): the standard valuer prices a pack's routes from its value lines (data, no engine code).
`rental_std_test` is imported, submitted and approved through the actions, a case is opened on it and decided by the one
decider (`decide_case`). The amount grammar is JSON only (never `eval`); an unknown operation is refused when the pack is
parsed (PackError part 9). Every test ends with the starting state."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.cases import store
from di.services.cases.decide import decide_case
from di.services.modeler import simulate as sim
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import PackError, parse_pack
from di.services.modeler.valuers import VALUERS, amount
from di.services.modeler.valuers.amount import AmountError
from tests import flowkit, starting
from tests.helpers import call

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "packs" / "rental_std_test.json"
FACTS = {"rate": 40, "months": 12, "utilisation": 0.8, "prep": 60}
ORG = "Customer A"
ORDER = ("gates", "compliance", "rules", "rank")


def _doc() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _pack(**more: Any):
    d = _doc()
    d["valuer"]["params"] |= more
    return parse_pack(d)


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _publish() -> None:
    pid = int(ok(call("pack.import", {"doc": _doc()}, "admin"))["id"])
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))


def _open(asset: str, facts: dict[str, Any]) -> dict:
    body = {"org_unit_id": ORG, "template_key": "rental_std_test", "asset_key": asset, "reason": "manual", "facts": facts}
    return call("case.open", body, "planner-a")


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _route(d, rid: str) -> dict:
    return next(r for r in d.routes if r["id"] == rid)


def test_x_01_new_pack_needs_no_engine_code():
    _publish()
    cid = ok(_open("RS-1", FACTS))["case_id"]
    c = _case(cid)
    assert c["template"] == "rental_std_test" and c["recommendation"]["id"] == "rerent"
    assert c["recommendation"]["net"] == pytest.approx(324)  # 40 x 12 x 0.8 - 60
    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    assert d.route == "rerent" and d.net == pytest.approx(324) and d.trace == ORDER
    assert {r["id"]: round(r["net"]) for r in d.routes} == {"rerent": 324, "refurbish": 282, "dispose": 15}
    assert [t["label"] for t in _route(d, "rerent")["terms"]] == ["Re-rent income", "Preparation"]
    assert [t["amt"] for t in _route(d, "rerent")["terms"]] == pytest.approx([384, -60])
    assert "standard" in VALUERS


def test_x_01_standard_case_missing_min_field_refused():
    _publish()
    r = _open("RS-2", {"rate": 40})
    assert r["error"]["code"] == "validation_error" and "months" in r["error"]["message"], r


def test_amount_rejects_unknown_ops():
    doc = _doc()
    doc["valuer"]["params"]["lines"][0]["amount"] = {"pow": [{"const": 2}, {"const": 3}]}
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert e.value.part == 9 and "Unknown amount pow at" in str(e.value)
    with pytest.raises(AmountError, match="Unknown amount pow at lines"):
        amount.check({"pow": []}, "lines")
    doc = _doc()
    doc["valuer"]["params"]["lines"][0]["route"] = "nowhere"
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert e.value.part == 9


def test_amount_grammar_evaluates():
    pack = _pack()
    case = {"a": {"b": 3}, "grade": "B", "n": 2.5}
    ev = lambda x: amount.evaluate(x, case, pack)  # noqa: E731
    assert ev({"const": 4}) == 4 and ev({"field": "a.b"}) == 3 and ev({"param": "scrap"}) == 20
    assert ev({"table": "grade_cost", "by": ["grade"]}) == 25
    assert ev({"mul": [{"const": 2}, {"field": "n"}]}) == 5 and ev({"add": [{"const": 1}, {"const": 2}, {"const": 3}]}) == 6
    assert ev({"sub": [{"const": 5}, {"const": 2}]}) == 3 and ev({"min": [{"const": 5}, {"const": 2}]}) == 2
    assert ev({"max": [{"const": 5}, {"const": 2}]}) == 5 and ev({"round": {"field": "n"}}) == 3  # JS rounding, half up


def test_amount_missing_field_named():
    with pytest.raises(AmountError, match=r"The case has no rate \(needed at lines\[0\]\)") as e:
        amount.evaluate({"field": "rate"}, {}, _pack(), "lines[0]")
    assert e.value.path == "lines[0]"
    d = decide_case({"id": "X", "months": 12, "utilisation": 0.8, "prep": 60}, _pack(), FlowVersion(None, 1, ()))
    assert _route(d, "rerent")["excluded"] and "The case has no rate" in _route(d, "rerent")["failReason"]
    assert d.route == "refurbish" or d.route == "dispose"  # a route that cannot be valued is never recommended


def test_paths_agree_standard():
    _publish()
    cid = ok(_open("RS-3", FACTS))["case_id"]
    seen = {"opened": (_case(cid)["recommendation"]["id"], _case(cid)["recommendation"]["net"])}
    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    c = _case(cid)
    seen["reevaluated"] = (c["recommendation"]["id"], c["recommendation"]["net"])
    with SessionLocal() as s:
        pack, fv = live_pack(s, c), flow_version(s, c)
        d = decide_case(cid, pack, fv, session=s)
        seen["decide_case"] = (d.route, d.net)
        f = decide_case(dict(FACTS) | {"id": "F"}, pack, fv)
        seen["facts"] = (f.route, f.net)
        t = sim.simulate(
            __import__("di.services.modeler.templates", fromlist=["x"]).template_of_pack(pack),
            (),
            (),
            [c],
            lambda case, rules: sim.decision_to_sim(decide_case(case, pack, FlowVersion(None, fv.ver, tuple(rules)), session=s)),
        )
        assert t.flips == [] and t.dv == 0
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_order_invariant_standard():
    pack = parse_pack(_doc())
    facts = FACTS | {"utilisation": 0.3, "id": "OI"}  # the requirement fails: utilisation under 50 percent
    require = CompiledRule("R-1", {}, "require", "rerent", "send every unit to re-rent")
    d = decide_case(facts, pack, FlowVersion(None, 1, (require,)))
    rr = _route(d, "rerent")
    assert d.trace == ORDER and rr["excluded"] and rr["failReason"] == "Utilisation is under 50 percent"
    assert d.route != "rerent" and d.waived is False and d.rules_applied == []
    open_ids = [r["id"] for r in decide_case(facts, pack, FlowVersion(None, 1, ())).routes if not r["excluded"]]
    exclude = [CompiledRule(f"R-{i}", {}, "exclude", k, "no") for i, k in enumerate(open_ids)]
    w = decide_case(facts, pack, FlowVersion(None, 1, tuple(exclude)))  # nothing would stay eligible: waived
    assert w.waived is True and [r["id"] for r in w.routes if not r["excluded"]] == open_ids
    assert _route(w, "rerent")["excluded"]


def test_standard_decision_shape_and_rules():
    pack = parse_pack(_doc())
    from di.services.modeler.valuers import standard

    dec = standard.decide(dict(FACTS), pack, [])
    assert [v["k"] for v in dec["all"]] == ["rerent", "refurbish", "dispose"] and dec["best"]["k"] == "rerent"
    v = dec["all"][0]
    assert (v["gross"], v["cost"], v["hold"]) == pytest.approx((384, 60, 0)) and v["net"] == pytest.approx(324)
    assert v["lines"][0]["type"] == "v" and v["lines"][0]["amt"] == pytest.approx(384) and v["co2"] is None
    rule = [{"id": "R-1", "scope": {}, "action": "exclude", "path": "rerent", "text": "no re-rent"}]
    assert standard.decide(dict(FACTS), pack, rule)["best"]["k"] == "refurbish"
    assert copy.deepcopy(FACTS) == FACTS
