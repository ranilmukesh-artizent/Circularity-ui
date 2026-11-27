# ruff: noqa: E501 - long lines in the docstring and the action texts
"""Wholesale lot actions (plan 9, P9-6.11, story DV-07; registry entries I-11 and I-15; the lot is a new approvable object, R21).

    lot.build     act     {org_unit_id}       manageLots: group the org's open wholesale-routed device cases by model and grade into lots
                                              of at most the pack's lot size (GR-D4), and post each lot to the device market (`bidding`)
    lot.propose   act     {lot_id}            manageLots: pick the best approved net bid -> `proposed`, worth net times units. At or under
                                              GR-D10's $25,000 the org's standing policy approves it (journal "approved by policy P vN,
                                              owner X"); above, or with no policy that covers it, it waits for the Approver role (owner
                                              label "Commercial manager")
    lot.approve   commit  {lot_id}            approve.decisions: a person accepts the proposal; each member case is approved on the
                                              wholesale route and its sale plan (reserve, sale, ship, fulfil, receipt) is queued
    lot.reject    act     {lot_id, reason}    approve.decisions: send the proposal back, with a reason
    lot.list      read    {}                  the lots the actor may see, with their bids, the best approved bid and the dropped ones

The best bid is computed (`di.services.modeler.valuers.device_lots.rank_bids`): net a unit, among the buyers of the `approved_buyers`
market table (GR-D12); a bid from a buyer not on it is never chosen and is listed with its reason. No language model picks a bid.
`lot.approve` and `lot.reject` are in `FORBIDDEN_ACTIONS` and `lot.propose` in `HELD_FOR_PERSON` (di.services.agents.forbidden): an
agent never accepts or sells a lot, and its proposal waits for a person. Maker-checker: the person who built or proposed a lot cannot
approve it. Approval is checked against the approver's limit like a decision's. A lot of another tenant is neither seen nor changed.
Needs review by Kinective's Legal team before a customer relies on it.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from di.connectors.http import SourceError
from di.core import clock, policy
from di.repositories import device_lots as repo
from di.repositories import standing_policies
from di.repositories.common import limit_for
from di.repositories.device_lots import LotRow
from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.repositories.standing_policies import PolicyRow
from di.services.actions import decisions
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.actions.standing_policy import _fraud, _guardrail_holds, owner_limit
from di.services.cases import store
from di.services.modeler.valuers import device_lots as lots
from di.services.modeler.valuers.device_lots import Bid, LotCandidate, usd
from di.services.policy_standing import covers, parse_rules

PACK = repo.PACK
_MANAGE, _APPROVE = "manageLots", "approve.decisions"
_STR = {"req": True, "t": "string"}
MAKER_CHECKER = "Maker-checker: you built or proposed this lot, so you cannot approve it."
_ROUTE = "wholesale"


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id, ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb)
    )


_declare("lot.build", "Build wholesale lots", "build wholesale lots",
         "Group the org's open wholesale-routed devices by model and grade into lots within the lot size, and post them for bids.",
         "act", {"org_unit_id": _STR}, _MANAGE)  # fmt: skip
_declare("lot.propose", "Propose a wholesale lot", "propose wholesale lots",
         "Pick the best bid of an approved buyer for a lot, net of fees and logistics. A lot at or under the limit is approved by the "
         "standing policy; a bigger one waits for the Commercial manager.",
         "act", {"lot_id": _STR}, _MANAGE)  # fmt: skip
_declare("lot.approve", "Approve a wholesale lot", "approve wholesale lots",
         "Accept the proposed bid: each member device is sold on the wholesale route at it. Not by the person who built or proposed it.",
         "commit", {"lot_id": _STR}, _APPROVE)  # fmt: skip
_declare("lot.reject", "Reject a wholesale lot", "reject wholesale lots",
         "Send a proposed lot back, with a reason.", "act",
         {"lot_id": _STR, "reason": {"req": True, "t": "string", "min": 10, "minText": "Add a reason of at least 10 characters."}},
         _APPROVE)  # fmt: skip
_declare(
    "lot.list",
    "List wholesale lots",
    "see wholesale lots",
    "The wholesale lots of the orgs you see, with their bids, the best approved bid and the dropped ones.",
    "read",
    {},
    None,
)


# ---------------------------------------------------------------- helpers
def _reach(lot_id: str, ctx: CallContext) -> tuple[str, str] | LotRow:
    """The lot, or the refusal: unknown, or of an org the actor cannot see (the tenant boundary)."""
    lot = repo.get(ctx.session, lot_id)
    if lot is None:
        return "not_found", f"No wholesale lot {lot_id}."
    if lot.org_unit_id and not _org_ok(ctx, lot.org_unit_id):
        return _boundary(lot.org_unit_id)
    return lot


def _today() -> date:
    return clock.now().date()


def _bid_view(b: Bid) -> dict[str, Any]:
    return {
        "bid_id": b.bid_id,
        "buyer_code": b.buyer_code,
        "amount": b.amount,
        "fees": b.fees,
        "logistics": b.logistics,
        "net": b.net,
    }


def _waits(value: float, limit: float) -> dict[str, str]:
    """Who a proposed lot waits for, and why (GR-D10): a person with the Approver role, owner label "Commercial manager"."""
    why = (
        f"A {usd(value)} lot is over the {usd(limit)} limit (GR-D10)"
        if lots.over_limit(value, limit)
        else f"No standing policy covers this {usd(value)} lot"
    )
    return {"role": lots.ROLE, "owner": lots.OWNER, "reason": why}


def _view(ctx: CallContext, lot: LotRow) -> dict[str, Any]:
    """The lot as the list shows it: the bids received, the best approved one (the proposal's own once proposed), the dropped ones."""
    s = ctx.session
    rk = repo.ranking(s, lot, _today())
    best = next((b for b in rk.ranked if b.bid_id == lot.best_bid_id), None) or rk.best
    waits = None
    if lot.status == "proposed" and lot.value_usd is not None:
        waits = _waits(lot.value_usd, lots.value_limit(active_pack(s, PACK, lot.org_unit_id)))
    return {
        "id": lot.id, "lot_ref": lot.lot_ref, "org_unit_id": lot.org_unit_id, "model": lot.model, "grade": lot.grade,
        "units": lot.units, "status": lot.status, "case_ids": repo.members(s, lot.id),
        "bids_received": len(rk.ranked) + len(rk.dropped), "best_bid": _bid_view(best) if best else None,
        "dropped": [{"bid_id": d.bid_id, "buyer_code": d.buyer_code, "reason": d.reason} for d in rk.dropped],
        "value_usd": lot.value_usd, "created_by": lot.created_by, "proposed_by": lot.proposed_by,
        "approved_by": lot.approved_by, "reason": lot.reason, "waits_for": waits,
    }  # fmt: skip


def _candidates(ctx: CallContext, org: str) -> list[LotCandidate]:
    """The org's received devices whose case awaits approval with the wholesale route recommended and that are in no lot."""
    taken = repo.cases_in_lots(ctx.session)
    out: list[LotCandidate] = []
    for c in store.all_cases(ctx.session):
        v, rec = c.get("valuer") or {}, c.get("recommendation")
        if c["owner"] != org or c["id"] in taken or not v.get("imei") or c["stage"] != "awaiting_approval":
            continue
        if not rec or rec.get("id") != _ROUTE or rec.get("excluded") or c.get("approval") or c.get("blocked"):
            continue
        got = v.get("received")
        out.append(
            LotCandidate(
                c["id"],
                str(v["model"]),
                str(v["grade"]),
                datetime.fromisoformat(str(got)) if got else clock.now(),
                int(v.get("qty") or 1),
            )
        )
    return out


def _next_id(ctx: CallContext) -> tuple[str, str]:
    """(lot id, a local lot ref) for the next lot: L-00001 and LOT-D-0001. The market gives its own ref once it takes the lot."""
    s = ctx.session
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext('device_lot.next'))"))
    n = s.execute(
        text("SELECT coalesce(max(substring(id from 3)::int), 0) + 1 FROM device_lot WHERE id ~ '^L-[0-9]+$'")
    ).scalar_one()
    return f"L-{n:05d}", f"LOT-D-{n:04d}"


