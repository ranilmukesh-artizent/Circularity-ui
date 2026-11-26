"""The follow-through steps of a medical rental route (plan 9, P9-11.17; stories MR-19 and MR-23). Pure.

    follow_steps(route_id, pack, facts) -> list[str]   the step kinds sent after the route is approved

The steps are the pack's route `instructions` (part 5): re-rent `dispatch`; service then re-rent `service_order`, `dispatch`;
refurbish `biomed_refurb`; retire `data_sanitisation` (only for a class with patient data, G-DATA-3), `disposal_collection`,
`write_off`. A re-rent route id carries its request (`rerent:REQ-2`); the pack's route is the part before the colon. `write_off`
is not a step of the plan: it is a posting for Finance, prepared by the close (`di.services.cases.close_medical_rental`) and held
for a person. `decide_case` sets the list on each route as `steps`, and the execution plan
(`di.services.execution.steps.ex_kinds`) reads it. The writers are in `di.services.instructions.writers`.

Never does: read a session or the clock, send anything, or approve.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.pack import Pack

SANITISATION = "data_sanitisation"
WRITE_OFF = "write_off"


def patient_data(pack: Pack, facts: Mapping[str, Any]) -> bool:
    """The device's class holds patient data (the pack's `classes[].attrs.patient_data`)."""
    cls = next((c for c in pack.classes if c.id == facts.get("cls")), None)
    return bool(cls is not None and cls.attrs.patient_data)


def follow_steps(route_id: str, pack: Pack, facts: Mapping[str, Any]) -> list[str]:
    """The step kinds of the route `route_id` for the device (module docstring); none for an id the pack does not have."""
    route = next((r for r in pack.routes if r.id == route_id.split(":", 1)[0]), None)
    if route is None:
        return []
    return [k for k in route.instructions if k != WRITE_OFF and (k != SANITISATION or patient_data(pack, facts))]
