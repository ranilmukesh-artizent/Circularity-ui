"""Keep, like-life swap or upgrade for each tool of a contract refresh (plan 9, P9-5.2, story CR-02). Pure.

    tool_actions(lines, life, eop, next_term_end, evaluator, market, table) -> list[ToolAction]   one action per tool line
    totals(actions) -> {"keep": n, "swap": n, "upgrade": n}                                       the panel's split
    flag(action) -> str | None                                                                    "life estimate low confidence"
    hold_reason(actions) -> "confidence" | None                                           why the decision waits for a person
    needs(case_id, actions) -> list[Need]                                                 the like-life need of each swap (P9-5.3)
    price(actions, match, rate_card, credit_table, history, market, *, fees, lines, term_months) -> Pricing   the money (P9-5.4)

The per-tool choice is the market's decision table `refresh_tool_action` (I-15, P9-4.2), first hit: parts end before the next term
ends -> `upgrade` to the successor; remaining life under 25% -> `swap`; else `keep`. The thresholds are business rules (BR-C1),
so they live in the table and change only through its maker-checker (a market or customer overlay, P9-5.6's levers). The table's
`reason` is a template: `{class}`, `{eop}`, `{term_end}`, `{successor}` and `{rul}` are filled here from computed facts.

Inputs, all passed in: `lines` (`{serial, cls}`), `life` (serial -> `tool_life.LifeResult` of P9-3.9), `eop` (class -> end of
parts and successor from `plm.end_of_parts`, P9-3.3) and `next_term_end` (the contract's term end plus its term months). A tool
with no life result is treated as 100% with Low confidence (nothing is known, so the decision waits). A tool whose life
confidence is Low (GR-13) keeps its action but is flagged, and `hold_reason` says `confidence`.

`price` (P9-5.4, CR-04) puts money on the choices, in the market's currency, all `Decimal`, each figure to the cent.
Fees come from the market's rate cards in force on the decision date (the version is cited on every line): a tool's new-unit fee a
month is its class's list price (`terms`) times `refresh_fee_rate` (`refresh_terms`), a refurbished unit's that less
`refurb_fee_discount`. Kept tools keep their fee, swaps move to the refurbished-unit fee, upgrades to the new-unit fee. Saving versus new is the swaps' fee difference over the
next term. An upgraded tool is credited from the market's `credit_rules` table (`credit_pct` of the list price, at most
`credit_cap`), by life used. Three routes are valued (`proposal`, `renew_as_is`, `upgrade_all`), the first two weighted by the
renewal likelihood of `renewal_odds` (a computed rate from the contract history), and ranked by net; the standard route is
`renew_as_is`.

Never does: read the database or the clock, write text with a model (every sentence is a table template over computed numbers, so
there is no `AgentLoop` step here, and no number is ever written by a model) or approve anything. Implements no registry entry; it
reads I-15 tables.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from di.services.engine import like_life
from di.services.modeler.tables import DecisionTableEvaluator, JdmTable, RateCard, ZenEvaluator, rate
from di.services.modeler.valuers import renewal_odds
from di.services.modeler.valuers.tool_life import LifeResult

Action = Literal["keep", "swap", "upgrade"]
ACTIONS: tuple[Action, ...] = ("keep", "swap", "upgrade")
LOW_FLAG = "life estimate low confidence"


@dataclass(frozen=True)
class ToolAction:
    serial: str
    cls: str
    action: Action
    reason: str
    rul_pct: int
    confidence: str
    end_of_parts: date | None
    successor: str | None


def tool_actions(
    lines: Sequence[Mapping[str, Any]],
    life: Mapping[str, LifeResult],
    eop: Mapping[str, tuple[date | None, str | None]],
    next_term_end: date,
    evaluator: DecisionTableEvaluator,
    market: str,
    table: JdmTable,
) -> list[ToolAction]:
    """The action of each line (module docstring), in the order of `lines`."""
    out: list[ToolAction] = []
    for ln in lines:
        serial, cls = str(ln["serial"]), str(ln.get("cls") or ln.get("tool_class") or "")
        lf = life.get(serial)
        rul, conf = (lf.rul_tool, lf.confidence) if lf is not None else (100, "Low")
        ends, successor = eop.get(cls, (None, None))
        before = ends is not None and ends < next_term_end
        r = evaluator.evaluate(
            table,
            {
                "market": market, "rul_pct": rul, "parts_end_before_term": before,
                "cover_type": str(ln.get("cover_type") or "fleet"),
            },
        )  # fmt: skip
        action = str(r.outputs.get("action"))
        if action not in ACTIONS:
            raise ValueError(f"The table refresh_tool_action gave the action {action!r} for {serial}")
        reason = (
            str(r.outputs.get("reason") or "")
            .replace("{class}", cls)
            .replace("{eop}", ends.isoformat() if ends else "an unknown date")
            .replace("{term_end}", next_term_end.isoformat())
            .replace("{successor}", successor or "its successor")
            .replace("{rul}", str(rul))
        )
        out.append(ToolAction(serial, cls, action, reason, rul, conf, ends, successor))
    return out


def totals(actions: Sequence[ToolAction]) -> dict[str, int]:
    """How many tools are kept, swapped and upgraded."""
    return {a: sum(1 for x in actions if x.action == a) for a in ACTIONS}


def flag(a: ToolAction) -> str | None:
    return LOW_FLAG if a.confidence == "Low" else None


def hold_reason(actions: Sequence[ToolAction]) -> Literal["confidence"] | None:
    """`confidence` when any tool's life estimate is Low confidence: a person decides before the proposal goes on."""
    return "confidence" if any(a.confidence == "Low" for a in actions) else None