def _post(ctx: CallContext, lot: LotRow) -> str | None:
    """Post the lot to the device market (`dvmkt`, POST /lots) and return the ref it gave it; None when the market did not take it.
    With sending off (the suite, a pilot org) the lot is taken as it stands, as every instruction is acknowledged by the simulated adapter."""
    from di.services.instructions import queue, writers  # lazy: the writers import the case store

    if not queue.enabled():
        return lot.lot_ref
    cl = writers.client(ctx.session, "dvmkt")
    try:
        doc = cl.request(
            "POST",
            "/lots",
            json={"model": lot.model, "grade": lot.grade, "units": lot.units, "currency": "USD", "status": "open"},
        ).json()
    except SourceError:
        return None
    finally:
        cl.close()
    return str(doc.get("lotRef") or lot.lot_ref) if isinstance(doc, dict) else lot.lot_ref


def _bid_of(ctx: CallContext, lot: LotRow) -> Bid | None:
    """The bid the lot was proposed on, while it is still among its approved bids; None when it is gone (never another bid: the
    person accepted that one, phase 6 review F5)."""
    rk = repo.ranking(ctx.session, lot, _today())
    return next((b for b in rk.ranked if b.bid_id == lot.best_bid_id), None)


def _members_problem(ctx: CallContext, lot: LotRow) -> str | None:
    """Why a member case cannot be approved now (gone, not awaiting approval, held for fraud), or None."""
    for cid in repo.members(ctx.session, lot.id):
        c = store.get(ctx.session, cid)
        if c is None:
            return f"Case {cid} of the lot no longer exists."
        if c["stage"] != "awaiting_approval" or c.get("approval"):
            return f"{cid} is not awaiting approval, so the lot cannot be approved."
        if _fraud(c):
            return f"{cid} is held for fraud review: release it first."
        rec = c.get("recommendation")
        if not rec or rec.get("id") != _ROUTE or rec.get("excluded"):
            return (
                f"{cid} is no longer recommended for the wholesale route, so the lot cannot be approved: take it out of the lot."
            )
        if c.get("blocked") or c.get("gateHold"):
            return f"{cid} is blocked or held, so the lot cannot be approved."
        if stale := decisions._stale_tables(ctx, c):
            return stale[1]
    return None


