"""The close of a used car: sold against the forecast, then the residual gain or loss and the lessee's charges (plan 9, P9-9.20;
story UC-23; reads registry entries I-7 (the outcome and reconcile stages) and I-10 (the hold policy); X-13 reuses it).

    close_case(s, case_id, ctx=None) -> CloseResult   what the sale of the car says, and what the close prepares for Finance
    usedCar.close  {case_id}                          the action an agent (the reconcile stage) or a person calls: `close_case`
    usedCar.post   {case_id, kind, amount, label}     one amount of the close, posted: the held proposal's action (below)

On a sale fact (the dealer system's `dms.listing.sold` or the auction platform's `auction.consignment.sold`, read by their
adapters as `outcome.sale_price`, `outcome.sold_at`, `outcome.days_to_sale` of the car) `close_case` keeps, on the case as
`close.sale`, the sale price and the days to sale against the decision's forecast: the route's forecast net, its sale line
and its days to sale (the route's `dest.days`), the realised net (the forecast net with the sale line at the price the car
fetched and a holding cost line at the days it took; every other cost line stays the forecast until Finance confirms the
real ones) and the errors, realised less forecast. It writes no `outcome`: confirming an outcome is a person's
(`outcome.confirm`, FORBIDDEN_ACTIONS), and calibration (`di.services.engine.calibration`) learns only from confirmed
outcomes, so this record is what the reconcile stage and Finance read.

For a lease return (`asset.return_kind` `lease_end`, `asset.book_value` the residual) it also computes, all by code in Decimal:
    gain or loss    realised net less `asset.book_value`
    excess mileage  max(0, `asset.mileage_at_return` - `asset.contract_mileage`) x the pack's `excess_mileage_rate` (the
                    `kind: close` rule of `runtime.suggestion_rules`, dollars a mile)
    excess wear     the sum of the inspection's recon lines (`condition.recon_lines`) with `excessWear`
An amount that is zero is not posted. Each other amount becomes an agent-prepared `usedCar.post`: `residual` (the gain or loss, to
S/4HANA through the journal writer `residual`) and `excess_mileage` and `excess_wear` (to the lease system through the writer
`lessee_charge`). `usedCar.post` is in HELD_FOR_PERSON, so the hold policy holds each as a proposal for Finance at every level
(`proposal.accept` is a person's, never an agent's, and a person may not accept what they prepared themselves). Accepting it
records the post on the case (`close.posted.<kind>`) and, with instructions on, queues the instruction on its own, outside the
approval's plan (`instructions.queue.OFF_PLAN`; key `CLOSE.<case>.<kind>.<cents>`). A second `close_case` prepares nothing
new for an amount that already has a proposal, whatever its state.

Never does: confirm an outcome, close the case (its stage is the last acknowledgement's) or approve anything; a case that is not a
used car's, was not approved, or has no sale yet is left alone (`CloseResult.status`). No model step (R16): this reads facts and
computes amounts; the model's explanation of the deltas is the reconcile stage's (P9-2.21), which reads `close` on the case.
Accounting references are for orientation only: Finance and Kinective's Legal team confirm them.
"""

import json
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.core.config import get_settings
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.canonical import store as canonical
from di.services.cases import car_facts, process
from di.services.cases import store as case_store

TEMPLATE = "used_cars"
AGENT = "coordinator"  # the agent that prepares the posts when the caller is not one (a person's call, a test)
KINDS = ("residual", "excess_mileage", "excess_wear")
INSTRUCTION = {
    "residual": ("residual", "erp"),
    "excess_mileage": ("lessee_charge", "uc_lease"),
    "excess_wear": ("lessee_charge", "uc_lease"),
}
STEP = {"residual": 0, "excess_mileage": 1, "excess_wear": 2}  # the instruction's `step` under approval_ref CLOSE-<case>
CENT = Decimal("0.01")

Status = Literal["closed", "not_applicable", "not_approved", "waiting_for_sale"]


