"""A contract refresh case as a decision a person approves, and what its approval carries out (plan 9, P9-5.4 and P9-5.5,
stories CR-04 and CR-05; registry entries I-6, I-10, I-11).

    quote(s, c, acts=None, match=None) -> Quote | None   the proposal priced: fees, credits, renewal odds, routes, approver
    attach(s, c) -> bool                                 set the routes, the recommendation, the holds, the proposal documents
    on_approve(c)                                        in `decision.approve`'s transaction: keep the chosen route's document
    send_back(s, case_id, reason)                        a unit was taken meanwhile: the decision goes back to the Fleet desk
    units_of(c) -> [unit id]                             the units the proposal route would hold

- **The decision.** The three priced routes (`proposal`, `renew_as_is`, `upgrade_all`) become the case's routes, ranked by
  net, and the case waits for approval (`awaiting_approval`) as any decision does: `decision.submit`, then a person's
  `decision.approve` (or `decision.override` for another route). They are priced again when the case is opened, re-evaluated
  and submitted, so the approver sees what was submitted. Its `approvalHolds` (GR-C1 credits over the limit to Sales, GR-C2
  everything else to the Fleet desk) keep the standing policy and every agent from approving it.
- **The gate first (P9-5.8, R20).** GR-07 on the contract (`contract_block`: an open theft claim or damage charge) blocks
  the proposal before any pricing: no routes, holds or documents, and `refreshBlock` says which gate and why. Recalled tools and
  units are gated earlier still (`tool_queue`), the holds come last.
- **The documents.** `refreshProposal[route]` is what that route would send to the customer: the fee a month now and
  offered, the tools' lines (action, fee, credit), the saving, the renewal likelihood and the units matched to the swaps. It is
  JSON and computed; nothing in it is worded by a model (R16 has nothing to route: no `AgentLoop` step). On approval the
  chosen one moves to `exec.proposal` with the approval date and the validity (the market's `proposal_valid_days`, 14).
- **Carrying it out.** The existing execution plan (`execution/steps.py`: `propsend`, `propdraft`, `propreserve`) and the
  instruction queue send it; the writers are in `instructions/writers_fleet.py`. Nothing is sent, drafted or held before a
  person approves.

Never does: approve, send or hold a unit for a person (the writers run only for an approved plan), write language, or call a
source.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import contract_history
from di.repositories import market_tables as tables_repo
from di.services.actions.registry import ActionError
from di.services.cases import intake, lifecycle, process, store, tool_queue
from di.services.engine.routes import mk_route, rank_routes, term
from di.services.modeler import tables
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import contract_refresh, fleet_evidence, renewal_odds, tool_approval
from di.services.service_desk.inputs import fx_per_usd

DEFAULT_VALID_DAYS = 14  # when the market's terms name none
DESK = "Fleet desk"


@dataclass(frozen=True)
class Quote:
    pricing: contract_refresh.Pricing
    fees_version: int
    credit_version: int
    credit_usd: float
    route: tool_approval.ApprovalRoute
    match: list[dict[str, Any]]
    valid_days: int


def _match(s: Session, c: dict[str, Any]) -> list[dict[str, Any]]:
    """The like-life unit of each swap of this case (tool_queue.refresh_match, over the org's open refresh cases together)."""
    return tool_queue.case_match(s, c)


def contract_block(s: Session, c: dict[str, Any]) -> str | None:
    """GR-07 (gate `G-CON-2`) on the contract's lines: why the contract gives no right to propose, None when it does. An open
    theft claim or damage charge on a line blocks, as it does for a returned tool (`fleet_evidence.contract_check`); the line's
    own status is not read (a contract in its window is on contract) and no owner is named."""
    r = c.get("refresh") or {}
    rows = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'contract_line' AND data ->> 'contract_id' = :c ORDER BY key"),
        {"c": r.get("contract_id") or c.get("contract_id")},
    )
    for row in rows:
        line = fleet_evidence.line_value(row.data) | {"status": "active"}
        res = fleet_evidence.contract_check(line, "", str(row.key))
        if not res.passed:
            return f"{fleet_evidence.GATE}: {res.reason}"
    return None


