"""Customer overlay actions (plan 9, P9-1.3; registry entry I-4; story X-04). A customer overlay is a pack's customer
changes (di.services.modeler.overlay) with their own maker-checker, as a flow has.

    overlay.save     act     {pack_key, org_unit_id, ops, resolved?}   the draft (checked against the pack: tighten
                                                         only; `resolved` drops those conflicts); agents may draft
    overlay.submit   act     {pack_key, org_unit_id}     draft -> review (no conflicts left, still valid)
    overlay.approve  commit  {pack_key, org_unit_id}     review -> pub: the draft is in force from the next decision (not
                                                         by anyone who saved, submitted or rebased this draft: journal)
    overlay.reject   commit  {pack_key, org_unit_id, reason}   review -> draft, the reason kept as a note
    overlay.rebase   act     {pack_key, org_unit_id}     the ops onto the pack's newer version, as a draft with the
                                                         `conflicts` and `notes` the rebase found; agents may prepare it

Approve and reject are in `FORBIDDEN_ACTIONS`: no agent runs them, however the call arrives. The org scope is the
overlay's org unit, checked as the flow actions do (a tenant-scoped person reaches only their units). A refused compliance
skip is audited: a `domain_event` `overlay.blocked` is written in its own transaction (the refusal rolls the call's back).

The refusal of an operation is a `validation_error` carrying the message of `OverlayError` and, beside it, `op_id` and
`overlay_code` (the registry's `code`, renamed because `code` is the error's own field).
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import overlays as repo
from di.repositories.orgs import units
from di.repositories.overlays import OverlayRow
from di.repositories.packs import active_pack
from di.services.actions.modeler import MAKER_CHECKER, _boundary, _org_ok
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.overlay import OverlayError, OverlayOp, apply_overlay, ops_json, parse_ops, rebase
from di.services.modeler.pack import Pack, pack_keys

_MANAGE, _APPROVE = "manageFlows", "approve.flows"
_STR = {"req": True, "t": "string"}
_REF = {"pack_key": _STR, "org_unit_id": _STR}


def _declare(action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("overlay.save", "Save a customer overlay", "edit customer overlays",
         "Save a customer's tightening changes to a pack as a draft, checked against the pack.", "act",
         {**_REF, "ops": {"req": True, "t": "array"}, "resolved": {"t": "array"}}, _MANAGE)  # fmt: skip
_declare("overlay.submit", "Submit a customer overlay", "submit customer overlays",
         "Send a draft customer overlay to a different person for approval.", "act", _REF, _MANAGE)  # fmt: skip
_declare("overlay.approve", "Approve a customer overlay", "approve customer overlays",
         "Approve a submitted customer overlay; it applies to the org's decisions from then on.", "commit", _REF,
         _APPROVE)  # fmt: skip
_declare("overlay.reject", "Return a customer overlay to draft", "return customer overlays",
         "Return a submitted customer overlay to its maker with a reason.", "commit",
         {**_REF, "reason": {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}},
         _APPROVE)  # fmt: skip
_declare("overlay.rebase", "Rebase a customer overlay", "rebase customer overlays",
         "Move a customer overlay onto the pack's newer version as a draft, with its conflicts and notes.", "act", _REF,
         _MANAGE)  # fmt: skip

# a draft's history in the journal: these make someone its maker; an approval ends the draft
_MAKES, _ENDS = ("overlay.save", "overlay.submit", "overlay.rebase"), ("overlay.approve",)


# ---------------------------------------------------------------- helpers
def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    """The refusal for an unknown pack or org unit, or an org outside the actor's units."""
    if i["pack_key"] not in pack_keys():
        return "not_found", f"No pack {i['pack_key']}."
    org = i["org_unit_id"]
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if _org_ok(ctx, org) else _boundary(org)


def _in_force(i: dict[str, Any], ctx: CallContext) -> Pack:
    """The pack in force for the overlay's org: its published version, else the pack file (not the file alone)."""
    return active_pack(ctx.session, i["pack_key"], i["org_unit_id"])


def _label(i: dict[str, Any]) -> str:
    return f"{i['pack_key']} at {i['org_unit_id']}"


def _agent_refusal(ctx: CallContext) -> tuple[str, str] | None:
    if ctx.preparer:
        return "approval_required", "Customer overlays are approved or returned only by a person."
    return None


