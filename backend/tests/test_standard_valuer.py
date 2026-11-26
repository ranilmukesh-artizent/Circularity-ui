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
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")


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


# ---- P9-12.1: division, decay, fact alias, per-route conditions, validation ----


def _std(**more: Any):
    from di.services.modeler.valuers import standard

    return standard, _pack(**more)


def _by(vals: list, rid: str) -> dict:
    return next(v for v in vals if v["k"] == rid)


def test_standard_valuer_decay_and_table():
    pack = _pack()
    decay = {"decay": {"start": {"mul": [{"const": 1400}, {"const": 0.35}]}, "monthly": {"const": 0.03}, "months": {"const": 4}}}
    assert round(amount.evaluate(decay, {}, pack), 2) == 433.79
    assert amount.evaluate({"div": [{"const": 9}, {"const": 4}]}, {}, pack) == 2.25
    assert amount.evaluate({"fact": "a.b"}, {"a": {"b": 7}}, pack) == 7
    assert amount.evaluate({"table": "grade_cost", "by": ["grade"]}, {"grade": "C"}, pack) == 40
    standard, pk = _std(lines=[{"route": "rerent", "type": "v", "label": "Resale", "amount": decay}])
    assert _by(standard.value_routes({}, pk), "rerent")["gross"] == 433.79  # rounded to cents


def test_standard_valuer_div_by_zero_raises():
    with pytest.raises(AmountError, match="Division by zero"):
        amount.evaluate({"div": [{"const": 1}, {"const": 0}]}, {}, _pack())


def test_standard_valuer_conditions():
    standard, pk = _std(
        requires=[],
        routes=[
            {
                "route": "rerent",
                "eligible_if": {
                    "all": [
                        {"fact": "utilisation", "op": "ge", "value": 0.5},
                        {"not": {"fact": "damaged", "op": "eq", "value": True}},
                    ]
                },
                "ineligible_reason": "Utilisation is low or the unit is damaged",
            }
        ],
    )
    good = _by(standard.value_routes(dict(FACTS), pk), "rerent")
    assert good["ok"] is True and good["why"] == ""
    bad = _by(standard.value_routes(FACTS | {"utilisation": 0.2}, pk), "rerent")
    assert bad["ok"] is False and bad["why"] == "Utilisation is low or the unit is damaged"
    anyc = {
        "routes": [
            {
                "route": "rerent",
                "eligible_if": {"any": [{"fact": "x", "op": "exists"}, {"fact": "rate", "op": "in", "value": [40]}]},
            }
        ]
    }
    assert _by(standard.value_routes(dict(FACTS), _pack(**anyc)), "rerent")["ok"] is True


def test_standard_valuer_missing_fact_reported():
    line = {"route": "rerent", "type": "v", "label": "Income", "amount": {"fact": "rate"}}
    standard, pk = _std(lines=[line, {"route": "rerent", "type": "c", "label": "Prep", "amount": {"const": 5}}])
    v = _by(standard.value_routes({}, pk), "rerent")
    assert v["misses"] == ["rate"] and v["gross"] == 0 and v["cost"] == 5


def test_standard_valuer_validation_errors(tmp_path, monkeypatch):
    from di.services.modeler import pack as packmod
    from di.services.modeler.valuers import standard

    doc = _doc()
    doc["key"] = "bad_std_test"
    p = doc["valuer"]["params"]
    p["lines"][0]["amount"] = {"param": "no_such_param"}
    p["routes"] = [{"route": "rerent", "eligible_if": {"bogus": 1}}, {"route": "nowhere"}]
    msgs = standard.validate_valuer(parse_pack(doc))
    assert len(msgs) == 3 and any("no_such_param" in m for m in msgs)
    assert any("bogus" in m for m in msgs) and any("nowhere" in m for m in msgs)
    (tmp_path / "bad_std_test.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(packmod, "PACKS_DIR", tmp_path)
    packmod.load_pack.cache_clear()
    try:
        with pytest.raises(PackError):
            packmod.load_pack("bad_std_test")
    finally:
        packmod.load_pack.cache_clear()


def test_standard_valuer_has_no_eval():
    import re

    from di.services.modeler.valuers import standard

    for mod in (standard, amount):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert not re.search(r"\b(eval|exec|getattr)\(", src.split('"""', 2)[2]), mod.__name__