def quote(
    s: Session,
    c: dict[str, Any],
    acts: list[contract_refresh.ToolAction] | None = None,
    match: list[dict[str, Any]] | None = None,
) -> Quote | None:
    """The proposal priced and who approves it; None when the contract gate blocks it, and without tools, a market or the
    market's tables in force."""
    if contract_block(s, c):  # the gate first (R20): a blocked contract is never priced
        return None
    r = c.get("refresh") or {}
    market, org, today = r.get("market"), c.get("owner"), clock.now().date()
    acts = tool_queue.refresh_actions(s, c) if acts is None else acts
    if not acts or not market:
        return None
    args = (s, org, tool_queue.PACK, tool_queue.FLOW, str(market))
    card = tables_repo.effective(*args, "terms", today)
    credit = tables_repo.effective(*args, "credit_rules", today)
    fees = tables_repo.effective(*args, "refresh_terms", today)
    if card is None or credit is None or fees is None:
        return None
    match = _match(s, c) if match is None else match
    p = contract_refresh.price(
        acts, match, tables.rate_card(card), tables.JdmTable.model_validate(credit.body),
        renewal_odds.within(contract_history.rows(s), today), str(market),
        fees=tables.rate_card(fees), lines=list(r.get("lines") or []), term_months=int(r.get("term_months") or 0),
        credit_version=credit.version,
    )  # fmt: skip
    usd = float(p.credit_total / fx_per_usd(s, p.currency, today))
    days = int(tables.rate_card(card).values.get("proposal_valid_days", DEFAULT_VALID_DAYS))
    return Quote(p, fees.version, credit.version, usd, tool_approval.refresh_route(usd, load_pack(tool_queue.PACK)), match, days)


def _f(x: Decimal) -> float:
    return float(x)


def _doc(c: dict[str, Any], q: Quote, route_id: str) -> dict[str, Any]:
    """What the route sends to the customer (module docstring)."""
    r, p = c.get("refresh") or {}, q.pricing
    tools = p.tools[route_id]
    units = [
        {"serial": m["serial"], "need_id": m["need_id"], "unit_id": m["unit_id"], "source": m.get("source")}
        for m in q.match
        if route_id == "proposal" and m.get("unit_id")
    ]
    return {
        "route": route_id, "contract": r.get("contract_id") or c.get("contract_id"), "customer": r.get("customer"),
        "market": r.get("market"), "currency": p.currency, "term_months": p.term_months, "valid_days": q.valid_days,
        "fee_month_current": _f(p.current_fee_month), "fee_month_proposed": _f(sum((t.fee_month for t in tools), Decimal(0))),
        "saving_vs_new": _f(p.saving_vs_new) if route_id == "proposal" else 0.0,
        "credit_total": _f(sum((t.credit for t in tools), Decimal(0))), "renewal_likelihood": p.renewal_likelihood,
        "rate_card_version": p.rate_card_version, "fees_version": q.fees_version, "credit_rules_version": q.credit_version,
        "lines": [
            {"serial": t.serial, "cls": t.cls, "action": t.action, "fee_month": _f(t.fee_month), "credit": _f(t.credit),
             "successor": t.successor}
            for t in tools
        ],
        "units": units,
    }  # fmt: skip


def _exists(s: Session, case_id: str) -> bool:
    return s.execute(text("SELECT 1 FROM case_record WHERE id = :c"), {"c": case_id}).first() is not None


def attach(s: Session, c: dict[str, Any]) -> bool:
    """Price the refresh and make its routes the case's decision (module docstring). A case not stored yet is priced without
    unit matches (the match reads the stored open cases). False, and the case without a decision, when there is nothing to price;
    a contract the gate blocks (`contract_block`) keeps `refreshBlock` {gate, reason}, no proposal, and the holds it had."""
    if block := contract_block(s, c):
        c.pop("refreshProposal", None)
        c["refreshBlock"] = {"gate": fleet_evidence.GATE, "reason": block}
        # the holds the case had stay (review M7): a block that appears after the case opened never leaves a decision the
        # standing policy could cover, and the approval is refused with the gate's reason (`block_refusal`)
        return False
    c.pop("refreshBlock", None)
    q = quote(s, c, match=None if _exists(s, str(c["id"])) else [])
    if q is None:
        return False
    p, r = q.pricing, c.get("refresh") or {}
    routes = []
    for rv in p.routes:
        t = term(f"Expected net of {rv.name.lower()}", round(float(rv.net)), "v" if rv.net >= 0 else "c")
        why = f"{rv.name}: {p.currency} {rv.net:,.2f} expected net over {p.term_months} months at the modelled renewal odds"
        routes.append(
            mk_route(
                {
                    "id": rv.id,
                    "plan": rv.name,
                    "terms": [t],
                    "demandLabel": r.get("customer") or "Customer",
                    "unc": "",
                    "why": why,
                }
            )
        )
    c["routes"] = routes
    c["recommendation"] = rank_routes(routes)
    c["approvalRoute"] = {"kind": q.route.kind, "role": q.route.role, "reasons": list(q.route.reasons)}
    c["approvalHolds"] = [dict(h) for h in q.route.holds]
    c["refreshProposal"] = {rid: _doc(c, q, rid) for rid in p.tools}
    c.pop("refreshBack", None)
    if c.get("stage") in (None, "none"):
        c["stage"] = "awaiting_approval"
    return True


