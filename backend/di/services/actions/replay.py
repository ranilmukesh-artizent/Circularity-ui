"""Replay actions (plan 9, P9-7.1; registry entry I-16; story X-06): importing a batch of past decisions.

    replay.import   act   {pack, org_unit_id, csv, batch_id?}   check the CSV row by row (pandera, di.services.replay.history),
                                                                store the good rows and the held ones with their reasons;
                                                                answers the Batch. `batch_id` appends to a batch of the same
                                                                pack and org unit.
    replay.batches  read  {pack, org_unit_id}                   the org's batches with counts, period and the first 50 held rows

`runReplay` (Admin, Planner, Executive) is the permission of both; the Executive role only reads, so `replay.import` refuses it
("The Executive view reads replay reports; a Planner or Admin runs them."). An agent a planner prepared may import (it
changes no decision). The org boundary is the one `flow.*` uses. A header that looks personal, a missing column or more than
25,000 rows refuses the whole import and stores nothing.
"""

from typing import Any

from di.repositories import replay as repo
from di.repositories.orgs import units
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.pack import Pack, load_pack, pack_keys
from di.services.replay import history

_PERM = "runReplay"
EXECUTIVE = "The Executive view reads replay reports; a Planner or Admin runs them."


def _declare(action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]]) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=_PERM, scope="none", input=inp, verb=verb),
    )


_BASE = {"pack": {"req": True, "t": "string"}, "org_unit_id": {"req": True, "t": "string"}}
_declare("replay.import", "Import a history batch", "import history",
         "Check a CSV of past decisions against a pack and store it: good rows are kept, bad rows are held with a reason.",
         "act", {**_BASE, "csv": {"req": True, "t": "string"}, "batch_id": {"t": "number"}})  # fmt: skip
_declare("replay.batches", "List history batches", "see history batches",
         "The history batches of a pack and org unit, with counts, the decision period and the first 50 held rows.",
         "read", _BASE)  # fmt: skip


def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | Pack:
    """The pack, or the refusal: unknown pack or org unit, or an org unit outside the actor's tenants."""
    org = i["org_unit_id"]
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    if not _org_ok(ctx, org):
        return _boundary(org)
    if i["pack"] not in pack_keys():
        return "not_found", f"No pack {i['pack']}."
    return load_pack(i["pack"])


@guard("replay.import")
def import_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if ctx.actor.role == "Executive":
        return "out_of_scope", EXECUTIVE
    pack = _reach(i, ctx)
    if not isinstance(pack, Pack):
        return pack
    if i.get("batch_id") is not None:
        b = repo.get(ctx.session, int(i["batch_id"]))
        if b is None:
            return "not_found", f"No history batch {i['batch_id']}."
        if (b["pack"], b["org_unit_id"]) != (pack.key, i["org_unit_id"]):
            return "conflict", "A batch is appended to only for its own pack and org unit."
    try:
        rows = history.parse_csv(i["csv"])
        if not rows:
            raise history.HistoryRefused("The file has no rows.")
        if len(rows) > history.MAX_ROWS:
            raise history.HistoryRefused(f"At most {history.MAX_ROWS:,} rows per import.")
        history.check_header({k for r in rows for k in r}, pack)
    except history.HistoryRefused as e:
        return "validation_error", str(e)
    return None


@implement("replay.import")
def import_batch(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    pack = load_pack(i["pack"])
    s = ctx.session
    if i.get("batch_id") is not None:
        bid = int(i["batch_id"])
        repo.get(s, bid, for_update=True)
        seen = repo.item_ids(s, bid)
    else:
        bid, seen = repo.create(s, pack.key, i["org_unit_id"], ctx.actor.id), set()
    try:
        ok, held = history.import_history(history.parse_csv(i["csv"]), pack, now=ctx.now, seen=seen)
    except history.HistoryRefused as e:
        raise ActionError("validation_error", str(e)) from e
    start = repo.last_n(s, bid)
    repo.add_items(s, bid, ok, held=False, start=start)
    repo.add_items(s, bid, held, held=True, start=start)
    batch = repo.refresh(s, bid)
    return {**batch.view(), "log": f"Imported {len(ok) + len(held)} history rows for {pack.key}: {len(held)} held"}


@guard("replay.batches")
def batches_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    r = _reach(i, ctx)
    return None if isinstance(r, Pack) else r


@implement("replay.batches")
def list_batches(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    out = [
        {**b.view(), "held_items": repo.held_items(ctx.session, b.id)}
        for b in repo.for_org(ctx.session, i["pack"], i["org_unit_id"])
    ]
    return {"batches": out}
