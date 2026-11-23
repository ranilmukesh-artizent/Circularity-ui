"""Scope facts a case does not hold itself but rules may be scoped on (plan 8, MVP-7.1; story G, edge cases 11-13).

`alarm` (industrial dim, "yes" or "no"): whether the asset's latest condition-monitoring telemetry is at an alarm
threshold of the kit (source-sim's AWS IoT Core mock raises one when vibration reaches 7.1 mm/s, ISO 10816-3 zone D, or
the bearing reaches 90 °C; docs/backend-steps.md, B5c). The telemetry is the canonical `condition` record the iot
adapter writes (di.connectors.adapters.aws_iot: `vibration_mm_s`, `bearing_temp_c`). With no telemetry the case has
no `alarm`, so a rule scoped on it does not match.
"""

from collections.abc import Mapping
from typing import Any

VIBRATION_ALARM_MM_S = 7.1
BEARING_ALARM_C = 90.0
TELEMETRY_FIELDS = ("vibration_mm_s", "bearing_temp_c")
FACT_KEYS = ("alarm",)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def case_scope_facts(case: Mapping[str, Any], telemetry: Mapping[str, Any] | None) -> dict[str, Any]:
    """The case with its scope facts from `telemetry` (a new dict; any earlier facts are replaced)."""
    out = {k: v for k, v in case.items() if k not in FACT_KEYS}
    vib, temp = (_num((telemetry or {}).get(f)) for f in TELEMETRY_FIELDS)
    if vib is None and temp is None:
        return out
    alarm = (vib is not None and vib >= VIBRATION_ALARM_MM_S) or (temp is not None and temp >= BEARING_ALARM_C)
    out["alarm"] = "yes" if alarm else "no"
    return out
