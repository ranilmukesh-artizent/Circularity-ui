"""The facts a medical rental device's customer diversions read (plan 9, P9-11.12, stories MR-12 and MR-13).

    facts(s, case) -> {"asset": {...}, "demand": {...}}      {} for a device with no asset record

    asset.ward_type                      the ward type the device came back from (the rental system's `wardType`, e.g. isolation)
    asset.hospital                       the hospital it came back from
    asset.age_years                      the years in service the asset system gives (a customer approval's "younger than 5
                                         years", P9-11.14)
    demand.same_hospital_within_24h      the hospital it came back from has asked again within 24 hours: two of its requests (the
                                         case's `rentalRequests`) are at most 24 hours apart

A diversion's `when` conditions (`DV-MR-ISO`: `asset.ward_type eq isolation`; `DV-MR-SAME`: `demand.same_hospital_within_24h eq
true`) read them as facts of the case; `gate_hold.attach_evidence` sets them on a `medical_rental` case. Never does: decide a
route, write the store or run a diversion (`decide_case` does).
"""

from collections.abc import Mapping
from itertools import pairwise
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.evidence import parse_time

WINDOW_SECONDS = 24 * 3600


def same_hospital_again(hospital: Any, requests: list[dict[str, Any]]) -> bool:
    """Two requests of the hospital are at most 24 hours apart (a request with no readable time is not counted)."""
    times = sorted(
        t for q in requests if q.get("hospital_id") == hospital and (t := parse_time(q.get("requested_at"))) is not None
    )
    return bool(hospital) and any((b - a).total_seconds() <= WINDOW_SECONDS for a, b in pairwise(times))


def facts(s: Session, case: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    asset = ((canonical.get(s, "asset", str(case.get("assetId") or "")) or {}).get("data")) or {}
    if not asset:
        return {}
    hospital = asset.get("hospital")
    return {
        "asset": {"ward_type": asset.get("ward_type"), "hospital": hospital, "age_years": asset.get("age_years")},
        "demand": {"same_hospital_within_24h": same_hospital_again(hospital, list(case.get("rentalRequests") or []))},
    }
