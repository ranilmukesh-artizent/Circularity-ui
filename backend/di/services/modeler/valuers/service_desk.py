"""The options of a service ticket: fix, covered swap, upgrade (plan 9, P9-4.6, story SD-04; decides inside `decide_case`, I-6).

    decide_ticket(inputs) -> TicketDecision        per line the three options with their value lines, the best, and the case's
                                                   options (the sum over the lines); pure
    decide_batch(inputs) -> BatchDecision          a batch decided per tool (P9-4.8, SD-07): each line alone, the swaps taking
                                                   the stock in line order, the split and its totals; `batch_ticket` is the
                                                   case's view of it (options split, all_fix, all_upgrade)
    approval_holds(decision, route) -> [hold]      the holds of the route the case recommends: GR-S3, GR-S1, GR-14, GR-C1

`inputs` is `di.services.service_desk.inputs.gather`'s snapshot (JSON types): per line the estimate (P9-4.4) and the outputs
of the cover and credit tables with the table versions they cite (I-15), the terms card, the refurbished stock and the median
turnaround; for the case the take-up curve, the fx rate (units of the market currency per USD) and the approved table
versions of the decision date.

Order (R20): the gates (GR-07, GR-12) and the locked compliance (GR-S2: no swap unless the cover allows it) come first; then
the business rule BR-S1 (an upgrade from 50% of life used, or when the cover allows it; the flow's own rules act on the routes in
`decide_case`), then the values and the best option, and last the holds. Money is `Decimal`, each figure rounded half up to the
cent. Never does: read a table, the stock or a clock (the gatherer does), call a language model (every number and every reason
is computed, R16), write, approve or release anything (a person approves through I-10 and I-11).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from di.services.modeler.pack import load_pack
from di.services.modeler.valuers.tool_fleet import CLS

D = Decimal
CENT = D("0.01")
KEYS = ("fix", "swap", "upgrade")
NAMES = {
    "fix": "Fix it", "swap": "Covered swap", "upgrade": "Upgrade offer",
    "split": "Batch split", "all_fix": "Fix every tool", "all_upgrade": "Upgrade every tool",
}  # fmt: skip
COMPARE = (
    ("all_fix", "fix"),
    ("all_upgrade", "upgrade"),
)  # a batch case's comparison routes and the option each takes on every line
SPLIT_LABELS = (("upgrade", "Upgrade"), ("fix", "Fix"), ("swap", "Covered swap"))
STOCK_USED = "Refurbished stock used by earlier lines of this batch"
STALE = "Prices must come from the market's current approved table (GR-S3)"


def _d(x: Any) -> Decimal:
    return D(str(x))


OPTS: dict[str, Any] = load_pack("tool_fleet").valuer.params["service_desk"][
    "options"
]  # the pack's numbers (BR-S1, GR-14, GR-C1)
UPGRADE_LIFE = int(OPTS["upgrade_life_pct"])
GR_14_USD, GR_C1_USD = _d(OPTS["gr_14_usd"]), _d(OPTS["gr_c1_usd"])
OWNERS: dict[str, str] = OPTS["owners"]
TicketDecision = dict[str, Any]


def _c(x: Decimal) -> Decimal:
    return x.quantize(CENT, ROUND_HALF_UP)


def _f(x: Decimal) -> float:
    return float(_c(x))


def _take_up(t: Mapping[str, Any], pct: Decimal) -> float:
    return 1 / (1 + math.exp(-(float(t["a"]) + float(t.get("shift") or 0) + float(t["b"]) * float(pct))))


def _vl(kind: str, label: str, amt: Decimal, cites: str, basis: str = "") -> dict[str, Any]:
    """A value line: `kind` v (value) or c (cost); `amt` is positive; every line cites the table it came from."""
    return {"type": kind, "label": label, "amt": _f(amt), "basis": basis, "cites": cites}


def _option(k: str, eligible: bool, why: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "k": k,
        "name": NAMES[k],
        "eligible": eligible,
        "why": why,
        "customer_price": None,
        "margin": None,
        "expected_margin": None,
        "days": None,
        "take_up": None,
        "credit": None,
        "cost": None,
        "lines": [],
    }
    return base | kw


def _line_options(ln: Mapping[str, Any], fx: Decimal, take: Mapping[str, Any]) -> list[dict[str, Any]]:
    est, cover, credit, terms = ln.get("estimate"), ln["cover"], ln["credit"], ln["terms"]
    cls = str(ln["model_class"])
    if not est or not est.get("n"):  # no estimate: a technician checks the tool first
        why = "No estimate yet: a technician checks the tool first"
        return [_option(k, False, why) for k in KEYS]
    cost, log = _d(est["point"]), _d(terms["logistics"])
    t_ref, c_ref = terms["ref"], cover["ref"]
    back = _d(CLS[cls]["res"]["C"]) * _d(CLS[cls]["newP"]) * fx  # the tool counts as grade C until Returns grades it
    back_line = _vl("v", "Value of the tool taken back", back, "tool_fleet class card", "grade C residual share x new price")
    cost_lines = [_vl("c", e["label"], _d(e["amount"]), e["cites"], e.get("basis", "")) for e in est["lines"]]

    # fix
    covered = bool(cover["repair_covered"])
    price = D(0) if covered else cost * (1 + _d(terms["markup"]))
    fix_m = -(cost + log) if covered else price - cost - log
    fix = _option(
        "fix",
        True,
        cover["reason"] if covered else f"Repair at cost plus {_d(terms['markup']) * 100:.0f}% markup",
        customer_price=_f(price),
        margin=_f(fix_m),
        expected_margin=_f(fix_m),
        days=ln.get("fix_days"),
        cost=_f(cost),
        lines=[
            _vl("v", "Customer price", price, t_ref, "cost x (1 + markup)" if not covered else f"Covered: {c_ref}"),
            *cost_lines,
            _vl("c", "Logistics", log, t_ref),
        ],
    )

    # swap: GR-S2 (locked) and the stock
    if not cover["swap_allowed"]:
        swap = _option("swap", False, f"Covered swap is not allowed: {cover['reason']}")
    elif int(ln["refurb_stock"]) < 1:
        swap = _option("swap", False, f"No refurbished {ln['family']} in stock")
    else:
        refurb = _d(CLS[cls]["refurb"]) * fx
        m = -(refurb + 2 * log) + back
        swap = _option(
            "swap",
            True,
            cover["reason"],
            customer_price=0.0,
            margin=_f(m),
            expected_margin=_f(m),
            days=terms["swap_days"],
            cost=_f(refurb + 2 * log),
            lines=[
                _vl("c", "Refurbished unit", refurb, "tool_fleet class card", "refurbishment cost of the class"),
                _vl("c", "Logistics", 2 * log, t_ref, "there and back"),
                back_line,
                _vl("v", "Covered by the contract", D(0), c_ref),
            ],
        )

    # upgrade: BR-S1
    life = int(ln["life_used_pct"])
    if life < UPGRADE_LIFE and not cover["upgrade_allowed"]:
        up = _option(
            "upgrade", False, f"Upgrade is offered from {UPGRADE_LIFE}% of life used (BR-S1); this tool has used {life}%"
        )
    else:
        lp, pct = _d(terms[f"list_price.{cls}"]), _d(credit["credit_pct"])
        cr = min(pct * lp, _d(credit["credit_cap"]))
        pr = lp - cr
        m_up = pr - _d(terms["unit_cost_share"]) * lp - log + back
        p = _take_up(take, pct)
        exp = D(str(p)) * m_up + (1 - D(str(p))) * fix_m
        up = _option(
            "upgrade",
            True,
            f"{pct * 100:.0f}% credit on the new tool, capped at {_c(_d(credit['credit_cap']))}",
            customer_price=_f(pr),
            margin=_f(m_up),
            expected_margin=_f(exp),
            days=terms["upgrade_days"],
            take_up=p,
            credit=_f(cr),
            cost=_f(_d(terms["unit_cost_share"]) * lp),
            lines=[
                _vl("v", "Customer price", pr, t_ref, "list price less the credit"),
                _vl("c", "New unit cost", _d(terms["unit_cost_share"]) * lp, t_ref, "unit cost share x list price"),
                _vl("c", "Logistics", log, t_ref),
                _vl("c", "Credit", cr, credit["ref"], f"{pct * 100:.0f}% of list, capped"),
                back_line,
                _vl("v", "Expected take-up", D(str(p)), credit["ref"], "the share of customers who accept"),
            ],
        )
    return [fix, swap, up]


def _best(options: list[dict[str, Any]]) -> str | None:
    ok = [o for o in options if o["eligible"]]
    return max(ok, key=lambda o: (o["expected_margin"], -KEYS.index(o["k"])))["k"] if ok else None


def _case_option(k: str, lines: list[dict[str, Any]], of: str | None = None) -> dict[str, Any]:
    """The case's option `k`: the sum over the lines of the option `of` (default `k`), open only when open to every line."""
    of = of or k
    opts = [next(o for o in ln["options"] if o["k"] == of) for ln in lines]
    bad = next((o for o in opts if not o["eligible"]), None)
    if bad is not None:
        return _option(k, False, bad["why"])
    days = [o["days"] for o in opts if o["days"] is not None]
    return _option(
        k,
        True,
        opts[0]["why"] if len(opts) == 1 else f"{NAMES[of]} for all {len(opts)} tools",
        customer_price=_f(sum((_d(o["customer_price"]) for o in opts), D(0))),
        margin=_f(sum((_d(o["margin"]) for o in opts), D(0))),
        expected_margin=_f(sum((_d(o["expected_margin"]) for o in opts), D(0))),
        days=max(days) if days else None,
    )


