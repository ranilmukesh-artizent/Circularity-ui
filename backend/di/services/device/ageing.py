"""Ageing suggestions from live listings (plan 9, P9-6.13, story DV-08).

Owns: `suggest` (pure: live listings, the customer's days, the day -> the moves worth a rule) and its Session wrapper
`suggestions_for` (the listings of a flow's org, the pack's settings). A listing on Offers with no offer for
`offers_to_auction_days` (14; 7, 10 or 21 by choice) is suggested a move to Auction; one on Buy Now unsold for
`buynow_to_offers_days` (21) a move to Offers. Each suggestion names its listings, their total value and the draft rule
`{action: "require", path, scope: {listChannel, listDaysMin[, offersMax: 0]}}`, ordered oldest age band first, then by value.
The rule is the customer's policy, not an industry one (a Buy Now listing is still excluded at 45 days on hand by DR-01).
Never does: save a rule or a draft (accepting is the person's own `flow.saveDraft`, approved by someone else), approve
anything, or use a language model: every count and sum comes from the listing rows (R16: no figure by a model).
Implements the suggestion half of registry entry I-4 (rules that run); the action is `device.ageingSuggestions`
(`di.services.actions.device_learning`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from di.core.orgs import subtree
from di.repositories import device_market, orgs
from di.repositories.device_market import ListingRow
from di.services.modeler.pack import load_pack

OFFERS, BUYNOW, AUCTION = "offers", "buynow", "auction"


@dataclass(frozen=True)
class Settings:
    """The days after which a listing is suggested the next channel."""

    offers_to_auction_days: int = 14
    buynow_to_offers_days: int = 21


@dataclass(frozen=True)
class AgeingSuggestion:
    kind: str  # "offers_to_auction" or "buynow_to_offers"
    frm: str  # the channel the listings are on
    to: str  # the channel suggested
    days: int  # the age band: the days listed that the rule asks for
    n: int
    value: float  # the listings' asking prices, summed
    listings: tuple[str, ...]
    text: str
    rule: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "from": self.frm, "to": self.to, "days": self.days, "n": self.n, "value": self.value,
            "listings": list(self.listings), "text": self.text, "rule": self.rule,
        }  # fmt: skip


def choices() -> tuple[int, ...]:
    """The days a person may choose for the Offers move (the pack's `ageing.offers_choices`)."""
    return tuple(int(x) for x in load_pack("device").valuer.params["ageing"]["offers_choices"])


def settings(offers_days: int | None = None) -> Settings:
    """The pack's defaults; `offers_days` (one of `choices()`) replaces the Offers move's days."""
    p = load_pack("device").valuer.params["ageing"]
    return Settings(int(offers_days or p["offers_to_auction_days"]), int(p["buynow_to_offers_days"]))


def _channel(row: ListingRow) -> str:
    names = {str(v).lower(): k for k, v in load_pack("device").valuer.params["dcn"].items()}
    return names.get(row.channel.lower(), row.channel.lower())


def _days(row: ListingRow, as_of: date) -> int:
    return max(0, (as_of - row.listed_at.date()).days)


def _name(channel: str) -> str:
    return str(load_pack("device").valuer.params["dcn"][channel])


def suggest(listings: Sequence[ListingRow], cfg: Settings, as_of: date) -> list[AgeingSuggestion]:
    """The moves for the live `listings` as of `as_of`, oldest age band first, then the larger value first."""
    live = [x for x in listings if x.status == "live"]
    out: list[AgeingSuggestion] = []
    moves = (
        ("offers_to_auction", OFFERS, AUCTION, cfg.offers_to_auction_days, ", no offer"),
        ("buynow_to_offers", BUYNOW, OFFERS, cfg.buynow_to_offers_days, " unsold"),
    )
    for kind, frm, to, days, why in moves:
        hit = [
            x for x in live
            if _channel(x) == frm and _days(x, as_of) >= days and (frm != OFFERS or x.offers == 0)
        ]  # fmt: skip
        if not hit:
            continue
        scope: dict[str, Any] = {"listChannel": [frm], "listDaysMin": days} | ({"offersMax": 0} if frm == OFFERS else {})
        what = "listing" if len(hit) == 1 else "listings"
        out.append(
            AgeingSuggestion(
                kind, frm, to, days, len(hit), round(sum(x.price for x in hit), 2), tuple(x.listing_id for x in hit),
                f"Move {len(hit)} {_name(frm)} {what} to {_name(to)}: {days} days{why}",
                {"action": "require", "path": to, "scope": scope},
            )
        )  # fmt: skip
    return sorted(out, key=lambda x: (-x.days, -x.value, x.kind))


def live_of_org(s: Session, org_unit_id: str, as_of: date) -> list[ListingRow]:
    """The live listings of the org unit and the units under it (a listing with no org unit is shared and left out)."""
    mine = subtree(orgs.units(s), org_unit_id)
    return [x for x in device_market.live_listings(s, as_of) if x.org_unit_id in mine]


def suggestions_for(
    s: Session, org_unit_id: str, as_of: date, offers_days: int | None = None, visible: Sequence[str] | None = None
) -> list[AgeingSuggestion]:
    """`suggest` over the org's live listings; `visible` (org units the person may see) narrows them when given."""
    rows = [x for x in live_of_org(s, org_unit_id, as_of) if visible is None or x.org_unit_id in visible]
    return suggest(rows, settings(offers_days), as_of)


def reevaluate_listed(s: Session, as_of: date, agent: str) -> dict[str, str]:
    """The daily job (`device.ageing`, once per simulated day): each listed device whose case waits for re-evaluation is valued
    again through `case.reevaluate` as the valuation stage agent `agent`, so the days it has been listed reach its scope. The
    pipeline's hold policy judges the call (an unconfirmed agent write is held for a person where the policy says so); nothing
    here approves, declines or publishes. Answers the outcome per case id: "done", "held" or the refusal's code."""
    from di.services.actions.pipeline import SYSTEM, CallContext, invoke  # lazily: the pipeline imports the devices
    from di.services.agents.stage_context import StageContext
    from di.services.cases import store

    out: dict[str, str] = {}
    for row in device_market.live_listings(s, as_of):
        case = store.get(s, row.case_id) if row.case_id and row.case_id not in out else None
        if case is None or case.get("stage") != "reeval":
            continue
        stage = StageContext("valuation", "limits", None, 0.0, None, None, None)
        r = invoke("case.reevaluate", {"case_id": row.case_id}, CallContext(actor=SYSTEM, session=s, preparer=agent, stage=stage))
        held = r.get("ok") and "held" in (r.get("output") or {})
        out[str(row.case_id)] = "held" if held else "done" if r.get("ok") else str((r.get("error") or {}).get("code", "refused"))
    return out
