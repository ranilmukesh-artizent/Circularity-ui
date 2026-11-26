"""The follow-through steps of a used-car channel (plan 9, P9-9.17; stories UC-18 and UC-25). Pure.

    follow_steps(route_id, pack, facts) -> list[str]   the step kinds sent after the channel is approved

The steps are the pack's route `instructions` (part 5): retail `recon_order`, `lot_transfer`, `listing`; auction `consignment`;
dealer trade `dealer_trade`; salvage `salvage_sale`. A retail route id carries its lot (`retail:LOT-S`); the pack's route is the
part before the colon. `infotainment_reset` ("Reset infotainment and remove paired devices", UC-25) is listed first on every
channel, and it applies only to a car whose inspection found paired devices (`condition.paired_devices` is true): a person's
checklist step with no system write. The other kinds go to the dealer system (`uc_dms`) or the auction platform (`uc_auction`)
through the writers of `di.services.instructions.writers`; `decide_case` sets the list on each route as `steps`, and the
execution plan (`di.services.execution.steps.ex_kinds`) reads it.

Never does: read a session or the clock, send anything, or approve. Whether a duty to reset the infotainment exists in the US is
unconfirmed (the GDPR Art. 32 reading is ours); the step's wording needs review by Kinective's Legal team before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.pack import Pack

RESET = "infotainment_reset"


def paired_devices(facts: Mapping[str, Any]) -> bool:
    """The inspection found paired phones or stored addresses in the car."""
    condition = facts.get("condition")
    return isinstance(condition, Mapping) and condition.get("paired_devices") is True


def follow_steps(route_id: str, pack: Pack, facts: Mapping[str, Any]) -> list[str]:
    """The step kinds of the channel `route_id` for the car (module docstring); none for an id the pack does not have."""
    route = next((r for r in pack.routes if r.id == route_id.split(":", 1)[0]), None)
    if route is None:
        return []
    kinds = [k for k in route.instructions if k != RESET]
    if RESET in route.instructions and paired_devices(facts):
        kinds.insert(0, RESET)
    return kinds
