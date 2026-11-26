"""The customer overlay of a pack (plan 9, P9-1.3, story X-04). Implements registry entry I-4: `OverlayOp` (the typed
operations), `apply_overlay(pack, ops) -> Pack` and `rebase(old_base, new_base, ops) -> RebaseResult`.

A customer may only make a pack stricter, never looser. The five operations are: `tighten` a guardrail's parameter,
`add_approver` to a guardrail, `add_step` (an extra step at a stage), `shortcut` (skip the stages between two) and
`set_param` (a pack-published parameter, inside its range). Nothing relaxes, suspends or removes a guardrail, and a
shortcut that skips a Compliance guardrail or an active Compliance gate is refused by looking at the stage graph (the
`when` condition never narrows it away: a compliance rule applies to every item).

Owns: the op models, `parse_ops`, `OverlayError` (code and the texts of the registry), `apply_overlay`, `rebase`.
Never does: read a session or the clock, save anything, or run a diversion (`decide_case`, P9-1.5, runs them). The
overlay approval and its storage are `di.services.actions.overlays` and `di.repositories.overlays`.

The pack's customer parts: `customer_layer.editable` (the fields the Modeler offers; a field can be tightened only when
it is the guardrail's `param.field`, the one that says which way is stricter), `customer_layer.params` (the parameters
a customer may set, inside min and max) and `diversions` (written here, never in a pack file).
A shortcut to a route skips the stages strictly between its stage and `decide`: the decide stage itself always runs,
so its guardrails still apply (R20 runs guardrails before diversions). `jsonpatch` and `deepdiff` are not used: the
five operations and the stage graph need neither.
"""

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from di.services.modeler.gates import Cond, pack_gates
from di.services.modeler.pack import Diversion, Pack, PackGuardrail
from di.services.modeler.stages import STAGE_KEYS, STAGE_LABELS, StageKey


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^op-\d+$")
    by: str = ""
    note: str = ""


class Tighten(_Op):
    op: Literal["tighten"]
    target: str
    field: str
    value: float
    seen: float


class AddApprover(_Op):
    op: Literal["add_approver"]
    target: str
    role: str


class AddStep(_Op):
    op: Literal["add_step"]
    stage: StageKey
    when: list[Cond] = Field(default_factory=list)
    step: str
    owner_role: str


class Shortcut(_Op):
    op: Literal["shortcut"]
    stage: StageKey
    when: list[Cond] = Field(default_factory=list)
    to: str


class SetParam(_Op):
    op: Literal["set_param"]
    path: str
    value: float
    seen: float


OverlayOp = Annotated[Tighten | AddApprover | AddStep | Shortcut | SetParam, Field(discriminator="op")]
_OPS: TypeAdapter[list[OverlayOp]] = TypeAdapter(list[OverlayOp])


def parse_ops(raw: Sequence[Mapping[str, Any]]) -> list[OverlayOp]:
    """The typed operations of stored or submitted JSON; ids must be unique. ValueError names the first problem."""
    ops = _OPS.validate_python([dict(r) for r in raw])
    ids = [o.id for o in ops]
    if len(set(ids)) != len(ids):
        raise ValueError("operation ids must be unique")
    return ops


def ops_json(ops: Sequence[OverlayOp]) -> list[dict[str, Any]]:
    """The operations as stored JSON."""
    return [o.model_dump(mode="json") for o in ops]


class OverlayError(ValueError):
    """A refused operation: `op_id`, `code` (weakens, locked, not_editable, skips_compliance, unknown_target,
    out_of_range), the message of the registry, and for a skipped compliance rule `guardrail` (its id, for the audit)."""

    def __init__(self, op_id: str, code: str, message: str, guardrail: str | None = None) -> None:
        self.op_id, self.code, self.message, self.guardrail = op_id, code, message, guardrail
        super().__init__(message)


class Conflict(BaseModel):
    """An operation a person must decide: `mine` is the customer's value and `theirs` the pack's; `op` is the operation as
    the customer made it, so "Keep mine" can save it again."""

    model_config = ConfigDict(frozen=True)

    op_id: str
    kind: Literal["target_gone", "changed_by_pack", "now_skips_compliance"]
    message: str
    mine: Any = None
    theirs: Any = None
    op: dict[str, Any] | None = None


class RebaseResult(BaseModel):
    """Every input operation ends in exactly one of `ops` (kept), `notes` (dropped, with the reason) or `conflicts`."""

    model_config = ConfigDict(frozen=True)

    ops: list[OverlayOp]
    conflicts: list[Conflict]
    notes: list[str] = Field(default_factory=list)


