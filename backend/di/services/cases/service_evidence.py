"""The biomedical service record of a rental device as evidence (plan 9, P9-11.7, stories MR-06, MR-07 and MR-15).

    evidence(s, case)   (records, keys): the evidence records of the device's service and field safety notice status, and the
                        case keys they come with

The canonical `condition` record of the device (key `schema.tag_key`) holds what the biomedical service system (`mr_biomed`)
wrote: `certification_expiry`, `pm_due`, `functional_test`, `electrical_safety`, `notes`, `correction_open`, `correction_ref`;
`servicing_assessment` (the refurbishment assessment: G-MED-REFURB evidence);
the `demand` record holds the open requests (`rental_requests`, the rental system), the `asset` record the device class. They
become:

    service_record        {certification_expiry, pm_due, pm_code, functional_test, electrical_safety, notes}, at the time the
                          system wrote the dates; result `fail` when the functional test or the electrical safety test failed
    field_safety_status   {notice_id, correction_ref}, result `fail` while a notice that covers the device is open, else `pass`;
                          a later `field_safety_status` compliance record (the correction record) makes the unit eligible again
    keys:
      rentalRequests      the requests for the device's class, each {req_id, hospital_id, hospital, start_date, days, ends,
                          distance_miles, requested_at}: `hospital` is the label the rental system gave (else the id) and
                          `distance_miles` the whole miles from the device's depot, which the valuer prices the transport with
                          (P9-11.9: both were dropped before, so a real case valued every request at 0 miles)
      serviceRead         what the service system says, each with its source and age (MR-07): the two test results, the notes
                          (a cosmetic note is shown, never read as a failure), the dates
      serviceCheck        {requests: [{req_id, ends, ok, reason, recommendation}], proposed}: the service gate's result per
                          request (`gate_checks.medical.request_checks`), "Send a different unit: <tag>" naming an in-date
                          unit of the class, and the `service.book` the gate proposes for this one (a person books it)

Never does: decide a gate (`gate_checks.medical`), write the store, book anything or clear a hold. Wording of both gates needs
review by Kinective's Legal team before it is relied on (42 CFR 482.41, CMS S&C 14-07, IEC 62353:2014, 21 CFR Part 7 and 806).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.modeler.gate_checks import medical

SOURCE = "mr_biomed"
SERVICE_FIELDS = ("certification_expiry", "pm_due", "pm_code", "functional_test", "electrical_safety", "notes")
ALTERNATIVES = 3  # in-date units named in a recommendation


def _newest(cond: dict[str, Any], *fields: str) -> tuple[str, Any]:
    """The source and time of the newest write among the fields of the canonical record."""
    rows = [r for f in fields for r in (cond.get("provenance") or {}).get(f) or []]
    if not rows:
        return "", None
    best = max(rows, key=lambda r: r["fetched_at"])
    return str(best["source_id"] or ""), best["fetched_at"]


def _requests(s: Session, asset_key: str, device_class: Any) -> list[dict[str, Any]]:
    rec = canonical.get(s, "demand", asset_key)
    rows = ((rec or {}).get("data") or {}).get("rental_requests") or []
    out = []
    for q in rows:
        if device_class and q.get("device_class") not in (None, device_class):
            continue
        ends = medical.rental_end(q.get("start_date"), q.get("days"))
        if ends is not None:
            out.append({"req_id": q.get("req_id"), "hospital_id": q.get("hospital_id"),
                        "hospital": q.get("hospital") or q.get("hospital_id"), "start_date": q.get("start_date"),
                        "days": q.get("days"), "ends": ends.isoformat(), "distance_miles": q.get("distance_miles"),
                        "requested_at": q.get("requested_at")})  # fmt: skip
    return out


def _alternatives(s: Session, asset_key: str, device_class: Any) -> list[tuple[str, dict[str, Any]]]:
    """The other units of the device's class (same org unit) with their service facts, by tag."""
    if not device_class:
        return []
    org = asset_key.split(":", 1)[0]
    rows = s.execute(
        text(
            "SELECT c.key, c.data FROM canonical c JOIN canonical a ON a.model = 'asset' AND a.key = c.key "
            "WHERE c.model = 'condition' AND c.key LIKE :p AND c.key <> :k AND a.data ->> 'device_class' = :d ORDER BY c.key"
        ),
        {"p": org + ":%", "k": asset_key, "d": device_class},
    ).all()
    return [(str(k).split(":", 1)[1], d) for k, d in rows]


def evidence(s: Session, case: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The records and case keys of the module docstring; ([], {}) for a device the service system has no record of."""
    key = case.get("assetId")
    if not key:
        return [], {}
    cond = canonical.get(s, "condition", str(key))
    data = (cond or {}).get("data") or {}
    if cond is None or not any(data.get(f) is not None for f in (*SERVICE_FIELDS, "correction_open", "servicing_assessment")):
        return [], {}
    asset = ((canonical.get(s, "asset", str(key)) or {}).get("data")) or {}
    recs: list[dict[str, Any]] = []
    keys: dict[str, Any] = {}
    if any(data.get(f) is not None for f in SERVICE_FIELDS):
        src, at = _newest(cond, *SERVICE_FIELDS)
        failed = [t for t in ("functional_test", "electrical_safety") if str((data.get(t) or {}).get("result")) == "fail"]
        value = {f: data.get(f) for f in SERVICE_FIELDS} | {"failed": failed}
        if at is not None:
            recs.append({"type": "service_record", "source": src or SOURCE, "at": at.isoformat(),
                         "result": "fail" if failed else "pass", "value": value})  # fmt: skip
            keys["serviceRead"] = {
                "source": src or SOURCE, "at": at.isoformat(),
                "ageDays": round(max(0.0, (clock.now() - at).total_seconds()) / 86400, 1),
                "functionalTest": data.get("functional_test"), "electricalSafety": data.get("electrical_safety"),
                "notes": data.get("notes") or [], "certificationExpiry": data.get("certification_expiry"),
                "pmDue": data.get("pm_due"), "pmCode": data.get("pm_code"),
            }  # fmt: skip
    if data.get("correction_open") is not None:
        src, at = _newest(cond, "correction_open")
        notice = ((cond.get("provenance") or {}).get("correction_open") or [{}])[0].get("source_value")
        if at is not None:
            recs.append({
                "type": "field_safety_status", "source": src or SOURCE, "at": at.isoformat(),
                "result": "fail" if data.get("correction_open") else "pass",
                "value": {"notice_id": notice if isinstance(notice, str) else None, "correction_ref": data.get("correction_ref")},
            })  # fmt: skip
    if data.get("servicing_assessment") is not None:  # servicing, remanufacturing or full_refurbishment (P9-11.10)
        src, at = _newest(cond, "servicing_assessment")
        if at is not None:
            recs.append({"type": "servicing_assessment", "source": src or SOURCE, "at": at.isoformat(),
                         "result": "fail" if data["servicing_assessment"] in medical.FULL else "pass",
                         "value": {"assessment": data["servicing_assessment"]}})  # fmt: skip
    reqs = _requests(s, str(key), asset.get("device_class"))
    keys["rentalRequests"] = reqs
    checks = medical.request_checks(data, reqs)
    if any(not c["ok"] for c in checks):
        units = _alternatives(s, str(key), asset.get("device_class"))
        for c in checks:
            if not c["ok"]:
                c["recommendation"] = medical.recommend_other_unit(units, c["ends"])
    keys["serviceCheck"] = {"requests": checks, "proposed": medical.proposal(case, checks)}
    return recs, keys