def best_of(s: Session, c: dict[str, Any]) -> tuple[str | None, float]:
    """The best route and its net, to the cent, as the decision is priced (the Modeler's simulation queue reads it)."""
    q = quote(s, c)
    return (None, 0.0) if q is None else (q.pricing.best, float(q.pricing.routes[0].net))


def units_of(c: dict[str, Any]) -> list[str]:
    """The units the proposal route would hold, by id."""
    return [u["unit_id"] for u in ((c.get("refreshProposal") or {}).get("proposal") or {}).get("units") or []]


def on_approve(c: dict[str, Any]) -> None:
    """Keep the chosen route's proposal document on the approved plan (module docstring). No commit."""
    if not intake.is_refresh(c) or not c.get("exec"):
        return
    doc = (c.get("refreshProposal") or {}).get(str((c.get("chosen") or {}).get("id")))
    if doc is None:
        raise ActionError("conflict", f"{c['id']} has no priced proposal to send: submit it again.")
    today = clock.now().date()
    c["exec"]["proposal"] = doc | {
        "approved_on": today.isoformat(), "valid_until": (today + timedelta(days=int(doc["valid_days"]))).isoformat(),
        "approver": c["exec"].get("approver"),
    }  # fmt: skip


def send_back(s: Session, case_id: str, reason: str) -> None:
    """A unit this proposal would hold was reserved by another approval: the case goes back to re-evaluation (the next match
    leaves that unit out) and the decision to the Fleet desk with the reason, as a decline does. In the caller's transaction."""
    c = store.get(s, case_id, for_update=True)
    if c is None or not lifecycle.can_move(c["stage"], "reeval"):
        return
    c["reevalReason"] = reason
    c["refreshBack"] = {"to": DESK, "reason": reason}
    c["submitted"] = None
    c["cycle"] = (c.get("cycle") or 0) + 1  # a new decision cycle: new approval reference and keys
    lifecycle.move(s, c, "reeval", reason, "system")


def block_refusal(c: dict[str, Any]) -> tuple[str, str] | None:
    """The approval refusal of a contract the gate blocks (GR-07): its reason, as `refreshBlock` shows it (review M7)."""
    b = c.get("refreshBlock")
    return ("conflict", f"{c['id']}: {b['reason']}") if isinstance(b, dict) and b.get("reason") else None


def approver_refusal(s: Session, c: dict[str, Any], plan: str | None, role: str) -> tuple[str, str] | None:
    """Who may approve the route the person chooses (plan `plan`, else the recommendation): GR-C1 is computed again on that
    route's own credits (an override to `upgrade_all` credits every tool), and the role it names (Sales: Approver) is the role
    the approver must hold, Admin included (review M4 and M5). None when the actor may."""
    route = next((r for r in c.get("routes") or [] if r["plan"] == plan), None) or c.get("recommendation")
    doc = (c.get("refreshProposal") or {}).get(str((route or {}).get("id")))
    if doc is None:
        return None
    credit = Decimal(str(doc.get("credit_total") or 0)) / fx_per_usd(s, str(doc.get("currency") or "USD"), clock.now().date())
    ar = tool_approval.refresh_route(float(credit), load_pack(tool_queue.PACK))
    needed = process.role_of_owner(ar.role or DESK)
    if needed == "Approver" and role not in ("Approver", "Admin"):
        return "out_of_scope", f"{c['id']}: {'; '.join(ar.reasons)}, so {ar.role} (an Approver) must approve it, not a {role}."
    return None
