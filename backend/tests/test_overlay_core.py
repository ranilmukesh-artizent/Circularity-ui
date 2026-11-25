"""P9-1.3 (I-4, story X-04, Review Focus 1 and 2): the customer overlay is tighten-only, never skips a compliance
guardrail, and survives a pack update by rebase. Pure: no database (the actions are in test_overlay_actions.py)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from di.services.modeler.overlay import (
    AddApprover,
    OverlayError,
    OverlayOp,
    SetParam,
    Shortcut,
    Tighten,
    apply_overlay,
    parse_ops,
    rebase,
)
from di.services.modeler.pack import GuardParam, Pack, ParamRange, load_pack, parse_pack

RECALL = Path(__file__).resolve().parent / "fixtures" / "packs" / "recall_test.json"


def _device() -> Pack:
    return load_pack("device")


def _floor(pack: Pack) -> float:
    g = next(g for g in pack.guardrails if g.id == "GR-D2")
    assert g.param is not None
    return g.param.value


def _with_floor(pack: Pack, value: float) -> Pack:
    gs = [
        g.model_copy(update={"param": g.param.model_copy(update={"value": value})}) if g.id == "GR-D2" and g.param else g
        for g in pack.guardrails
    ]
    return pack.model_copy(update={"guardrails": gs})


def _with_param(pack: Pack, path: str, value: float) -> Pack:
    layer = pack.customer_layer
    params = {**layer.params, path: ParamRange(value=value, min=50, max=90)}
    return pack.model_copy(update={"customer_layer": layer.model_copy(update={"params": params})})


def _tighten(value: float, seen: float = 0.55, op_id: str = "op-1") -> Tighten:
    return Tighten(id=op_id, op="tighten", target="GR-D2", field="floor", value=value, seen=seen)


def _recall_pack() -> Pack:
    return parse_pack(json.loads(RECALL.read_text(encoding="utf-8")))


def _no_gates(pack: Pack) -> Pack:
    """The pack with no gates: since P9-1.11 the shipped tool-fleet pack has a compliance gate at Match (G-CON-1),
    so the tests that need a pack where a shortcut skips nothing compliant take its gates off."""
    return pack.model_copy(update={"gates": []})


def _refused(pack: Pack, op: OverlayOp) -> OverlayError:
    with pytest.raises(OverlayError) as e:
        apply_overlay(pack, [op])
    return e.value


def test_x_04_tighten_only():
    out = apply_overlay(_device(), [_tighten(0.60)])
    assert _floor(out) == 0.60 and _floor(_device()) == 0.55  # a new pack; the loaded one is untouched
    err = _refused(_device(), _tighten(0.50))
    assert (err.code, err.op_id) == ("weakens", "op-1")
    assert str(err) == "GR-D2 can only be tightened: floor 0.55 → 0.5 weakens it."
    assert _refused(_device(), _tighten(0.55)).code == "weakens"  # equal is not stricter


def test_x_04_tighten_refusals_name_the_reason():
    assert _refused(_device(), _tighten(0.95)).code == "out_of_range"
    assert str(_refused(_device(), _tighten(0.95))) == "GR-D2.floor must be between 0.3 and 0.9."
    other = Tighten(id="op-2", op="tighten", target="GR-D2", field="max_lot", value=1, seen=0)
    assert str(_refused(_device(), other)) == "max_lot of GR-D2 is not editable in this pack."
    locked = Tighten(id="op-3", op="tighten", target="GR-D1", field="x", value=1, seen=0)
    assert _refused(_device(), locked).code == "locked"
    assert str(_refused(_device(), locked)) == (
        "GR-D1 is a compliance guardrail locked by the pack: only tightening and extra approvers are allowed."
    )
    gone = Tighten(id="op-4", op="tighten", target="GR-X", field="floor", value=1, seen=0)
    assert str(_refused(_device(), gone)) == "No guardrail, stage, route or parameter GR-X in device v2.7.0."


def test_x_04_compliance_skip_refused():
    op = Shortcut(id="op-1", op="shortcut", stage="receive", when=[{"fact": "age", "op": "lte", "value": 3}], to="condition")
    err = _refused(_recall_pack(), op)
    assert err.code == "skips_compliance"
    assert str(err) == "Blocked: this skips the compliance guardrail Safety recall check at Match and verify."
    assert err.guardrail == "G-TOOL-REC"
    # the same shortcut on the pack without the gate skips nothing compliant
    assert apply_overlay(_no_gates(load_pack("tool_fleet")), [op]).diversions[0].to == "condition"


def test_x_04_compliance_skip_is_a_graph_check_not_a_text_match():
    far = Shortcut(id="op-1", op="shortcut", stage="receive", to="decide")  # no `when`: it skips match too
    assert _refused(_recall_pack(), far).code == "skips_compliance"
    by_route = Shortcut(id="op-2", op="shortcut", stage="receive", to="redeploy")
    assert _refused(_recall_pack(), by_route).code == "skips_compliance"
    nothing_between = Shortcut(id="op-3", op="shortcut", stage="match", to="condition")
    assert len(apply_overlay(_recall_pack(), [nothing_between]).diversions) == 1


def test_x_04_add_approver_on_locked():
    pack = load_pack("tool_fleet")
    op = AddApprover(id="op-1", op="add_approver", target="GR-01", role="Finance")
    out = apply_overlay(pack, [op])
    assert next(g for g in out.guardrails if g.id == "GR-01").approvers == ["Finance"]
    assert next(g for g in pack.guardrails if g.id == "GR-01").approvers == []


def test_x_04_step_and_shortcut_become_diversions():
    ops = parse_ops([
        {"id": "op-1", "op": "add_step", "stage": "condition", "when": [{"fact": "age", "op": "gte", "value": 5}],
         "step": "Second grading check", "owner_role": "Engineer"},
        {"id": "op-2", "op": "shortcut", "stage": "value", "when": [], "to": "decide"},
    ])  # fmt: skip
    out = apply_overlay(_device(), ops)
    assert [(d.op_id, d.kind, d.stage, d.step, d.to, d.owner_role) for d in out.diversions] == [
        ("op-1", "step", "condition", "Second grading check", None, "Engineer"),
        ("op-2", "shortcut", "value", None, "decide", ""),
    ]
    assert out.diversions[0].when == [{"fact": "age", "op": "gte", "value": 5}]


def test_x_04_set_param_within_range():
    pack = _with_param(_device(), "GR-D2.rulMin", 70)
    ok = SetParam(id="op-1", op="set_param", path="GR-D2.rulMin", value=80, seen=70)
    assert apply_overlay(pack, [ok]).customer_layer.params["GR-D2.rulMin"].value == 80
    over = SetParam(id="op-2", op="set_param", path="GR-D2.rulMin", value=95, seen=70)
    assert str(_refused(pack, over)) == "GR-D2.rulMin must be between 50 and 90."
    unknown = SetParam(id="op-3", op="set_param", path="GR-D2.nope", value=1, seen=0)
    assert _refused(pack, unknown).code == "unknown_target"


def test_x_04_ops_are_typed():
    with pytest.raises(ValidationError):
        parse_ops([{"id": "op-1", "op": "loosen", "target": "GR-D2"}])
    with pytest.raises(ValidationError):
        parse_ops([{"id": "x", "op": "add_approver", "target": "GR-01", "role": "Finance"}])  # id is "op-<n>"


def test_x_04_rebase_keeps_stricter():
    old = _device()
    op = _tighten(0.60)
    res = rebase(old, _with_floor(old, 0.58), [op])
    assert [(o.id, o.value, o.seen) for o in res.ops if isinstance(o, Tighten)] == [("op-1", 0.60, 0.58)]
    assert (res.conflicts, res.notes) == ([], [])
    res = rebase(old, _with_floor(old, 0.65), [op])
    assert (res.ops, res.conflicts) == ([], [])
    assert res.notes == ["GR-D2: the pack is now stricter (0.65); your change is no longer needed."]
    res = rebase(old, old, [op])
    assert res.ops == [op] and res.notes == []  # `seen` equals the base: unchanged


def test_x_04_rebase_conflict_on_param():
    old = _with_param(_device(), "GR-D2.rulMin", 70)
    op = SetParam(id="op-1", op="set_param", path="GR-D2.rulMin", value=80, seen=70)
    res = rebase(old, _with_param(old, "GR-D2.rulMin", 75), [op])
    assert res.ops == [] and res.notes == []
    [c] = res.conflicts
    assert (c.op_id, c.kind, c.mine, c.theirs) == ("op-1", "changed_by_pack", 80, 75)


def test_x_04_rebase_target_gone():
    old = _device()
    gs = [g for g in old.guardrails if g.id != "GR-D2"]
    new = old.model_copy(update={"guardrails": gs})
    res = rebase(old, new, [_tighten(0.60)])
    assert (res.ops, res.notes) == ([], [])
    assert [(c.op_id, c.kind) for c in res.conflicts] == [("op-1", "target_gone")]


def test_x_04_rebase_diversion_that_now_skips_compliance_is_dropped():
    old = _no_gates(load_pack("tool_fleet"))
    op = Shortcut(id="op-1", op="shortcut", stage="receive", to="condition")
    assert rebase(old, old, [op]).ops == [op]
    res = rebase(old, _recall_pack(), [op])
    assert res.ops == [] and [(c.op_id, c.kind) for c in res.conflicts] == [("op-1", "now_skips_compliance")]


def test_x_04_pack_update_never_drops_customer_change():
    base = _with_param(_device(), "GR-D2.rulMin", 70)
    ops: list[OverlayOp] = [
        _tighten(0.60),
        SetParam(id="op-2", op="set_param", path="GR-D2.rulMin", value=80, seen=70),
        AddApprover(id="op-3", op="add_approver", target="GR-D1", role="Finance"),
        Shortcut(id="op-4", op="shortcut", stage="receive", to="condition"),
        AddApprover(id="op-5", op="add_approver", target="GR-GONE", role="Finance"),
    ]
    for new in (_with_floor(base, 0.58), _with_floor(base, 0.65), _with_param(base, "GR-D2.rulMin", 75), base):
        res = rebase(base, new, ops)
        assert len(res.ops) + len(res.notes) + len(res.conflicts) == len(ops)
        assert {o.id for o in res.ops} | {c.op_id for c in res.conflicts} <= {o.id for o in ops}
        assert "op-5" in {c.op_id for c in res.conflicts}  # a target the pack removed goes to a person, not away


def _guard(pack: Pack, gid: str) -> Any:
    return next(g for g in pack.guardrails if g.id == gid)


def test_x_04_models_are_the_packs():
    assert isinstance(_guard(_device(), "GR-D2").param, GuardParam)