def _decision_guard(i: dict[str, Any], ctx: CallContext, lot: LotRow) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    """The approval policy of `decision.approve` (no self-approval, the approver's limit) for each member on its wholesale route."""
    for cid in repo.members(ctx.session, lot.id):
        c = store.get(ctx.session, cid)
        if c is not None and (rec := c.get("recommendation")) and (g := decisions._ap_policy({"route": rec["plan"]} | i, ctx, c)):
            return g
    return None


def _policy_row(ctx: CallContext, lot: LotRow, value: float) -> PolicyRow | None:
    """The org's active standing policy when it covers this lot (its value limit, the approver's own limit, the wholesale route, no hold
    on a member case, no fraud hold), else None."""
    row = standing_policies.effective(ctx.session, PACK, lot.org_unit_id or "")
    rules = parse_rules(row.rules) if row else None
    if row is None or isinstance(rules, str) or rules is None or _members_problem(ctx, lot):
        return None
    limit = owner_limit(ctx, row.owner)
    held = any(_guardrail_holds(c) for cid in repo.members(ctx.session, lot.id) if (c := store.get(ctx.session, cid)) is not None)
    if limit is None or Decimal(str(value)) > limit or held:
        return None
    ok = covers(
        rules, value=Decimal(str(value)), confidence=1.0, route=_ROUTE, cls="device", market=repo.MARKET,
        holds=[], open_exception=False, conflict=False, fraud_hold=False,
    )  # fmt: skip
    return row if ok else None


def _approve_lot(ctx: CallContext, lot: LotRow, by: str, label: str, bid: Bid) -> None:
    """Mark the lot approved by `by` and approve each member case on the wholesale route (the sale plan follows from the route). `label`
    is who approves, as a case's approval records it."""
    if bad := _members_problem(ctx, lot):  # again under the lock: a member re-valued since the guard
        raise ActionError("conflict", bad)
    ctx.session.execute(text("UPDATE device_lot SET status = 'approved', approved_by = :a WHERE id = :i"), {"a": by, "i": lot.id})
    note = f"Wholesale lot {lot.lot_ref} sold to buyer {bid.buyer_code} at {usd(bid.net)} net a unit"
    for cid in repo.members(ctx.session, lot.id):
        mine = store.get(ctx.session, cid)
        route = mine["recommendation"]["plan"] if mine is not None and mine.get("recommendation") else None  # checked above
        decisions._approve(
            "decision.approve", {"case_id": cid, "rationale": note, "spend": 0, "route": route}, ctx, approver=label
        )
        c = store.get(ctx.session, cid, for_update=True)
        if c is not None:
            c["lotSale"] = {
                "lot_id": lot.id,
                "lot_ref": lot.lot_ref,
                "buyer": bid.buyer_code,
                "bid_id": bid.bid_id,
                "net_per_unit": bid.net,
            }
            store.save(ctx.session, c)