def decide_ticket(inputs: Mapping[str, Any]) -> TicketDecision:
    """Per line the options and the best; per case the options summed over the lines (an option is open to the case only when
    it is open to every line) and the best of them. The holds are `approval_holds`' to give for the route finally chosen."""
    fx, take = _d(inputs["fx"]), inputs["take_up"]
    lines = []
    for ln in inputs["lines"]:
        opts = _line_options(ln, fx, take)
        lines.append(
            {
                "n": ln["n"],
                "serial": ln["serial"],
                "currency": inputs["currency"],
                "options": opts,
                "best": _best(opts),
                "draft": bool(ln.get("estimate")) and not ln["estimate"].get("auto"),
                "stale": sorted(set(ln.get("cited") or []) - set(inputs.get("approved") or [])),
            }
        )
    options = [_case_option(k, lines) for k in KEYS]
    return {
        "market": inputs["market"],
        "currency": inputs["currency"],
        "fx": float(fx),
        "take_up": dict(take),
        "lines": lines,
        "options": options,
        "best": _best(options),
    }


@dataclass(frozen=True)
class BatchDecision:
    """`lines` each decided alone (`decide_ticket`) with the stock shared in line order, so a line's `best` is its chosen
    option; `split` the lines per chosen option; `totals` the customer's price and the margins of the chosen options."""

    lines: list[dict[str, Any]]
    split: dict[str, int]
    totals: dict[str, Decimal]


