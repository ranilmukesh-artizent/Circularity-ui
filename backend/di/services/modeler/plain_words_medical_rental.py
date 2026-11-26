"""What a plain-words guardrail of the medical rental pack may name (plan 9, P9-11.14, story MR-11; `plain_guardrail.Vocab`).

The routes by the words a rental fleet director uses, the age of a device as the asset system serves it (`asset.age_years`,
years from the in-service date) and the words of the work item a retirement approval opens. "Retiring a device younger
than 5 years needs approval from clinical engineering" becomes the guardrail `AP-MR-RETIRE5`: the retire route,
`asset.age_years < 5`, approved by `clinical_engineering` (a role of the pack). The roles are the pack's; nothing else is
named here. Compliance wording the pack holds is reviewed by Kinective's Legal team before it is relied on.

`history_items` adapts the sample history's items (their facts are text under short names) to what `plain_guardrail.would_change`
reads (the route taken, the facts as flat dotted numbers).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.plain_guardrail import RangeWords, Vocab

AGE = "asset.age_years"


def _ident(route: str, codes: list[str]) -> str:
    return f"AP-MR-{route.upper()}{''.join(codes)}"  # AP-MR-RETIRE5


VOCAB = Vocab(
    id_prefix="AP-MR",
    routes={
        "retire": ("retire", "retiring", "retired", "retirement"),
        "refurbish": ("refurbish", "refurbishing", "refurbished", "refurbishment"),
        "service_rerent": ("service", "servicing"),
        "rerent": ("rerent", "re rent", "re renting", "rerenting"),
    },
    facts=(),
    action="Retire and harvest when repair exceeds residual value",
    default_route="rerent",
    ranges=(
        RangeWords(AGE, below=("younger than", "under", "less than"), above=("older than", "over", "more than"), unit="years?"),
    ),
    ident=_ident,
)


def history_items(items: Sequence[Mapping[str, Any]]) -> list[tuple[str | None, dict[str, Any]]]:
    """The history's items as (the route taken, `asset.age_years` as a number), for `plain_guardrail.would_change`."""
    out: list[tuple[str | None, dict[str, Any]]] = []
    for it in items:
        raw = (it.get("facts") or {}).get("age_years")
        raw = raw.get("value") if isinstance(raw, Mapping) else raw
        try:
            age = float(str(raw))
        except ValueError:
            continue
        out.append((it.get("actual_route"), {AGE: age}))
    return out