def _n(x: float) -> str:
    return f"{x:g}"


def _unknown(op_id: str, x: str, pack: Pack) -> OverlayError:
    return OverlayError(op_id, "unknown_target", f"No guardrail, stage, route or parameter {x} in {pack.key} v{pack.version}.")


def _guardrail(pack: Pack, gid: str) -> PackGuardrail | None:
    return next((g for g in pack.guardrails if g.id == gid), None)


def _replace(pack: Pack, g: PackGuardrail) -> Pack:
    return pack.model_copy(update={"guardrails": [g if x.id == g.id else x for x in pack.guardrails]})


# ---------------------------------------------------------------- the stage graph
def _skipped(op: Shortcut, pack: Pack) -> tuple[StageKey, ...]:
    """The stages a shortcut jumps over: strictly between its stage and a later stage, or, for a route, strictly between
    its stage and `decide`."""
    start = STAGE_KEYS.index(op.stage)
    if op.to in STAGE_KEYS:
        end = STAGE_KEYS.index(op.to)
        if end <= start:
            raise _unknown(op.id, op.to, pack)
    elif op.to in {r.id for r in pack.routes}:
        end = STAGE_KEYS.index("decide")
    else:
        raise _unknown(op.id, op.to, pack)
    return STAGE_KEYS[start + 1 : max(end, start + 1)]


def _compliance_skipped(pack: Pack, stages: Sequence[StageKey]) -> tuple[str, str, StageKey] | None:
    """The first Compliance guardrail or active Compliance gate held at one of the stages: (id, name, stage)."""
    gates = [g for g in pack_gates(pack) if g.type == "Compliance"]
    for st in stages:
        for gr in pack.guardrails:
            if gr.type == "Compliance" and gr.stage == st:
                return gr.id, gr.text, st
        for ga in gates:
            if ga.stage == st:
                return ga.id, ga.name, st
    return None


def _check_skip(op: Shortcut, pack: Pack) -> None:
    hit = _compliance_skipped(pack, _skipped(op, pack))
    if hit is not None:
        gid, name, stage = hit
        msg = f"Blocked: this skips the compliance guardrail {name} at {STAGE_LABELS[stage]}."
        gate = next((g for g in pack_gates(pack) if g.id == gid), None)
        note = (gate.params.get("skip_refusal") if gate is not None else None) or {}
        if note.get("name") and note.get("suggestion"):  # the pack's own wording for its gate (P9-11.12, MR-14)
            msg = (
                f"Blocked: this would bypass the compliance guardrail '{note['name']}'; ask for a change to the guardrail "
                f"instead. Suggestion: {note['suggestion']}."
            )
        raise OverlayError(op.id, "skips_compliance", msg, gid)


# ---------------------------------------------------------------- apply
def _tighten(pack: Pack, op: Tighten) -> Pack:
    g = _guardrail(pack, op.target)
    if g is None:
        raise _unknown(op.id, op.target, pack)
    param = g.param
    if param is None or op.field != param.field:  # only a field with a direction (`param.stricter`) can be tightened
        if g.locked:
            msg = f"{g.id} is a compliance guardrail locked by the pack: only tightening and extra approvers are allowed."
            raise OverlayError(op.id, "locked", msg)
        raise OverlayError(op.id, "not_editable", f"{op.field} of {g.id} is not editable in this pack.")
    stricter = op.value > param.value if param.stricter == "higher" else op.value < param.value
    if not stricter:
        msg = f"{g.id} can only be tightened: {op.field} {_n(op.seen)} → {_n(op.value)} weakens it."
        raise OverlayError(op.id, "weakens", msg)
    if not param.min <= op.value <= param.max:
        raise OverlayError(op.id, "out_of_range", f"{g.id}.{op.field} must be between {_n(param.min)} and {_n(param.max)}.")
    return _replace(pack, g.model_copy(update={"param": param.model_copy(update={"value": op.value})}))


def _add_approver(pack: Pack, op: AddApprover) -> Pack:
    g = _guardrail(pack, op.target)
    if g is None:
        raise _unknown(op.id, op.target, pack)
    if op.role in g.approvers:
        return pack
    return _replace(pack, g.model_copy(update={"approvers": [*g.approvers, op.role]}))


def _set_param(pack: Pack, op: SetParam) -> Pack:
    layer = pack.customer_layer
    rng = layer.params.get(op.path)
    if rng is None:
        raise _unknown(op.id, op.path, pack)
    if not rng.min <= op.value <= rng.max:
        raise OverlayError(op.id, "out_of_range", f"{op.path} must be between {_n(rng.min)} and {_n(rng.max)}.")
    params = {**layer.params, op.path: rng.model_copy(update={"value": op.value})}
    return pack.model_copy(update={"customer_layer": layer.model_copy(update={"params": params})})