@dataclass(frozen=True)
class CloseResult:
    """What `close_case` found and prepared. `posts` is one entry per amount: {kind, amount, label, state, proposal}, state
    `held` (a proposal for Finance), `exists` (one was prepared before, `proposal` its id when known) or `refused` (`why`)."""

    status: Status
    reason: str = ""
    sale: dict[str, Any] | None = None
    gain_loss: float | None = None
    charges: dict[str, float] = field(default_factory=dict)
    posts: list[dict[str, Any]] = field(default_factory=list)


def _d(v: Any) -> Decimal:
    return Decimal(str(v))


def _money(v: Decimal) -> float:
    return float(v.quantize(CENT, ROUND_HALF_UP))


def excess_rate(pack: Any) -> Decimal:
    """The pack's dollars a mile over the contract mileage (`kind: close` of `runtime.suggestion_rules`), 0 when it has none."""
    for r in pack.runtime.suggestion_rules:
        if r.get("kind") == "close" and (r.get("params") or {}).get("excess_mileage_rate") is not None:
            return _d(r["params"]["excess_mileage_rate"])
    return Decimal(0)


def sale_facts(s: Session, asset_key: str) -> dict[str, Any]:
    """The car's `outcome` record, as written by the dealer system's and the auction platform's adapters (empty: not sold)."""
    rec = canonical.get(s, "outcome", asset_key)
    return dict((rec or {}).get("data") or {})


def _sale_record(route: dict[str, Any], facts: dict[str, Any]) -> tuple[dict[str, Any], Decimal | None]:
    """The sale against the route's forecast, and the realised net (None when the route has no sale line to replace)."""
    terms = [t for t in route.get("terms") or [] if isinstance(t, dict)]
    price, days = _d(facts["sale_price"]), facts.get("days_to_sale")
    sale_lines = [t for t in terms if t.get("kind") == "sale"]
    forecast_price = sum((_d(t["amt"]) for t in sale_lines), Decimal(0))
    forecast_days = (route.get("dest") or {}).get("days")
    forecast_net = _d(route["net"])
    realised: Decimal | None = None
    if sale_lines:
        realised = forecast_net + (price - forecast_price)
        holding = next((t for t in terms if str(t.get("label", "")).startswith("Holding")), None)
        if holding is not None and days is not None and forecast_days:
            rate = abs(_d(holding["amt"])) / _d(forecast_days)  # the holding cost a day the forecast assumed
            realised += abs(_d(holding["amt"])) - rate * _d(days)
    sale: dict[str, Any] = {
        "route": route.get("id"), "sale_price": _money(price), "sold_at": facts.get("sold_at"), "days_to_sale": days,
        "forecast_price": _money(forecast_price) if sale_lines else None, "forecast_days": forecast_days,
        "forecast_net": _money(forecast_net), "realised_net": _money(realised) if realised is not None else None,
        "price_error": _money(price - forecast_price) if sale_lines else None,
        "net_error": _money(realised - forecast_net) if realised is not None else None,
        "days_error": days - forecast_days if days is not None and forecast_days is not None else None,
    }  # fmt: skip
    return sale, realised


def amounts(facts: dict[str, dict[str, Any]], pack: Any, realised: Decimal | None) -> dict[str, tuple[Decimal, str]]:
    """The amounts of a lease return's close by kind: {kind: (amount, label)}, only those that are not zero."""
    asset, cond = facts.get("asset", {}), facts.get("condition", {})
    out: dict[str, tuple[Decimal, str]] = {}
    if asset.get("return_kind") != "lease_end":
        return out
    book = asset.get("book_value")
    if realised is not None and book is not None:
        gain = realised - _d(book)
        if gain:
            out["residual"] = (gain, "Residual gain" if gain > 0 else "Residual loss")
    miles, contract = asset.get("mileage_at_return"), asset.get("contract_mileage")
    if miles is not None and contract is not None:
        over = max(Decimal(0), _d(miles) - _d(contract))
        if over * excess_rate(pack):
            out["excess_mileage"] = (over * excess_rate(pack), f"Excess mileage, {over:,.0f} miles over the contract")
    wear = sum(
        (_d(x["amount"]) for x in cond.get("recon_lines") or [] if isinstance(x, dict) and x.get("excessWear")), Decimal(0)
    )
    if wear:
        out["excess_wear"] = (wear, "Excess wear on return")
    return out