def makers(ctx: CallContext, row: OverlayRow) -> set[str]:
    """Everyone who saved, submitted or rebased the current draft (as `flow.approve` reads it, audit F3b): the journaled
    calls since the last approval, and the recorded maker."""
    rows = ctx.session.execute(
        text(
            "SELECT action, actor FROM action_journal WHERE NOT undone AND action = ANY(:acts) "
            "AND input->>'pack_key' = :p AND input->>'org_unit_id' = :o ORDER BY seq"
        ),
        {"acts": [*_MAKES, *_ENDS], "p": row.pack_key, "o": row.org_unit_id},
    )
    out: set[str] = set()
    for action, actor in rows:
        if action in _ENDS:
            out.clear()
        else:
            out.add(actor)
    return out | ({row.maker} if row.maker else set())


def _get(i: dict[str, Any], ctx: CallContext, for_update: bool = False) -> OverlayRow:
    row = repo.get(ctx.session, i["pack_key"], i["org_unit_id"], for_update=for_update)
    if row is None:
        raise ActionError("not_found", f"No customer overlay for {_label(i)}.")
    return row


def _wanted(row: OverlayRow | None, want: tuple[str, ...], msg: str) -> OverlayRow | tuple[str, str]:
    """The overlay when it is in one of the statuses, else the conflict refusal."""
    return row if row is not None and row.status in want else ("conflict", msg)


def _update(ctx: CallContext, row: OverlayRow, **cols: Any) -> None:
    json_cols = {"draft", "published", "conflicts", "notes"}
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k in json_cols else f"{k} = :{k}" for k in cols)
    vals = {k: (json.dumps(v) if k in json_cols and v is not None else v) for k, v in cols.items()}
    sql = f"UPDATE customer_overlay SET {sets}, updated_at = :now WHERE id = :id"  # noqa: S608 - column names are this module's; values are bound
    ctx.session.execute(text(sql), {**vals, "id": row.id, "now": ctx.now})


def _audit_blocked(i: dict[str, Any], op_id: str, guardrail: str | None, ctx: CallContext) -> None:
    """The blocked attempt, in its own transaction: the refusal rolls back the call's."""
    op = next((o for o in i["ops"] if isinstance(o, dict) and o.get("id") == op_id), None)
    payload = {"pack_key": i["pack_key"], "org_unit_id": i["org_unit_id"], "op": op, "guardrail": guardrail, "by": ctx.actor.id}
    with SessionLocal() as own:
        own.execute(
            text("INSERT INTO domain_event (type, payload, at) VALUES ('overlay.blocked', CAST(:p AS jsonb), :at)"),
            {"p": json.dumps(payload), "at": ctx.now},
        )
        own.commit()


def _refusal(e: OverlayError) -> tuple[str, str, dict[str, Any]]:
    code = "locked_guardrail" if e.code == "locked" else "validation_error"  # a locked guardrail is its own refusal (UC-17)
    return code, e.message, {"op_id": e.op_id, "overlay_code": e.code}


def _refused(pack: Pack, ops: list[OverlayOp]) -> OverlayError | None:
    """The refusal of the first operation that does not apply to the pack, else None."""
    try:
        apply_overlay(pack, ops)
    except OverlayError as e:
        return e
    return None


def _parse(raw: Any) -> list[OverlayOp] | tuple[str, str]:
    try:
        return parse_ops(raw)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return "validation_error", f"The operations are not valid ({where}): {first['msg']}."
    except ValueError as e:
        return "validation_error", f"The operations are not valid: {e}."


# ---------------------------------------------------------------- save
@guard("overlay.save")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _reach(i, ctx):
        return bad
    ops = _parse(i["ops"])
    if isinstance(ops, tuple):
        return ops
    err = _refused(_in_force(i, ctx), ops)
    if err is None:
        return None
    if err.code == "skips_compliance":
        _audit_blocked(i, err.op_id, err.guardrail, ctx)
    return _refusal(err)


