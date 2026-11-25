"""Pack version actions (plan 9, P9-1.6; registry entry I-1; stories X-01 and X-03). A pack is a versioned document
(di.services.modeler.pack); a new version is an approvable object with its own maker-checker, as a flow and a customer
overlay are.

    pack.import   act     {doc, org_unit_id?, note?}   the document as a draft (checked as `parse_pack` checks it, a version
                                                       newer than every stored and file version of its key), with the
                                                       impact on the open cases and the sample queue; agents may import
    pack.submit   act     {id}                         draft -> review
    pack.approve  commit  {id}                         review -> pub: the previous published version of the key and org is
                                                       retired; the customer overlays on an older version are rebased as
                                                       drafts (not by anyone who made or submitted this version: journal)
    pack.reject   commit  {id, reason}                 review -> draft, the reason kept as the note

Approve and reject are in `FORBIDDEN_ACTIONS`: no agent runs them, however the call arrives. `managePacks` (Admin, Planner)
imports and submits, `approve.packs` (Admin, Approver) approves and returns. A pack for every org (no `org_unit_id`) is
imported by Admin only; an org's pack is checked against the person's units as the flow actions check them. A published
version takes effect from the next decision: `repositories.packs.active_pack` reads it; cases already decided are not.

The overlay rebase of an approval is `di.services.modeler.overlay.rebase` per overlay of the key in scope, saved as the
overlay's draft with its `conflicts` and `notes`; a locked gate the version adds is noted on each rebased overlay
("<gate name> added by the pack") and applies to every org at once.
"""

import json
from typing import Any

from sqlalchemy import text

from di.core import orgs
from di.repositories import packs as repo
from di.repositories.orgs import units
from di.repositories.overlays import OverlayRow
from di.repositories.packs import PackRow
from di.services.actions.modeler import MAKER_CHECKER, _boundary, _org_ok
from di.services.actions.pack_impact import impact
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.gates import catalogue
from di.services.modeler.overlay import ops_json, parse_ops, rebase
from di.services.modeler.pack import Pack, PackError, parse_pack

_MANAGE, _APPROVE = "managePacks", "approve.packs"
_ID = {"id": {"req": True, "t": "number"}}