def _divert(pack: Pack, op: AddStep | Shortcut) -> Pack:
    when = [c.model_dump() for c in op.when]
    if isinstance(op, Shortcut):
        _check_skip(op, pack)
        d = Diversion(op_id=op.id, stage=op.stage, when=when, kind="shortcut", to=op.to)
    else:
        d = Diversion(op_id=op.id, stage=op.stage, when=when, kind="step", step=op.step, owner_role=op.owner_role)
    return pack.model_copy(update={"diversions": [*pack.diversions, d]})


def _apply_one(pack: Pack, op: OverlayOp) -> Pack:
    if isinstance(op, Tighten):
        return _tighten(pack, op)
    if isinstance(op, AddApprover):
        return _add_approver(pack, op)
    if isinstance(op, SetParam):
        return _set_param(pack, op)
    return _divert(pack, op)


def apply_overlay(pack: Pack, ops: Sequence[OverlayOp]) -> Pack:
    """A new pack with the operations applied in order. The first refused operation raises `OverlayError`. The pack
    given is never changed."""
    out = pack
    for op in ops:
        out = _apply_one(out, op)
    return out


# ---------------------------------------------------------------- rebase
def _param_value(pack: Pack, g: str, field: str) -> float | None:
    gr = _guardrail(pack, g)
    return gr.param.value if gr and gr.param and gr.param.field == field else None


def _gone(op_id: str, what: str, new: Pack, mine: Any) -> Conflict:
    return Conflict(op_id=op_id, kind="target_gone", message=f"{what} is no longer in {new.key} v{new.version}.", mine=mine)


def _rebase_tighten(op: Tighten, new: Pack) -> tuple[OverlayOp | None, Conflict | None, str | None]:
    cur = _param_value(new, op.target, op.field)
    gr = _guardrail(new, op.target)
    if cur is None or gr is None or gr.param is None:
        return None, _gone(op.id, f"{op.target} {op.field}", new, op.value), None
    if op.seen == cur:
        return op, None, None
    stricter = op.value > cur if gr.param.stricter == "higher" else op.value < cur
    if stricter:
        return op.model_copy(update={"seen": cur}), None, None
    return None, None, f"{op.target}: the pack is now stricter ({_n(cur)}); your change is no longer needed."


def _rebase_param(op: SetParam, old: Pack, new: Pack) -> tuple[OverlayOp | None, Conflict | None]:
    cur = new.customer_layer.params.get(op.path)
    if cur is None:
        return None, _gone(op.id, op.path, new, op.value)
    if op.seen == cur.value:
        return op, None
    msg = f"{op.path}: the pack changed it to {_n(cur.value)} (v{old.version} to v{new.version}) while you set {_n(op.value)}."
    return None, Conflict(op_id=op.id, kind="changed_by_pack", message=msg, mine=op.value, theirs=cur.value)


def _rebase_one(op: OverlayOp, old: Pack, new: Pack) -> tuple[OverlayOp | None, Conflict | None, str | None]:
    if isinstance(op, Tighten):
        return _rebase_tighten(op, new)
    if isinstance(op, SetParam):
        kept, conflict = _rebase_param(op, old, new)
        return kept, conflict, None
    if isinstance(op, AddApprover):
        if _guardrail(new, op.target) is None:
            return None, _gone(op.id, op.target, new, op.role), None
        return op, None, None
    try:
        _divert(new, op)
    except OverlayError as e:
        kind = "now_skips_compliance" if e.code == "skips_compliance" else "target_gone"
        return None, Conflict(op_id=op.id, kind=kind, message=e.message, mine=op.id), None
    return op, None, None


def rebase(old_base: Pack, new_base: Pack, ops: Sequence[OverlayOp]) -> RebaseResult:
    """Move operations made on `old_base` onto `new_base` (E section 11.1), in order. A pack update never drops a
    customer change silently: each operation is kept (a stricter value wins, `seen` is brought up to date), dropped with
    a note (the pack is now at least as strict), or raised as a conflict for a person."""
    kept: list[OverlayOp] = []
    conflicts: list[Conflict] = []
    notes: list[str] = []
    for op in ops:
        got, conflict, note = _rebase_one(op, old_base, new_base)
        if got is not None:
            kept.append(got)
        if conflict is not None:
            conflicts.append(conflict.model_copy(update={"op": op.model_dump(mode="json")}))
        if note is not None:
            notes.append(note)
    return RebaseResult(ops=kept, conflicts=conflicts, notes=notes)
