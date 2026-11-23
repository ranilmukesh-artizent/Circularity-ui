"""MVP-2.5: validating a flow (Domain spec D6; the prototype's fValidate), messages verbatim."""

import copy

import pytest

from di.core import golden
from di.services.modeler.flow import default_flow, fe
from di.services.modeler.templates import load_template
from di.services.modeler.validate import Check, blocking, validate_flow

TF = load_template("tool_fleet")
FLOWS = {c["name"]: {"nodes": c["flow"]["n"], "edges": c["flow"]["e"]} for c in golden.load("po/compile_cases")["cases"]}
CASES = golden.load("po/validate_cases")["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_validate_matches_golden(case):
    checks = validate_flow(TF, FLOWS[case["name"]])
    assert [list(c) for c in checks] == case["checks"]
    assert all(isinstance(c, Check) for c in checks)


def test_validate_covers_the_five_flows():
    assert len(CASES) == 5 and {c["name"] for c in CASES} == set(FLOWS)


def test_guardrail_bypass_fails():
    f = default_flow(TF)
    f["edges"].append(fe("in", "p-resell"))
    fails = blocking(validate_flow(TF, f))
    assert fails == [
        Check(
            "fail",
            "Guardrail bypass: Pre-owned sale can be reached without passing the guardrail gate. Remove that connection.",
            "p-resell",
        ),
        Check("fail", "Approval bypass: Pre-owned sale can be reached without owner approval.", "p-resell"),
    ]


def test_conflict_warns():
    f = default_flow(TF)
    r3 = copy.deepcopy(next(n for n in f["nodes"] if n["id"] == "r2"))
    r3.update({"id": "r3", "rid": "BR-03", "action": "exclude", "scope": {"grade": ["B", "C"]}})
    f["nodes"].append(r3)
    f["edges"] = [e for e in f["edges"] if e["id"] != "r2>dec"] + [fe("r2", "r3"), fe("r3", "dec")]
    checks = validate_flow(TF, f)
    assert checks[-1] == Check(
        "warn", "Conflict: BR-02 and BR-03 pull Tool pool in opposite directions for overlapping returns.", "r3"
    )
    assert not blocking(checks)
    # scopes that share no grade do not conflict
    r3["scope"] = {"grade": ["C", "D"]}
    assert not [c for c in validate_flow(TF, f) if c.msg.startswith("Conflict")]


def test_industrial_default_is_clean():
    t = load_template("industrial")
    checks = validate_flow(t, default_flow(t))
    assert [c.level for c in checks] == ["ok", "ok", "ok"]
    assert checks[0].msg == "Every step is connected from asset returned."
