"""Registers the worked analytics questions of every pack (plan 9; P9-6.17 DV-13, P9-9.19, P9-10.17, P9-11.16).

The questions live in code, not in the pack JSON (the pack schema forbids extra fields; decision 26 Nov 2026): each pack
has one module here (`used_cars`, `telecom_network`, `medical_rental`) that calls `di.services.device.analytics.register`;
the device pack's own questions are in `di.services.device.analytics`. Importing this package imports them all, so
`analytics.REGISTRY` holds every pack's questions. Outside the case-store layer, so a question may read repositories.
Writes nothing.
"""

from di.services.cases import mr_turnaround as _mt
from di.services.device import analytics
from di.services.questions import device as device_headline
from di.services.questions import medical_rental, telecom_network, tool_fleet, used_cars  # noqa: F401
from di.services.questions.headline import Spec

#: The worked questions of each pack that has any (ids in `analytics.REGISTRY`); the Packs tab lists the selected pack's own.
PACK_QUESTIONS: dict[str, tuple[str, ...]] = {
    "device": ("price_after_launch", "disputes_by_partner"),
    "used_cars": ("wq_uc_1", "wq_uc_2"),
    "telecom_network": ("wq_tn_1", "wq_tn_2"),
    "medical_rental": (_mt.QUESTION_ID, "retired_earliest"),
}


#: The packs whose Analytics opens on a headline (plan 11, D1): the figures of each, from `di.services.questions.headline`.
HEADLINES: dict[str, Spec] = {tool_fleet.SPEC.key: tool_fleet.SPEC, device_headline.SPEC.key: device_headline.SPEC}


def worked_questions(pack_key: str) -> list[dict[str, str]]:
    """[{id, question}] of the pack's worked questions, in order; empty for a pack with none."""
    return [
        {"id": i, "question": analytics.REGISTRY[i].question} for i in PACK_QUESTIONS.get(pack_key, ()) if i in analytics.REGISTRY
    ]
