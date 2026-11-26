"""What a plain-words guardrail of the used-car pack may name (plan 9, P9-9.16, story UC-13; `plain_guardrail.Vocab`).

The routes by the words a remarketing team uses, the odometer reading as the lease system serves it (`asset.mileage_at_return`,
a number bounded by "fewer than 40,000 miles") and the words of the work item an approval opens. "Any car sent to auction with
fewer than 40,000 miles needs approval from the remarketing manager" becomes the guardrail `AP-UC-AUCTION40K`: the auction route,
`asset.mileage_at_return < 40000`, approved by `remarketing_manager` (a role of the pack). The roles are the pack's; nothing else
is named here. A per-lot retail route (`retail:LOT-C`) is the pack's `retail` route.

`history_items` adapts the sample history's cars (route taken, flat dotted facts) to what `plain_guardrail.would_change` reads.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.plain_guardrail import RangeWords, Vocab

MILES = "asset.mileage_at_return"


def _ident(route: str, codes: list[str]) -> str:
    thousands = "".join(f"{int(float(c)) // 1000}K" for c in codes)
    return f"AP-UC-{route.upper()}{thousands}"  # AP-UC-AUCTION40K


VOCAB = Vocab(
    id_prefix="AP-UC",
    routes={
        "auction": ("auction", "auctions", "wholesale auction"),
        "retail": ("retail", "retailed", "retailing"),
        "dealer_trade": ("dealer trade", "dealer trades", "trade to a dealer"),
        "salvage": ("salvage", "salvaged"),
    },
    facts=(),
    action="Auction when retail days-to-sale is far above average at every lot",
    default_route="retail",
    ranges=(
        RangeWords(
            MILES, below=("fewer than", "less than", "under", "below"), above=("more than", "over", "above"), unit="miles"
        ),
    ),
    ident=_ident,
)


def history_items(cars: Sequence[Mapping[str, Any]]) -> list[tuple[str | None, dict[str, Any]]]:
    """The history's cars as (the route taken, `asset.mileage_at_return`), for `plain_guardrail.would_change`."""
    return [(c.get("actual_route"), {MILES: float(c[MILES])}) for c in cars if c.get(MILES) is not None]