@implement("overlay.save")
def save(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    pack = _in_force(i, ctx)
    ops = [o.model_copy(update={"by": o.by or ctx.actor.id}) for o in parse_ops(i["ops"])]
    row = repo.get(ctx.session, i["pack_key"], i["org_unit_id"], for_update=True)
    mine = ops_json(ops)
    if row is None:
        ctx.session.execute(
            text(
                "INSERT INTO customer_overlay (pack_key, org_unit_id, base_version, draft, draft_base_version, status, "
                "maker, updated_at) VALUES (:p, :o, :v, CAST(:d AS jsonb), :v, 'draft', :by, :now)"
            ),
            {
                "p": i["pack_key"],
                "o": i["org_unit_id"],
                "v": pack.version,
                "d": json.dumps(mine),
                "by": ctx.actor.id,
                "now": ctx.now,
            },
        )
    else:
        kept = {o.id for o in ops} | set(i.get("resolved") or [])
        left = [c for c in row.conflicts if c.get("op_id") not in kept]
        _update(
            ctx,
            row,
            status="draft",
            maker=ctx.actor.id,
            checker=None,
            draft=mine,
            draft_base_version=pack.version,
            conflicts=left,
        )
    return {
        "status": "draft",
        "pack_key": i["pack_key"],
        "org_unit_id": i["org_unit_id"],
        "log": f"Saved the overlay draft for {_label(i)}",
    }


# ---------------------------------------------------------------- submit, approve, reject
@guard("overlay.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _reach(i, ctx):
        return bad
    row = _wanted(
        repo.get(ctx.session, i["pack_key"], i["org_unit_id"]), ("draft",), f"The overlay for {_label(i)} has no draft to submit."
    )
    if isinstance(row, tuple):
        return row
    if row.conflicts:
        return "conflict", "Resolve the conflicts before submitting."
    ops = _parse(row.draft or [])
    if isinstance(ops, tuple):
        return ops
    err = _refused(_in_force(i, ctx), ops)
    return _refusal(err) if err else None


@implement("overlay.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _get(i, ctx, for_update=True)
    _update(ctx, row, status="review")
    return {"status": "review", "log": f"Submitted the overlay for {_label(i)} for approval"}


@guard("overlay.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    if bad := _agent_refusal(ctx):
        return bad
    row = _wanted(
        repo.get(ctx.session, i["pack_key"], i["org_unit_id"]),
        ("review",),
        f"The overlay for {_label(i)} is not waiting for approval.",
    )
    if isinstance(row, tuple):
        return row
    return ("conflict", MAKER_CHECKER) if ctx.actor.id in makers(ctx, row) else None


@implement("overlay.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _get(i, ctx, for_update=True)
    if row.status != "review":  # returned or approved by someone else between the guard and this lock
        raise ActionError("conflict", f"The overlay for {_label(i)} is not waiting for approval.")
    ver = row.ver + 1
    base = row.draft_base_version or row.base_version
    _update(ctx, row, status="pub", ver=ver, checker=ctx.actor.id, published=row.draft or [], base_version=base,
            draft=None, draft_base_version=None, conflicts=[], notes=[])  # fmt: skip
    return {
        "status": "pub",
        "ver": ver,
        "log": f"Approved the overlay for {_label(i)} (v{ver}); it applies from the next decision",
    }


@guard("overlay.reject")
def reject_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    if bad := _agent_refusal(ctx):
        return bad
    row = _wanted(
        repo.get(ctx.session, i["pack_key"], i["org_unit_id"]),
        ("review",),
        f"The overlay for {_label(i)} is not waiting for approval.",
    )
    return row if isinstance(row, tuple) else None


@implement("overlay.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _get(i, ctx, for_update=True)
    notes = [*row.notes, f"Returned by {ctx.actor.id}: {i['reason'].strip()}"]
    _update(ctx, row, status="draft", checker=None, notes=notes)
    return {"status": "draft", "reason": i["reason"], "log": f"Returned the overlay for {_label(i)} to draft"}


# ---------------------------------------------------------------- rebase
def _rebase_source(row: OverlayRow) -> tuple[list[dict[str, Any]], str]:
    """The operations to move and the pack version they were made against: the draft if there is one, else the published."""
    return (row.draft, row.draft_base_version or row.base_version) if row.draft is not None else (row.published, row.base_version)


@guard("overlay.rebase")
def rebase_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    msg = f"The overlay for {_label(i)} is in review: return it to draft first."
    row = _wanted(repo.get(ctx.session, i["pack_key"], i["org_unit_id"]), ("draft", "pub"), msg)
    if isinstance(row, tuple):
        return row
    version = _in_force(i, ctx).version
    return ("conflict", f"Already on {version}.") if _rebase_source(row)[1] == version else None


@implement("overlay.rebase")
def rebase_overlay(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _get(i, ctx, for_update=True)
    new = _in_force(i, ctx)
    raw, base = _rebase_source(row)
    res = rebase(new.model_copy(update={"version": base}), new, parse_ops(raw))
    conflicts = [c.model_dump(mode="json") for c in res.conflicts]
    _update(ctx, row, status="draft", maker=ctx.actor.id, checker=None, draft=ops_json(res.ops), draft_base_version=new.version,
            conflicts=conflicts, notes=res.notes)  # fmt: skip
    return {
        "status": "draft", "ops": len(res.ops), "conflicts": conflicts, "notes": res.notes,
        "log": f"Rebased the overlay for {_label(i)} onto {new.key} v{new.version}",
    }  # fmt: skip
