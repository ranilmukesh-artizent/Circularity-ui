"""What a plain-words guardrail of the telecom network pack may name (plan 9, P9-10.14, story TN-14; `plain_guardrail.Vocab`).

The routes by the words a planner uses, the generation of a model as the catalogue serves it (`market.generation`, written by the
spares planning adapter: `current` or `previous`), and the words of the work item a resale approval opens (the research table:
"Resell what the forecast doesn't need; keep the rest as regional spares"). The roles are the pack's; nothing else is named here.
"""

from di.services.modeler.plain_guardrail import FactWords, ValueWords, Vocab

VOCAB = Vocab(
    id_prefix="AP-TN",
    routes={
        "resell": ("resale", "resell", "resold", "selling", "sale"),
        "spare": ("spares",),
        "harvest": ("harvest", "harvesting"),
        "recycle": ("recycle", "recycling"),
        "redeploy": ("redeploy", "redeployment"),
    },
    facts=(
        FactWords(
            "market.generation",
            "generation",
            {"current": ValueWords("current", "CURGEN"), "previous": ValueWords("previous", "PREGEN")},
        ),
    ),  # fmt: skip
    action="Resell what the forecast doesn't need; keep the rest as regional spares",
    default_route="resell",
)