def split_line(split: Mapping[str, int]) -> str:
    """ "Upgrade 9 · Fix 11 · Covered swap 2": the lines per chosen option, an option no line took left out."""
    return " · ".join(f"{label} {split[k]}" for k, label in SPLIT_LABELS if split.get(k))


def _allocate(d: TicketDecision, inputs: Mapping[str, Any]) -> BatchDecision:
    """Each line keeps what `decide_ticket` chose for it, except that swaps take the class's refurbished units in line order: a
    line that finds none left loses its swap (with the stated reason) and takes its next best option."""
    left: dict[str, int] = {}
    lines: list[dict[str, Any]] = []
    for ln, src in zip(d["lines"], inputs["lines"], strict=True):
        cls = str(src["model_class"])
        left.setdefault(cls, int(src["refurb_stock"]))
        if ln["best"] == "swap":
            if left[cls] < 1:
                options = [_option("swap", False, STOCK_USED) if o["k"] == "swap" else o for o in ln["options"]]
                ln = ln | {"options": options, "best": _best(options)}
            else:
                left[cls] -= 1
        lines.append(ln)
    chosen = [next(o for o in ln["options"] if o["k"] == ln["best"]) for ln in lines if ln["best"]]
    return BatchDecision(
        lines=lines,
        split={k: sum(1 for ln in lines if ln["best"] == k) for k, _ in SPLIT_LABELS},
        totals={k: sum((_d(o[k]) for o in chosen), D(0)).quantize(CENT, ROUND_HALF_UP)
                for k in ("customer_price", "margin", "expected_margin")},
    )  # fmt: skip