def _prepared(s: Session, case_id: str, kind: str, amount: Decimal) -> int | None:
    """The id of a proposal already prepared for this amount of this kind (any state: a rejected one is not asked again)."""
    row = s.execute(
        text(
            "SELECT id FROM agent_proposal WHERE action = 'usedCar.post' AND case_id = :c AND input ->> 'kind' = :k "
            "AND (input ->> 'amount')::numeric = :a ORDER BY id DESC LIMIT 1"
        ),
        {"c": case_id, "k": kind, "a": amount},
    ).scalar()
    return int(row) if row is not None else None


def _agent_ctx(s: Session, ctx: CallContext | None) -> CallContext:
    if ctx is None:
        return CallContext(actor=SYSTEM, session=s, preparer=AGENT)
    return replace(ctx, session=s, preparer=ctx.preparer or AGENT, confirmed=False)


def close_case(s: Session, case_id: str, ctx: CallContext | None = None) -> CloseResult:
    """The sale of the car against the forecast, and the amounts of its close prepared for Finance (module docstring). `ctx` is
    the caller's (an agent run's, with its stage); the posts are always prepared by an agent, so they are always held."""
    c = case_store.get(s, case_id, for_update=True)
    if c is None or c.get("template") != TEMPLATE:
        return CloseResult("not_applicable", "Not a used-car case.")
    route = c.get("chosen")
    if not c.get("exec") or not route:
        return CloseResult("not_approved", "No decision has been approved for the car yet.")
    facts = sale_facts(s, str(c["assetId"]))
    if facts.get("sale_price") is None:
        return CloseResult("waiting_for_sale", "The car has not sold yet.")
    sale, realised = _sale_record(dict(route), facts)
    now = (ctx.now if ctx else clock.now()).isoformat()
    car = car_facts.records(s, str(c["assetId"]))
    todo = amounts(car, process.pack_of(s, case_id), realised)
    c["close"] = {**(c.get("close") or {}), "sale": sale, "at": now}
    case_store.save(s, c)
    caller = _agent_ctx(s, ctx)
    posts: list[dict[str, Any]] = []
    for kind in KINDS:
        if kind not in todo:
            continue
        amount, label = todo[kind]
        post = {"kind": kind, "amount": _money(amount), "label": label}
        if (pid := _prepared(s, case_id, kind, amount.quantize(CENT, ROUND_HALF_UP))) is not None:
            posts.append(post | {"state": "exists", "proposal": pid})
            continue
        r = invoke("usedCar.post", {"case_id": case_id, **post}, caller)
        if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
            posts.append(post | {"state": "held", "proposal": r["output"]["held"]})
        else:
            posts.append(post | {"state": "refused", "why": r["error"]["message"] if not r["ok"] else "Not held for a person."})
    gain = _money(todo["residual"][0]) if "residual" in todo else None
    return CloseResult(
        "closed", "The sale is recorded against the forecast.", sale, gain,
        {k: _money(v[0]) for k, v in todo.items() if k != "residual"}, posts,
    )  # fmt: skip


