"""The test bench's read of a unit as evidence (plan 9, P9-10.7, stories TN-06 and TN-10).

    read(s, asset_key) -> dict | None   the bench's read of the unit (below), None when the bench has written nothing for it
    evidence(read) -> list              the `config_wipe` evidence record of that read ([] when the bench holds no wipe status)

The canonical `condition` record of the unit (key `schema.serial_key`) holds what the test bench (`tn_bench`) wrote
(`bench_passed`, `bench_total`, `firmware`, `wipe_*`). The case shows it as `case["bench"]`, every fact with its source and
age, and the configuration-wipe gate G-NET-CFG reads the wipe from the evidence record:

    bench   {source, passed, total, summary ("18 of 18 passed"), firmware, firmwareLatest,
             wipe {status, attempts, scope, certificate, verifiedAt, at}, facts [{fact, label, value, source, at, ageDays}]}
    config_wipe   {status, attempts, scope, certificate_ref, verified_at}, source `tn_bench`, result `pass` for a verified wipe
                  and `fail` for a failed one, at the time of the certificate (the bench's write when it has none)

A unit whose wipe status is `none` has no record: nothing is on file. Whether the wipe clears the unit (verified, the scope
holds configuration, credentials, keys and logs) is the gate's (`gate_checks.network`).

Never does: compute a pass (the bench's counts and wipe status are shown as it gave them; "18 of 18 passed" is its two numbers
side by side), decide a gate, write the store, or accept a certificate a person typed (the telecom case drops `compliance`
records of this type: `gate_hold.attach_evidence`).
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.modeler.evidence import parse_time
from di.services.modeler.gate_checks.network import WIPE

SOURCE = "tn_bench"


def _own(rec: dict[str, Any], field: str) -> tuple[Any, datetime | None]:
    """The value `tn_bench` wrote to the field and when, or (None, None)."""
    rows = [r for r in rec["provenance"].get(field) or [] if r["source_id"] == SOURCE]
    if not rows:
        return None, None
    row = max(rows, key=lambda r: r["fetched_at"])
    return row["value"], row["fetched_at"]


def _age_days(at: datetime) -> float:
    return round(max(0.0, (clock.now() - at).total_seconds()) / 86400, 1)


def _fact(name: str, label: str, value: Any, at: datetime | None) -> dict[str, Any]:
    return {
        "fact": name, "label": label, "value": value, "source": SOURCE,
        "at": at.isoformat() if at else None, "ageDays": _age_days(at) if at else None,
    }  # fmt: skip


def read(s: Session, asset_key: Any) -> dict[str, Any] | None:
    """The bench's read of the unit (module docstring); None when the bench has written nothing for it."""
    if not asset_key:
        return None
    rec = canonical.get(s, "condition", str(asset_key))
    if rec is None:
        return None
    got = {f: _own(rec, f) for f in rec["provenance"]}
    if not any(at for _, at in got.values()):
        return None

    def val(f: str) -> Any:
        return got.get(f, (None, None))[0]

    def at(f: str) -> datetime | None:
        return got.get(f, (None, None))[1]

    passed, total = val("bench_passed"), val("bench_total")
    summary = f"{passed} of {total} passed" if passed is not None and total is not None else None
    cert = val("wipe_certificate_ref")
    wiped_at = at("wipe_status")
    facts = []
    if summary:
        facts.append(_fact("bench_result", "Bench result", summary, max(filter(None, [at("bench_passed"), at("bench_total")]))))
    if val("firmware") is not None:
        facts.append(_fact("firmware", "Firmware", val("firmware"), at("firmware")))
    if cert:
        facts.append(_fact("wipe_certificate", "Wipe certificate", cert, at("wipe_certificate_ref")))
    return {
        "source": SOURCE, "passed": passed, "total": total, "summary": summary, "firmware": val("firmware"),
        "firmwareLatest": val("firmware_latest"),
        "wipe": {
            "status": val("wipe_status"), "attempts": val("wipe_attempts"), "scope": list(val("wipe_scope") or []),
            "certificate": cert, "verifiedAt": val("wipe_verified_at"),
            "at": wiped_at.isoformat() if wiped_at else None,
        },
        "facts": facts,
    }  # fmt: skip


def evidence(bench: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The `config_wipe` record of the bench's read (module docstring); [] when no wipe status is on file or it is `none`."""
    wipe = (bench or {}).get("wipe") or {}
    status = wipe.get("status")
    if status not in ("verified", "failed"):
        return []
    at = parse_time(wipe.get("verifiedAt")) or parse_time(wipe.get("at")) or clock.now()
    value = {
        "status": status, "attempts": wipe.get("attempts"), "scope": list(wipe.get("scope") or []),
        "certificate_ref": wipe.get("certificate"), "verified_at": wipe.get("verifiedAt"),
    }  # fmt: skip
    return [
        {
            "type": WIPE,
            "source": SOURCE,
            "at": at.isoformat(),
            "result": "pass" if status == "verified" else "fail",
            "value": value,
        }
    ]