# ---------------------------------------------------------------- list
@guard("lot.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001 - guards take (input, ctx)
    if not (policy.can(ctx.actor.account, _MANAGE, ctx.actor.ctx) or policy.can(ctx.actor.account, _APPROVE, ctx.actor.ctx)):
        return "out_of_scope", f"The {ctx.actor.role} view cannot see wholesale lots."
    return None


@implement("lot.list")
def list_lots(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - handlers take (input, ctx)
    visible = [u for u in units(ctx.session) if _org_ok(ctx, u)]
    return {
        "lots": [_view(ctx, r) for r in repo.listed(ctx.session, visible)],
        "me": ctx.actor.id,
        "can": {
            "build": policy.can(ctx.actor.account, _MANAGE, ctx.actor.ctx),
            "approve": policy.can(ctx.actor.account, _APPROVE, ctx.actor.ctx),
        },
    }


# ---------------------------------------------------------------- build
@guard("lot.build")
def build_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    org = str(i["org_unit_id"])
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if _org_ok(ctx, org) else _boundary(org)


@implement("lot.build")
def build(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    org = str(i["org_unit_id"])
    # the lock before the candidates are read: two builds never see the same open case (phase 6 review F2)
    ctx.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('device_lot.build'))"))
    cap = lots.lot_cap(active_pack(ctx.session, PACK, org))
    made: list[LotRow] = list(repo.drafts(ctx.session, org))  # built earlier, not taken by the market yet
    for d in lots.build_lots(_candidates(ctx, org), cap):
        lot_id, ref = _next_id(ctx)
        ctx.session.execute(
            text(
                "INSERT INTO device_lot (id, org_unit_id, lot_ref, model, grade, units, status, created_by) "
                "VALUES (:i, :o, :r, :m, :g, :u, 'draft', :by)"
            ),
            {"i": lot_id, "o": org, "r": ref, "m": d.model, "g": d.grade, "u": d.units, "by": ctx.actor.id},
        )
        for cid in d.case_ids:
            ctx.session.execute(text("INSERT INTO device_lot_member (lot_id, case_id) VALUES (:l, :c)"), {"l": lot_id, "c": cid})
        row = repo.get(ctx.session, lot_id)
        if row is not None:
            made.append(row)
    for lot in made:
        posted = _post(ctx, lot)
        if posted is not None:
            ctx.session.execute(
                text("UPDATE device_lot SET status = 'bidding', lot_ref = :r WHERE id = :i"), {"r": posted, "i": lot.id}
            )
    views = [_view(ctx, r) for lot in made if (r := repo.get(ctx.session, lot.id)) is not None]
    return {"lots": views, "log": f"Built {len(views)} wholesale lot{'' if len(views) == 1 else 's'} for {org}"}


# ---------------------------------------------------------------- propose
@guard("lot.propose")
def propose_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    lot = _reach(str(i["lot_id"]), ctx)
    if isinstance(lot, tuple):
        return lot
    if lot.status != "bidding":
        return "conflict", f"{lot.lot_ref} is {lot.status}: only a lot that is collecting bids is proposed."
    rk = repo.ranking(ctx.session, lot, _today())
    if rk.best is None:
        why = "; ".join(d.reason for d in rk.dropped)
        return "conflict", f"{lot.lot_ref} has no bid from an approved buyer yet" + (f" ({why})" if why else "") + "."
    return None


@implement("lot.propose")
def propose(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    lot = repo.get(ctx.session, str(i["lot_id"]), for_update=True)
    if lot is None or lot.status != "bidding":  # proposed by someone else between the guard and this lock
        raise ActionError("conflict", f"Lot {i['lot_id']} is no longer collecting bids.")
    rk = repo.ranking(ctx.session, lot, _today())
    best = rk.best
    if best is None:  # not reached: the guard found one
        raise ActionError("conflict", f"{lot.lot_ref} has no bid from an approved buyer yet.")
    value = lots.lot_value(best.net, lot.units)
    limit = lots.value_limit(active_pack(ctx.session, PACK, lot.org_unit_id))
    ctx.session.execute(
        text("UPDATE device_lot SET status = 'proposed', best_bid_id = :b, value_usd = :v, proposed_by = :a WHERE id = :i"),
        {"b": best.bid_id, "v": value, "a": ctx.actor.id, "i": lot.id},
    )
    proposed = repo.get(ctx.session, lot.id)
    row = None if lots.over_limit(value, limit) or proposed is None else _policy_row(ctx, proposed, value)
    sold = f"{lot.units} units to buyer {best.buyer_code} at {usd(best.net)} net a unit, {usd(value)}"
    out: dict[str, Any] = {
        "id": lot.id, "lot_id": lot.id, "status": "proposed", "value_usd": value, "best_bid": _bid_view(best),
        "dropped": [{"bid_id": d.bid_id, "buyer_code": d.buyer_code, "reason": d.reason} for d in rk.dropped],
        "approved_by_policy": row is not None, "waits_for": None if row else _waits(value, limit),
    }  # fmt: skip
    if row is None or proposed is None:
        return out | {"log": f"Proposed lot {lot.lot_ref}: {sold}; waits for the Commercial manager"}
    _approve_lot(ctx, proposed, f"policy {row.id} v{row.ver}", f"policy {row.id} v{row.ver}", best)
    return out | {
        "status": "approved", "policy_id": row.id, "ver": row.ver, "owner": row.owner,
        "log": f"Proposed lot {lot.lot_ref}: {sold}; approved by policy {row.id} v{row.ver}, owner {row.owner}",
    }  # fmt: skip


# ---------------------------------------------------------------- approve, reject
def _decidable(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | LotRow:
    lot = _reach(str(i["lot_id"]), ctx)
    if isinstance(lot, tuple):
        return lot
    if lot.status != "proposed":
        return "conflict", f"{lot.lot_ref} is {lot.status}: only a proposed lot is decided."
    return lot


@guard("lot.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    lot = _decidable(i, ctx)
    if isinstance(lot, tuple):
        return lot
    if ctx.actor.id in (lot.created_by, lot.proposed_by):
        return "conflict", MAKER_CHECKER
    bid = _bid_of(ctx, lot)
    if bid is None:
        return "conflict", f"The bid {lot.lot_ref} was proposed on is no longer available: propose the lot again."
    value, lim = (
        lots.lot_value(bid.net, lot.units),
        limit_for(ctx.actor.account, ctx.actor.ctx),
    )  # the sale value, not a stale one
    if value > lim:
        return (
            "limit_exceeded",
            f"{lot.lot_ref} is worth {usd(value)}, above your approval limit of {usd(lim)}. It escalates to Admin.",
            {"escalate": "admin"},
        )
    if bad := _members_problem(ctx, lot):
        return "conflict", bad
    return _decision_guard(i, ctx, lot)


@implement("lot.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    lot = repo.get(ctx.session, str(i["lot_id"]), for_update=True)
    bid = _bid_of(ctx, lot) if lot is not None else None
    if lot is None or lot.status != "proposed" or bid is None:  # decided by someone else between the guard and this lock
        raise ActionError("conflict", f"Lot {i['lot_id']} is not waiting for approval.")
    _approve_lot(ctx, lot, ctx.actor.id, decisions._by(ctx), bid)
    return {
        "id": lot.id, "lot_id": lot.id, "status": "approved", "value_usd": lot.value_usd, "best_bid": _bid_view(bid),
        "cases": repo.members(ctx.session, lot.id),
        "log": f"Approved lot {lot.lot_ref}: sold to buyer {bid.buyer_code} at {usd(bid.net)} net a unit, {usd(lot.value_usd or 0)}",
    }  # fmt: skip


@guard("lot.reject")
def reject_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    lot = _decidable(i, ctx)
    return lot if isinstance(lot, tuple) else None


@implement("lot.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    done = ctx.session.execute(
        text("UPDATE device_lot SET status = 'rejected', reason = :r WHERE id = :i AND status = 'proposed' RETURNING lot_ref"),
        {"r": i["reason"].strip(), "i": i["lot_id"]},
    ).first()
    if done is None:  # decided by someone else between the guard and this write
        raise ActionError("conflict", f"Lot {i['lot_id']} is not waiting for a decision.")
    return {"id": i["lot_id"], "lot_id": i["lot_id"], "status": "rejected", "reason": i["reason"].strip(),
            "log": f"Returned lot {done[0]} to its builder"}  # fmt: skip
