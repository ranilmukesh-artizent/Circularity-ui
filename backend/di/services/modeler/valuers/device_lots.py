"""Wholesale lots of received devices and the bid they are sold to (plan 9, P9-6.11, story DV-07; the approved buyers are a
market table, I-15; the approval is a person's or the standing policy's, I-11). Pure: no session, no I/O.

    build_lots(devices, cap) -> list[LotDraft]     devices routed to `wholesale`, grouped by (model, grade), split into lots of at
                                                    most `cap` units (GR-D4), the oldest received first
    rank_bids(bids, approved) -> Ranking           the approved bids ranked by net a unit, the dropped ones with reasons (GR-D12)
    best_bid(bids, approved) -> Bid | None         the best approved bid by net, or None
    lot_value(net, units) -> float                 what the lot is worth: net a unit times units, in cents
    over_limit(value, limit) -> bool               above GR-D10's limit a person decides; at or under it the policy may approve

A bid's net is `amount - fees - logistics` a unit. A bid from a buyer that is not in the approved set is never chosen, whatever
it bids (the approved set is the market table `approved_buyers`; the buyer who bids the most gross can be the unverified one).
Ties on net go to the earlier bid id, so the same bids always give the same answer.
Never does: accept or sell a lot (a person approves, `lot.approve`), read the table or the database, or write language: the
figures are computed and the texts are fixed wording over them, so there is no model call (R16).
"""

from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from di.services.modeler.pack import Pack

LIMIT_GUARD, LIMIT_FIELD, DEFAULT_LIMIT = "GR-D10", "max_value_usd", 25000.0
BUYERS_GUARD = "GR-D12"
NOT_APPROVED = "Buyer {code} is not an approved wholesale buyer"
OWNER = "Commercial manager"  # the owner label of GR-D10 (role Approver)
ROLE = "Approver"


@dataclass(frozen=True)
class LotCandidate:
    """A device (or a bulk line of `units`) routed to wholesale: its case, model and grade, and when it was received."""

    case_id: str
    model: str
    grade: str
    received_at: datetime
    units: int = 1


@dataclass(frozen=True)
class LotDraft:
    model: str
    grade: str
    units: int
    case_ids: tuple[str, ...]


@dataclass(frozen=True)
class Bid:
    """A buyer's bid on a lot: the amount a unit, with the fees and logistics a unit that come off it."""

    bid_id: str
    buyer_code: str
    amount: float
    fees: float
    logistics: float

    @property
    def net(self) -> float:
        return round(self.amount - self.fees - self.logistics, 2)


@dataclass(frozen=True)
class Dropped:
    bid_id: str
    buyer_code: str
    reason: str


@dataclass(frozen=True)
class Ranking:
    ranked: tuple[Bid, ...]  # the approved bids, best net first
    dropped: tuple[Dropped, ...]

    @property
    def best(self) -> Bid | None:
        return self.ranked[0] if self.ranked else None


def build_lots(devices: Sequence[LotCandidate], cap: int) -> list[LotDraft]:
    """The lots: one group per (model, grade), oldest received first, filled to `cap` units and then the next lot. A model never
    mixes with another, nor a grade. A line larger than `cap` units is its own lot (it cannot be split)."""
    if cap < 1:
        raise ValueError("A lot holds at least one unit.")
    groups: dict[tuple[str, str], list[LotCandidate]] = defaultdict(list)
    for d in devices:
        groups[(d.model, d.grade)].append(d)
    out: list[LotDraft] = []
    for (model, grade), members in sorted(groups.items()):
        members.sort(key=lambda d: (d.received_at, d.case_id))
        ids: list[str] = []
        units = 0
        for d in members:
            if ids and units + d.units > cap:
                out.append(LotDraft(model, grade, units, tuple(ids)))
                ids, units = [], 0
            ids.append(d.case_id)
            units += d.units
        if ids:
            out.append(LotDraft(model, grade, units, tuple(ids)))
    return out


def rank_bids(bids: Sequence[Bid], approved: Collection[str]) -> Ranking:
    """The approved bids by net a unit, best first, and the bids of buyers not in `approved`, each with its reason (GR-D12)."""
    ok = sorted((b for b in bids if b.buyer_code in approved), key=lambda b: (-b.net, b.bid_id))
    dropped = tuple(
        Dropped(b.bid_id, b.buyer_code, NOT_APPROVED.format(code=b.buyer_code)) for b in bids if b.buyer_code not in approved
    )
    return Ranking(tuple(ok), dropped)


def best_bid(bids: Sequence[Bid], approved: Collection[str]) -> Bid | None:
    return rank_bids(bids, approved).best


def lot_value(net: float, units: int) -> float:
    return round(net * units, 2)


def over_limit(value: float, limit: float) -> bool:
    return value > limit


def value_limit(pack: "Pack") -> float:
    """GR-D10's limit: a lot worth more than this waits for the Commercial manager (a customer's overlay may only lower it)."""
    g = next((x for x in pack.guardrails if x.id == LIMIT_GUARD), None)
    return float(g.param.value) if g is not None and g.param is not None else DEFAULT_LIMIT


def lot_cap(pack: "Pack") -> int:
    """GR-D4's lot size: the most units a wholesale lot holds (`dcfg.wholesale.lot` of the pack)."""
    return int(pack.valuer.params["dcfg"]["wholesale"]["lot"])


def usd(v: float) -> str:
    """ "$310" for a whole amount, "$310.50" otherwise."""
    r = round(v, 2)
    return f"${r:,.0f}" if r == int(r) else f"${r:,.2f}"