def _declare(action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("pack.import", "Import a pack version", "import packs",
         "Import a pack document as a draft version, checked part by part, with the impact it would have.", "act",
         {"doc": {"req": True, "t": "object"}, "org_unit_id": {"t": "string"}, "note": {"t": "string"}}, _MANAGE)  # fmt: skip
_declare("pack.submit", "Submit a pack version", "submit packs",
         "Send a draft pack version to a different person for approval.", "act", _ID, _MANAGE)  # fmt: skip
_declare("pack.approve", "Approve a pack version", "approve packs",
         "Approve a submitted pack version; it decides the org's cases from then on.", "commit", _ID, _APPROVE)  # fmt: skip
_declare("pack.reject", "Return a pack version to draft", "return packs",
         "Return a submitted pack version to its maker with a reason.", "commit",
         {**_ID, "reason": {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}},
         _APPROVE)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _row(i: dict[str, Any], ctx: CallContext, for_update: bool = False) -> PackRow:
    row = repo.get(ctx.session, int(i["id"]), for_update=for_update)
    if row is None:
        raise ActionError("not_found", f"No pack version {i['id']}.")
    return row


def _label(row: PackRow) -> str:
    return f"{row.key} {row.version}" + (f" for {row.org_unit_id}" if row.org_unit_id else "")


def _reach(row: PackRow, ctx: CallContext) -> tuple[str, str] | None:
    """The tenant refusal for a pack of an org the person may not see."""
    return _boundary(row.org_unit_id) if row.org_unit_id and not _org_ok(ctx, row.org_unit_id) else None


def _waiting(row: PackRow) -> tuple[str, str] | None:
    return None if row.status == "review" else ("conflict", f"The pack {_label(row)} is not waiting for approval.")


def _agent_refusal(ctx: CallContext) -> tuple[str, str] | None:
    return ("approval_required", "A pack version is approved or returned only by a person.") if ctx.preparer else None


def makers(ctx: CallContext, row: PackRow) -> set[str]:
    """Everyone who made or submitted this version: its recorded maker and the journaled submits."""
    rows = ctx.session.execute(
        text("SELECT actor FROM action_journal WHERE NOT undone AND action = 'pack.submit' AND input->>'id' = :i"),
        {"i": str(row.id)},
    )
    return set(rows.scalars()) | ({row.maker} if row.maker else set())


def _set(ctx: CallContext, row: PackRow, **cols: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    sql = f"UPDATE pack_version SET {sets} WHERE id = :id"  # noqa: S608 - column names are this module's; values are bound
    ctx.session.execute(text(sql), {**cols, "id": row.id})


# ---------------------------------------------------------------- import
@guard("pack.import")
def import_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    org = i.get("org_unit_id")
    if org:
        if org not in units(ctx.session):
            return "not_found", f"No org unit {org}."
        if not _org_ok(ctx, org):
            return _boundary(org)
    elif ctx.actor.role != "Admin":
        return "out_of_scope", "Only Admin imports a pack for every org."
    try:
        pack = parse_pack(i["doc"])
    except PackError as e:
        return "validation_error", str(e), {"part": e.part, "part_name": e.part_name}
    newest = repo.newest_version(ctx.session, pack.key)
    if newest is not None and repo.semver(pack.version) <= repo.semver(newest):
        return "conflict", f"Pack {pack.key} {pack.version} is not newer than {newest}."
    return None


@implement("pack.import")
def import_pack(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    pack = parse_pack(i["doc"])
    org = i.get("org_unit_id") or None
    try:
        current: Pack | None = repo.active_pack(ctx.session, pack.key, org)
    except KeyError:
        current = None  # a new pack key: nothing is decided under it yet
    effect = impact(ctx.session, current, pack, org) if current else {"changed": 0, "total": 0, "dv": 0}
    new_id = ctx.session.execute(
        text(
            "INSERT INTO pack_version (key, version, org_unit_id, doc, status, maker, note, impact, created_at) "
            "VALUES (:k, :v, :o, CAST(:d AS jsonb), 'draft', :by, :n, CAST(:x AS jsonb), :now) RETURNING id"
        ),
        {"k": pack.key, "v": pack.version, "o": org, "d": json.dumps(i["doc"]), "by": ctx.actor.id,
         "n": i.get("note") or None, "x": json.dumps(effect), "now": ctx.now},
    ).scalar_one()  # fmt: skip
    return {
        "id": new_id, "status": "draft", "key": pack.key, "version": pack.version, "impact": effect,
        "log": f"Imported pack {pack.key} {pack.version} as a draft",
    }  # fmt: skip


# ---------------------------------------------------------------- submit, approve, reject
@guard("pack.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No pack version {i['id']}."
    if bad := _reach(row, ctx):
        return bad
    return None if row.status == "draft" else ("conflict", f"The pack {_label(row)} has no draft to submit.")


@implement("pack.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    _set(ctx, row, status="review")
    return {"status": "review", "log": f"Submitted pack {_label(row)} for approval"}


@guard("pack.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No pack version {i['id']}."
    if bad := _reach(row, ctx) or _agent_refusal(ctx) or _waiting(row):
        return bad
    return ("conflict", MAKER_CHECKER) if ctx.actor.id in makers(ctx, row) else None


def _new_locked_gates(old: Pack | None, new: Pack) -> list[str]:
    """The names of the locked gates `new` activates that `old` did not."""
    was = {g.id for g in old.gates if g.active} if old else set()
    cat = catalogue()
    return [cat[g.id].name for g in new.gates if g.active and g.id not in was and g.id in cat and cat[g.id].locked]


def _rebase_overlay(ctx: CallContext, row: OverlayRow, new: Pack, gates: list[str]) -> None:
    """The overlay's draft (else published) operations moved onto `new` as the overlay's draft."""
    raw, base = (
        (row.draft, row.draft_base_version or row.base_version) if row.draft is not None else (row.published, row.base_version)
    )
    old = repo.pack_at(ctx.session, new.key, base) or new.model_copy(update={"version": base})
    res = rebase(old, new, parse_ops(raw))
    notes = [*res.notes, *(f"{g} added by the pack" for g in gates)]
    ctx.session.execute(
        text(
            "UPDATE customer_overlay SET status = 'draft', checker = NULL, draft = CAST(:d AS jsonb), draft_base_version = :v, "
            "conflicts = CAST(:c AS jsonb), notes = CAST(:n AS jsonb), updated_at = :now WHERE id = :id"
        ),
        {"d": json.dumps(ops_json(res.ops)), "v": new.version, "n": json.dumps(notes), "now": ctx.now, "id": row.id,
         "c": json.dumps([c.model_dump(mode="json") for c in res.conflicts])},
    )  # fmt: skip


def _rebase_overlays(ctx: CallContext, row: PackRow, old: Pack | None) -> int:
    """Every customer overlay of the key in the pack's scope that was made on another version is rebased onto the pack in
    force for its org; returns how many."""
    tree = units(ctx.session)
    n = 0
    for ov in repo.overlays_of(ctx.session, row.key):
        if row.org_unit_id is not None and row.org_unit_id not in orgs.ancestors(tree, ov.org_unit_id):
            continue
        now = repo.active_pack(ctx.session, row.key, ov.org_unit_id)
        if (ov.draft_base_version or ov.base_version) == now.version or not (ov.draft or ov.published):
            continue
        _rebase_overlay(ctx, ov, now, _new_locked_gates(old, now))
        n += 1
    return n


@implement("pack.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    try:
        old: Pack | None = repo.active_pack(ctx.session, row.key, row.org_unit_id)
    except KeyError:
        old = None
    ctx.session.execute(
        text(
            "UPDATE pack_version SET status = 'retired' WHERE key = :k AND status = 'pub' "
            "AND coalesce(org_unit_id, '') = coalesce(:o, '') AND id <> :id"
        ),
        {"k": row.key, "o": row.org_unit_id, "id": row.id},
    )
    _set(ctx, row, status="pub", checker=ctx.actor.id, published_at=ctx.now)
    rebased = _rebase_overlays(ctx, row, old)
    return {"status": "pub", "rebased": rebased, "log": f"Approved pack {_label(row)}; it applies from the next decision"}


@guard("pack.reject")
def reject_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No pack version {i['id']}."
    return _reach(row, ctx) or _agent_refusal(ctx) or _waiting(row)


@implement("pack.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    _set(ctx, row, status="draft", note=f"Returned by {ctx.actor.id}: {i['reason'].strip()}")
    return {"status": "draft", "reason": i["reason"], "log": f"Returned pack {_label(row)} to draft"}