def needs(case_id: str, actions: Sequence[ToolAction]) -> list[like_life.Need]:
    """One like-life need for each swapped tool (P9-5.3): id `<case>:<serial>`, the class, and the target life, the median of
    the tools kept (`like_life.target`). The assignment itself is `like_life.match`, over every open contract together."""
    tgt = like_life.target(actions)
    return [like_life.Need(f"{case_id}:{a.serial}", case_id, a.cls, tgt) for a in actions if a.action == "swap"]


# ---------------------------------------------------------------- the proposal's money (P9-5.4, CR-04)
D = Decimal
CENT = D("0.01")
STANDARD = "renew_as_is"
ROUTE_NAMES = {"proposal": "Send the proposal", STANDARD: "Renew as it is", "upgrade_all": "Upgrade every tool"}


def _c(x: Decimal) -> Decimal:
    return x.quantize(CENT, ROUND_HALF_UP)


@dataclass(frozen=True)
class ValueLine:
    label: str
    amount: Decimal  # market currency; a cost is negative
    cite: str  # the rate card or table version it comes from


@dataclass(frozen=True)
class Credit:
    serial: str
    amount: Decimal
    rule_version: int  # the version of the market's credit_rules table


@dataclass(frozen=True)
class RouteValue:
    id: str
    name: str
    net: Decimal
    standard: bool


@dataclass(frozen=True)
class Pricing:
    currency: str
    rate_card_version: int
    term_months: int
    current_fee_month: Decimal
    proposed_fee_month: Decimal
    saving_vs_new: Decimal
    renewal_likelihood: float  # with the proposal
    renewal_without: float  # with no proposal
    renewal_basis: str
    credits: list[Credit]
    credit_total: Decimal
    lines: list[ValueLine]
    routes: list[RouteValue]  # best net first
    best: str
    uplift: Decimal  # the best route's net less the standard route's


def _credit(ev: DecisionTableEvaluator, table: JdmTable, market: str, a: ToolAction, months: int, list_price: Decimal) -> Decimal:
    r = ev.evaluate(table, {"market": market, "family": a.cls, "age_months": months, "life_used_pct": 100 - a.rul_pct})
    pct, cap = D(str(r.outputs["credit_pct"])), D(str(r.outputs["credit_cap"]))
    return _c(min(pct * list_price, cap))