def decide_batch(inputs: Mapping[str, Any]) -> BatchDecision:
    """A batch decided per tool (module docstring, SD-07): the split and its totals."""
    return _allocate(decide_ticket(inputs), inputs)


def batch_ticket(inputs: Mapping[str, Any]) -> TicketDecision:
    """The batch as the ticket decision `decide_case` reads: the lines as `decide_batch` chose them, and the case's options
    `split` (the sum of the chosen options, the best) then `all_fix` and `all_upgrade` to compare, each open only when open to
    every line. `batch` holds what the page shows: the split, the totals and each line's chosen option with its reason."""
    d = decide_ticket(inputs)
    b = _allocate(d, inputs)
    unpriced = next((ln for ln in b.lines if ln["best"] is None), None)
    if unpriced is not None:
        split = _option("split", False, unpriced["options"][0]["why"])
    else:
        days = [o["days"] for ln in b.lines for o in ln["options"] if o["k"] == ln["best"] and o["days"] is not None]
        split = _option(
            "split", True, split_line(b.split),
            customer_price=_f(b.totals["customer_price"]), margin=_f(b.totals["margin"]),
            expected_margin=_f(b.totals["expected_margin"]), days=max(days) if days else None,
        )  # fmt: skip
    options = [split, *(_case_option(k, d["lines"], of) for k, of in COMPARE)]
    rows = []
    for ln in b.lines:
        o = next((x for x in ln["options"] if x["k"] == ln["best"]), None)
        rows.append({"n": ln["n"], "serial": ln["serial"], "k": ln["best"], "name": o["name"] if o else None,
                     "why": o["why"] if o else ln["options"][0]["why"]})  # fmt: skip
    return d | {
        "lines": b.lines,
        "options": options,
        "best": "split" if split["eligible"] else None,
        "batch": {"split": b.split, "totals": {k: float(v) for k, v in b.totals.items()}, "lines": rows},
    }


def approval_holds(d: Mapping[str, Any], route: str | None) -> list[dict[str, str]]:
    """What holds the recommendation for a person (I-10 reads `approvalHolds` as guardrail holds; the standing policy of I-11 may
    approve only a case with none): GR-S3 a price from a table that is not the current approved version, GR-S1 an estimate that
    is a draft, GR-14 a fix costing over $600, GR-C1 a credit over $300 (both converted at the case's rate)."""
    out: list[dict[str, str]] = []
    fx = _d(d["fx"])

    def hold(i: str, why: str) -> None:
        out.append({"id": i, "reason": why, "owner": OWNERS[i]})

    if any(ln["stale"] for ln in d["lines"]):
        hold("GR-S3", STALE)
    drafts = [ln["serial"] for ln in d["lines"] if ln["draft"]]
    if drafts:
        hold("GR-S1", f"The estimate of {', '.join(drafts)} is a draft: a technician checks it")
    for ln in d["lines"]:
        k = ln["best"] if route == "split" else dict(COMPARE).get(route or "", route)  # the option this line takes on the route
        o = next((x for x in ln["options"] if x["k"] == k), None)
        if o is None or not o["eligible"]:
            continue
        if k == "fix" and _d(o["cost"]) / fx > GR_14_USD:
            hold("GR-14", f"The repair of {ln['serial']} costs over ${GR_14_USD}: the fleet manager approves (GR-14)")
        if k == "upgrade" and _d(o["credit"]) / fx > GR_C1_USD:
            hold("GR-C1", f"The credit on {ln['serial']} is over ${GR_C1_USD}: sales approves (GR-C1)")
    return out


__all__ = [
    "KEYS", "NAMES", "STALE", "BatchDecision", "TicketDecision",
    "approval_holds", "batch_ticket", "decide_batch", "decide_ticket", "split_line",
]  # fmt: skip