# ---------------------------------------------------------------- the actions
ACTIONS.setdefault(
    "usedCar.close",
    ActionDef(
        id="usedCar.close", title="Close a sold used car", verb="close a sold used car",
        desc="Record the sale of a used car against the decision's forecast and prepare its residual gain or loss and the "
        "lessee's charges for Finance. Each amount is held for a person to accept.",
        risk="act", perm="confirm", scope="case", input={"case_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "usedCar.post",
    ActionDef(
        id="usedCar.post", title="Post an amount of a used car's close", verb="post the close of a used car",
        desc="Post the residual gain or loss to Finance, or a charge to the lessee, once Finance accepts it. An agent's call "
        "is held for a person.",
        risk="act", perm="confirm", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "kind": {"req": True, "t": "string"},
            "amount": {"req": True, "t": "number"},
            "label": {"req": True, "t": "string"},
        },
    ),
)  # fmt: skip


def _used_car(ctx: CallContext, case_id: str) -> case_store.Case | None:
    c = case_store.get(ctx.session, case_id)
    return c if c is not None and c.get("template") == TEMPLATE else None


@guard("usedCar.close")
def close_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return None if _used_car(ctx, i["case_id"]) else ("not_found", f"No live used-car case {i['case_id']}.")


@implement("usedCar.close")
def close_action(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    r = close_case(ctx.session, i["case_id"], ctx)
    return {
        "case_id": i["case_id"], "status": r.status, "reason": r.reason, "sale": r.sale, "gain_loss": r.gain_loss,
        "charges": r.charges, "posts": r.posts,
    }  # fmt: skip


def _post_key(i: dict[str, Any]) -> str:
    return f"{i['case_id']}:{i['kind']}"


@guard("usedCar.post")
def post_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = _used_car(ctx, i["case_id"])
    if c is None:
        return "not_found", f"No live used-car case {i['case_id']}."
    if i["kind"] not in KINDS:
        return "validation_error", f"Unknown kind {i['kind']}. Use one of {', '.join(KINDS)}."
    if not i["amount"] or (i["kind"] != "residual" and i["amount"] < 0):
        return "validation_error", "The amount is zero or has the wrong sign."
    if ((c.get("close") or {}).get("posted") or {}).get(i["kind"]):
        return "duplicate", f"The {i['kind'].replace('_', ' ')} of {i['case_id']} is already posted."
    return None


@implement("usedCar.post", idem=lambda i, ctx: _post_key(i))  # noqa: ARG005 - the key is the input
def post(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = case_store.get(ctx.session, i["case_id"], for_update=True)
    if c is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No live used-car case {i['case_id']}.")
    amount = _d(i["amount"]).quantize(CENT, ROUND_HALF_UP)
    iid = _queue(ctx.session, c, i["kind"], amount, str(i["label"]))
    close = dict(c.get("close") or {})
    close["posted"] = {
        **(close.get("posted") or {}),
        i["kind"]: {
            "amount": _money(amount),
            "label": i["label"],
            "by": ctx.actor.id,
            "at": ctx.now.isoformat(),
            "instruction": iid,
        },
    }
    c["close"] = close
    case_store.save(ctx.session, c)
    return {"case_id": c["id"], "kind": i["kind"], "amount": _money(amount), "instruction": iid}


def sending() -> bool:
    """Is sending instructions switched on (`DI_INSTRUCTIONS`, the same switch as `instructions.queue.enabled`)?"""
    return bool(get_settings().instructions)


def _queue(s: Session, c: case_store.Case, kind: str, amount: Decimal, label: str) -> int | None:
    """The instruction for one post, sent on its own (only when sending instructions is switched on): one row and one
    `instruction.send` job, idempotent on the case, the kind and the amount in cents."""
    from di.core import jobs  # lazy: the job queue is only needed by the write

    if not sending():
        return None
    cents = int((amount * 100).to_integral_value())
    ref, key, step = f"CLOSE-{c['id']}", f"CLOSE.{c['id']}.{kind}.{cents}", STEP[kind]
    detail = json.dumps({"close": {"kind": kind, "amount": float(amount), "label": label}})
    s.execute(text("DELETE FROM instruction WHERE approval_ref = :r AND step = :n"), {"r": ref, "n": step})
    iid = s.execute(
        text(
            "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, detail, queued_at) "
            "VALUES (:c, :r, :n, :k, :sys, :key, CAST(:refs AS jsonb), CAST(:d AS jsonb), :at) "
            "ON CONFLICT (idem_key) DO NOTHING RETURNING id"
        ),
        {
            "c": c["id"], "r": ref, "n": step, "k": INSTRUCTION[kind][0],
            "sys": INSTRUCTION[kind][1], "key": key,
            "refs": json.dumps([key]), "d": detail, "at": clock.now(),
        },
    ).scalar()  # fmt: skip
    if iid is not None:
        jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    return int(iid) if iid is not None else None