def price(
    actions: Sequence[ToolAction],
    match: Sequence[Mapping[str, Any]],
    rate_card: RateCard,
    credit_table: JdmTable,
    history: Sequence[Mapping[str, Any]],
    market: str,
    *,
    fees: RateCard,
    lines: Sequence[Mapping[str, Any]],
    term_months: int,
    credit_version: int = 1,
    evaluator: DecisionTableEvaluator | None = None,
) -> Pricing:
    """The fees, saving, credits, renewal likelihood and the three routes of a refresh (module docstring). `lines` are the
    contract's (`{serial, fee, months}`), `fees` the market's `refresh_terms` card (`rate_card` is its `terms`),
    `match` the like-life units of the swaps (`{serial, unit_id}`), `history` the fleet's ended contracts (`renewal_odds`)."""
    ev = evaluator or ZenEvaluator()
    card = f"terms v{rate_card.version}, refresh_terms v{fees.version}"
    cred = f"credit_rules v{credit_version}"
    by = {str(ln["serial"]): ln for ln in lines}
    unit = {str(m["serial"]): m.get("unit_id") for m in match}
    fee_rate, discount = rate(fees, "refresh_fee_rate"), rate(fees, "refurb_fee_discount")
    cost_share, logistics = rate(fees, "refurb_cost_share"), rate(rate_card, "logistics")
    n = D(term_months)
    out: list[ValueLine] = []
    current = proposed = saving = swap_cost = new_all = credit_all = D(0)
    credits: list[Credit] = []
    for a in actions:
        ln = by.get(a.serial, {})
        cur = D(str(ln.get("fee") or 0))
        list_price = rate(rate_card, f"list_price.{a.cls}")
        new_fee = _c(list_price * fee_rate)
        refurb_fee = _c(new_fee * (1 - discount))
        current += cur
        new_all += new_fee
        months = int(ln.get("months") or 0)
        credit_all += _credit(ev, credit_table, market, a, months, list_price)
        if a.action == "keep":
            proposed += cur
            out.append(ValueLine(f"{a.serial} kept at its fee", _c(cur), card))
        elif a.action == "swap":
            proposed += refurb_fee
            saving += (new_fee - refurb_fee) * n
            cost = _c(cost_share * list_price + logistics)
            swap_cost += cost
            u = unit.get(a.serial)
            out.append(
                ValueLine(f"{a.serial} swapped to {u or 'a refurbished unit (none matched yet)'}: fee a month", refurb_fee, card)
            )
            out.append(ValueLine(f"{a.serial} refurbishment and logistics", -cost, card))
        else:
            proposed += new_fee
            c = _credit(ev, credit_table, market, a, months, list_price)
            credits.append(Credit(a.serial, c, credit_version))
            out.append(ValueLine(f"{a.serial} upgraded to {a.successor or 'its successor'}: fee a month", new_fee, card))
            out.append(ValueLine(f"{a.serial} credit on the old tool", -c, cred))
    total = sum((c.amount for c in credits), D(0))
    segment = renewal_odds.segment_of(market, len(actions))
    p_with, basis = renewal_odds.likelihood(history, segment, True)
    p_without, _ = renewal_odds.likelihood(history, segment, False)
    w, wo = D(str(p_with)), D(str(p_without))
    nets = {
        "proposal": _c((proposed * n - swap_cost - total) * w),
        STANDARD: _c(current * n * wo),
        "upgrade_all": _c((new_all * n - credit_all) * w),
    }
    routes = sorted((RouteValue(k, ROUTE_NAMES[k], v, k == STANDARD) for k, v in nets.items()), key=lambda r: (-r.net, r.id))
    out.append(ValueLine(f"Renewal likelihood {p_with:.0%} with a proposal, {p_without:.0%} without", D(0), "renewal history"))
    return Pricing(
        currency=rate_card.currency, rate_card_version=rate_card.version, term_months=term_months,
        current_fee_month=_c(current), proposed_fee_month=_c(proposed), saving_vs_new=_c(saving),
        renewal_likelihood=p_with, renewal_without=p_without, renewal_basis=basis, credits=credits, credit_total=_c(total),
        lines=out, routes=routes, best=routes[0].id, uplift=_c(routes[0].net - nets[STANDARD]),
    )  # fmt: skip
