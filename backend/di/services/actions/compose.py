"""Composition actions (plan 9, P9-8.17; G C8, C12; R21): one approvable object made of the description's change set, the
mapping rows the owner accepted and the stage-agent settings, with maker-checker.

    compose.start          act     {org_unit_id, text, pack_key?}   the configuration agent (I-13) drafts the change set
    compose.answer         act     {id, answer}                     re-drafts with the answer to the pack's one question
    compose.editChangeSet  act     {id, ops}                        replaces the typed operations after the overlay validator
    compose.markStep       act     {id, step}                       describe, mapping or agents is done
    compose.get / .list    read    {id} / {org_unit_id?}            a composition; the compositions the person may see
    compose.submit         act     {id}                             refused with the blocking list; else a snapshot
    compose.sendBack       act     {id, step, reason, node_id?}     approve.packs: the reason (15+ characters) on the step
    compose.approve        commit  {id}                             approve.packs: applies the parts as one, or none of them

`managePacks` makes and submits, `approve.packs` sends back and approves (di.core.policy.EXTRA_PERMS); the composition's org
unit must be in the person's tenants. The maker is never the checker: whoever created, edited or submitted a composition cannot
approve it. Send back, approve and publish (P9-8.20) are in `FORBIDDEN_ACTIONS`; an agent may start, answer, edit and mark
steps (drafts). Approve runs inside the action's one transaction: the overlay goes through the overlay's own save and approve
handlers (`overlays.approve`; this actor the checker, the composition's maker the overlay's maker), then the accepted mapping
rows become a new mapping version per source (`mapping.save_version`), then the stage-agent settings are validated and kept in
the approved snapshot; any failure undoes all of it. Mapping rows come from `steps.mapping.fields` (`{source_id, row, state}`,
filled by P9-8.18); the stage settings from `steps.agents.settings` (`{stage, autonomy, threshold}`). The stage chain reads its
autonomy and threshold from the pack's stages today, so the settings are recorded and range-checked here and applied when the
`stageAgent.set` operation (I-13, F section 8c) exists.
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text

from di.connectors import mapping
from di.core import policy
from di.repositories import compositions as repo
from di.repositories import overlays as overlay_repo
from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.services.actions import overlays
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.agents.config_agent import MAX_TEXT, ChangeSet, ChangeSetError, draft_change_set, read_text
from di.services.agents.playbooks import pack_author
from di.services.modeler import compose as core
from di.services.modeler.overlay import OverlayError, apply_overlay, ops_json, parse_ops
from di.services.modeler.pack import Pack, pack_keys

_MANAGE, _APPROVE = "managePacks", "approve.packs"
MAKER_CHECKER = "Maker-checker: you composed this, so you cannot approve it."
_STR = {"req": True, "t": "string"}
_ID = {"id": {"req": True, "t": "number"}}
_EDITABLE = ("draft", "sent_back")


_OPS = {"req": True, "t": "array"}
_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}
# (id, title, description, risk, input, permission)
_DECLARED: tuple[tuple[str, str, str, Risk, dict[str, dict[str, Any]], str | None], ...] = (
    ("compose.start", "Start a composition", "Describe a business: the configuration agent drafts the change set.", "act",
     {"org_unit_id": _STR, "text": _STR, "pack_key": {"t": "string"}}, _MANAGE),
    ("compose.answer", "Answer the composition's question", "Answer the pack's one question; changes are redrafted.",
     "act", {**_ID, "answer": _STR}, _MANAGE),
    ("compose.editChangeSet", "Edit a composition's changes", "Replace the composition's changes, checked against the pack.",
     "act", {**_ID, "ops": _OPS}, _MANAGE),
    ("compose.markStep", "Mark a composition step done", "Mark the describe, mapping or agents step done.", "act",
     {**_ID, "step": _STR}, _MANAGE),
    ("compose.get", "Read a composition", "Read one composition with its steps and change set.", "read", _ID, None),
    ("compose.list", "List compositions", "List the compositions of the org units the person may see.", "read",
     {"org_unit_id": {"t": "string"}}, None),
    ("compose.submit", "Submit a composition", "Send a finished composition to a different person for approval.", "act",
     _ID, _MANAGE),
    ("compose.sendBack", "Send a composition back", "Send a submitted composition back to its maker, with the step and a reason.",
     "act", {**_ID, "step": _STR, "node_id": {"t": "string"}, "reason": _REASON}, _APPROVE),
    ("compose.approve", "Approve a composition", "Approve a submitted composition: changes, mapping and settings apply as one.",
     "commit", _ID, _APPROVE),
)  # fmt: skip
for _a in _DECLARED:
    ACTIONS.setdefault(
        _a[0], ActionDef(id=_a[0], title=_a[1], desc=_a[2], risk=_a[3], perm=_a[5], scope="none", input=_a[4], verb=_a[1].lower())
    )


# ---------------------------------------------------------------- helpers
def _row(i: dict[str, Any], ctx: CallContext, for_update: bool = False) -> dict[str, Any]:
    row = repo.get(ctx.session, int(i["id"]), for_update=for_update)
    if row is None:
        raise ActionError("not_found", f"No composition {i['id']}.")
    return row


def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    """The refusal for an unknown composition or one of an org the person cannot see."""
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No composition {i['id']}."
    return None if _org_ok(ctx, row["org_unit_id"]) else _boundary(row["org_unit_id"])


def _pack(row: dict[str, Any], ctx: CallContext) -> Pack:
    return active_pack(ctx.session, row["pack_key"], row["org_unit_id"])


def _ops(row: dict[str, Any]) -> list[Any]:
    return parse_ops(row["change_set"].get("ops") or [])


def _save(ctx: CallContext, cid: int, **cols: Any) -> None:
    json_cols = {"change_set", "steps", "reading"}
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k in json_cols else f"{k} = :{k}" for k in cols)
    vals = {k: json.dumps(v) if k in json_cols else v for k, v in cols.items()}
    sql = f"UPDATE composition SET {sets}, updated_at = :now WHERE id = :id"  # noqa: S608 - column names are this module's; values bound
    ctx.session.execute(text(sql), {**vals, "id": cid, "now": ctx.now})


def _editors(row: dict[str, Any], ctx: CallContext) -> list[str]:
    return sorted({*row["editors"], ctx.actor.id})


def _version(ctx: CallContext, row: dict[str, Any], status: str, **cols: Any) -> int:
    """Move the composition to `status` as a new version with its snapshot (the row's columns changed by `cols` first)."""
    new = {**row, **cols, "status": status}
    ver = row["version"] + 1
    _save(ctx, row["id"], status=status, version=ver, **cols)
    repo.add_version(ctx.session, row["id"], ver, json.dumps(core.snapshot(new)), status, ctx.actor.id, ctx.now)
    return ver


def _may_read(ctx: CallContext) -> bool:
    acct = ctx.actor.account
    return acct is not None and (policy.can(acct, _MANAGE, ctx.actor.ctx) or policy.can(acct, _APPROVE, ctx.actor.ctx))


def _out(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _wanted(row: dict[str, Any], want: tuple[str, ...], msg: str) -> tuple[str, str] | None:
    return None if row["status"] in want else ("conflict", msg)


def _failed(e: ChangeSetError) -> ActionError:
    return ActionError("validation_error", e.message, {"op_id": e.op_id} if e.op_id else None)


# ---------------------------------------------------------------- start, answer
def _draft(text_: str, org: str, packs: list[Pack], answer: str | None, ctx: CallContext) -> ChangeSet:
    try:
        return draft_change_set(text_, org, packs=packs, answer=answer, drafter=pack_author.make_drafter(ctx))
    except ChangeSetError as e:
        raise _failed(e) from e


@guard("compose.start")
def start_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if len(i["text"]) > MAX_TEXT:
        return "validation_error", f"The description is {len(i['text']):,} characters: keep it under {MAX_TEXT:,}."
    if i.get("pack_key") and i["pack_key"] not in pack_keys():
        return "not_found", f"No pack {i['pack_key']}."
    if i["org_unit_id"] not in units(ctx.session):
        return "not_found", f"No org unit {i['org_unit_id']}."
    return None if _org_ok(ctx, i["org_unit_id"]) else _boundary(i["org_unit_id"])


@implement("compose.start")
def start(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    org = i["org_unit_id"]
    keys = [i["pack_key"]] if i.get("pack_key") else pack_keys()
    packs = [active_pack(ctx.session, k, org) for k in keys]
    cs = _draft(i["text"], org, packs, None, ctx)
    reading = read_text(i["text"], packs).model_copy(update={"by_model": cs.by_model})
    cid = ctx.session.execute(
        text(
            "INSERT INTO composition (org_unit_id, pack_key, base_version, text, reading, change_set, steps, status, created_by, "
            "editors, created_at, updated_at) VALUES (:o, :p, :v, :t, CAST(:r AS jsonb), CAST(:c AS jsonb), CAST(:s AS jsonb), "
            "'draft', :by, :ed, :at, :at) RETURNING id"
        ),
        {
            "o": org, "p": cs.pack, "v": cs.base_version, "t": i["text"], "r": reading.model_dump_json(),
            "c": cs.model_dump_json(), "s": json.dumps(core.new_steps()), "by": ctx.actor.id, "ed": [ctx.actor.id], "at": ctx.now,
        },
    ).scalar_one()  # fmt: skip
    return _out(_row({"id": cid}, ctx)) | {"log": f"Started a composition for {cs.pack} at {org}"}


def _editable_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    return _wanted(_row(i, ctx), _EDITABLE, "A composition that was submitted or approved cannot be changed.")


guard("compose.answer")(_editable_guard)


@implement("compose.answer")
def answer(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    cs = _draft(row["text"], row["org_unit_id"], [_pack(row, ctx)], i["answer"], ctx)
    _save(ctx, row["id"], change_set=cs.model_dump(mode="json"), editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Answered the question of composition {row['id']}"}


# ---------------------------------------------------------------- edit, mark
@guard("compose.editChangeSet")
def edit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    try:
        apply_overlay(_pack(_row(i, ctx), ctx), parse_ops(i["ops"]))
    except ValidationError as e:
        first = e.errors()[0]
        return "validation_error", f"The operations are not valid ({'.'.join(str(p) for p in first['loc'])}): {first['msg']}."
    except ValueError as e:
        if isinstance(e, OverlayError):
            return "validation_error", e.message, {"op_id": e.op_id, "overlay_code": e.code}
        return "validation_error", f"The operations are not valid: {e}."
    return None


@implement("compose.editChangeSet")
def edit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    ops = parse_ops(i["ops"])
    kept = {o.id for o in ops}
    cs = {**row["change_set"], "ops": ops_json(ops), "assumed": [a for a in row["change_set"].get("assumed", []) if a in kept]}
    _save(ctx, row["id"], change_set=cs, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Changed the operations of composition {row['id']}"}


@guard("compose.markStep")
def mark_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    return (
        None
        if i["step"] in core.MAKER_STEPS
        else ("validation_error", f"A step to mark is one of {', '.join(core.MAKER_STEPS)}.")
    )


@implement("compose.markStep")
def mark_step(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    steps = {**row["steps"], i["step"]: {**row["steps"].get(i["step"], {}), "state": "done"}}
    steps[i["step"]].pop("note", None)
    _save(ctx, row["id"], steps=steps, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Marked step {i['step']} of composition {row['id']} done"}


# ---------------------------------------------------------------- reads
@guard("compose.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_read(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read compositions."
    return _reach(i, ctx)


@implement("compose.get")
def get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    return _row(i, ctx)


@guard("compose.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_read(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read compositions."
    org = i.get("org_unit_id")
    if org and org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if not org or _org_ok(ctx, org) else _boundary(org)


@implement("compose.list")
def list_compositions(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    org = i.get("org_unit_id")
    reach = [org] if org else [u for u in units(ctx.session) if _org_ok(ctx, u)]
    return {"compositions": repo.listing(ctx.session, reach)}


# ---------------------------------------------------------------- submit
@guard("compose.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    row = _row(i, ctx)
    left = core.blocking(row["steps"], _ops(row), _pack(row, ctx))
    return ("conflict", "Not ready to submit: " + " ".join(left), {"blocking": left}) if left else None


@implement("compose.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    ver = _version(ctx, row, "submitted", submitted_by=ctx.actor.id)
    return {"id": row["id"], "status": "submitted", "version": ver, "log": f"Submitted composition {row['id']} for approval"}


# ---------------------------------------------------------------- send back
@guard("compose.sendBack")
def send_back_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    if bad := _wanted(_row(i, ctx), ("submitted",), "The composition is not waiting for approval."):
        return bad
    return (
        None
        if i["step"] in core.MAKER_STEPS
        else ("validation_error", f"A step to send back is one of {', '.join(core.MAKER_STEPS)}.")
    )


@implement("compose.sendBack")
def send_back(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    if row["status"] != "submitted":  # sent back or approved by someone else between the guard and this lock
        raise ActionError("conflict", "The composition is not waiting for approval.")
    note: dict[str, Any] = {"reason": i["reason"].strip(), "by": ctx.actor.id, "at": ctx.now.isoformat()}
    if i.get("node_id"):
        note["node_id"] = i["node_id"]
    steps = {**row["steps"], i["step"]: {**row["steps"].get(i["step"], {}), "state": "sent_back", "note": note}}
    ver = _version(ctx, row, "sent_back", steps=steps)
    return {
        "id": row["id"],
        "status": "sent_back",
        "version": ver,
        "log": f"Sent composition {row['id']} back at step {i['step']}",
    }


# ---------------------------------------------------------------- approve
@guard("compose.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _reach(i, ctx):
        return bad
    row = _row(i, ctx)
    if bad := _wanted(row, ("submitted",), "The composition is not waiting for approval."):
        return bad
    if ctx.actor.id in {row["created_by"], row["submitted_by"], *row["editors"]}:
        return "conflict", MAKER_CHECKER
    left = core.blocking(row["steps"], _ops(row), _pack(row, ctx))
    return ("conflict", "Not ready to approve: " + " ".join(left), {"blocking": left}) if left else None


def _apply_overlay(row: dict[str, Any], ctx: CallContext) -> None:
    ops = [o.model_copy(update={"by": o.by or row["created_by"]}) for o in _ops(row)]
    if not ops:
        return
    ref = {"pack_key": row["pack_key"], "org_unit_id": row["org_unit_id"]}
    cur = overlay_repo.get(ctx.session, row["pack_key"], row["org_unit_id"], for_update=True)
    if cur is not None and cur.status == "review":
        raise ActionError("conflict", "A customer overlay for this pack is waiting for approval: decide it first.")
    overlays.save({**ref, "ops": ops_json(ops)}, ctx)
    ctx.session.execute(  # the composition's maker is the overlay's maker; this actor is its checker
        text("UPDATE customer_overlay SET status = 'review', maker = :m WHERE pack_key = :p AND org_unit_id = :o"),
        {"m": row["created_by"], "p": row["pack_key"], "o": row["org_unit_id"]},
    )
    overlays.approve(ref, ctx)


def _current_maps(ctx: CallContext, source_id: str) -> list[list[str]]:
    stored = ctx.session.execute(
        text("SELECT rows FROM field_mapping WHERE source_id = :s ORDER BY version DESC LIMIT 1"), {"s": source_id}
    ).scalar_one_or_none()
    return [list(r["show"]) for r in stored if r.get("show")] if stored else [list(m) for m in mapping.starting_maps(source_id)]


def _apply_mapping(row: dict[str, Any], ctx: CallContext) -> int:
    accepted: dict[str, list[list[str]]] = {}
    for f in (row["steps"].get("mapping") or {}).get("fields") or []:
        if f.get("state") == "accepted":
            accepted.setdefault(f["source_id"], []).append([str(x) for x in f["row"]])
    for sid, rows in accepted.items():
        taken = {(r[0], r[2]) for r in rows}
        maps = [m for m in _current_maps(ctx, sid) if (str(m[0]), str(m[2])) not in taken] + rows
        try:
            mapping.save_version(ctx.session, sid, maps, ctx.actor.id, f"Composition {row['id']} approved", ctx.now)
        except ValueError as e:
            raise ActionError("validation_error", f"The mapping for {sid} cannot be saved: {e}") from e
    return len(accepted)


@implement("compose.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    if row["status"] != "submitted":  # sent back or approved by someone else between the guard and this lock
        raise ActionError("conflict", "The composition is not waiting for approval.")
    _apply_overlay(row, ctx)
    sources = _apply_mapping(row, ctx)
    steps = {**row["steps"], "approve": {"state": "done"}}
    ver = _version(ctx, row, "approved", steps=steps, approved_by=ctx.actor.id)
    return {
        "id": row["id"], "status": "approved", "version": ver, "mapping_sources": sources,
        "log": f"Approved composition {row['id']} (v{ver}): changes, mapping and stage settings apply together",
    }  # fmt: skip
