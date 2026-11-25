"""The data-wipe certificate gate for a received device (plan 9, P9-6.7, story DV-04; gate G-DEV-WIPE of the catalogue, I-2, and
its batch hold and automatic release, `cases/gate_hold.py`).

    certificate_view(cond) -> dict                the lab's certificate of a device: state, the certificate and what it lacks
    refresh(s, case)                              the case's certificate from the canonical `condition`, kept on its snapshot
                                                  (`valuer.inputs.wipe`) on every valuation
    released_line(case) -> str | None             the journal line of a release: "Released: wipe certificate <id> arrived"
    view(s, case) -> dict | None                  the case page's `wipe` block (the certificate, the batch's waiting count)
    gate_check(case, pack, gate) -> GateResult | None   the check of G-DEV-WIPE (guardrail GR-D1), registered in CHECKS

The lab (dvlab, synthetic) writes `condition.wipe_certificate` {certificate_id, method, tool_version, verification, operator,
at}. States: `none` (no certificate, or one lacking `method`, `tool_version`, `verification` or `operator`, or one whose
verification is neither pass nor fail) fails every channel but recycle with "No data-wipe certificate (GR-D1): listing blocked"
and holds the case until a certificate arrives (the cases of one batch that wait are held as one batch: `gateHold.batch`);
`failed` (verification fail) keeps the channels blocked and held (the re-run's certificate releases the case) and adds the step
"Wipe verification failed: re-run the wipe or destroy the storage" (X-07); `ok` lets the case go on. A certificate written to
the canonical store queues `case.gateRecheck` (`canonical.store.apply`), which releases each case on its own with a journal
row by `system`. Only a received device (`valuer.imei`) is checked here (the pack's `params.when`); a bulk lot of devices and
a PO lot are not gated. The industrial erasure gate (`engine/gates.py`, class `it`) is untouched (parity).
Never does: release, override, approve or decline (golden rule 10): a hold ends only when a certificate lands.
Model first (R16): the gate and its text are computed from the certificate's fields; nothing here drafts or explains, so there
is no model call.
"""

from collections.abc import Mapping, MutableMapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

GATE_ID = "G-DEV-WIPE"
EXCEPTION = "missing_wipe_certificates"
REQUIRED = ("method", "tool_version", "verification", "operator")
NO_CERTIFICATE = "No data-wipe certificate (GR-D1): listing blocked"
FAILED_STEP = "Wipe verification failed: re-run the wipe or destroy the storage"
KEPT_ROUTE = "recycle"  # the one channel a missing certificate does not block


def certificate_view(cond: Mapping[str, Any]) -> dict[str, Any]:
    """`{state, certificate, missing}` from a device's canonical `condition` data (module docstring)."""
    cert = cond.get("wipe_certificate")
    cert = dict(cert) if isinstance(cert, Mapping) else {}
    missing = [f for f in REQUIRED if cert.get(f) in (None, "")]
    verification = str(cert.get("verification") or "").lower()
    state = "none" if missing or verification not in ("pass", "fail") else ("failed" if verification == "fail" else "ok")
    return {"state": state, "certificate": cert or None, "missing": missing}


def _lot(case: Mapping[str, Any]) -> dict[str, Any] | None:
    v = case.get("valuer")
    return v if isinstance(v, dict) and v.get("imei") else None


def refresh(s: Session, case: MutableMapping[str, Any]) -> None:
    """Keep the certificate on the case's snapshot (`valuer.inputs.wipe`); a case that is not a received device is left."""
    lot = _lot(case)
    if lot is not None:
        cond = (canonical.get(s, "condition", f"IMEI:{lot['imei']}") or {}).get("data") or {}
        lot.setdefault("inputs", {})["wipe"] = certificate_view(cond)


def _wipe(case: Mapping[str, Any]) -> dict[str, Any]:
    got = ((_lot(case) or {}).get("inputs") or {}).get("wipe")
    return got or {"state": "none", "certificate": None, "missing": list(REQUIRED)}


def released_line(case: Mapping[str, Any]) -> str | None:
    """ "Released: wipe certificate WC-1 arrived" for a case whose certificate is on file; None otherwise."""
    cert = _wipe(case).get("certificate") or {}
    return f"Released: wipe certificate {cert['certificate_id']} arrived" if cert.get("certificate_id") else None


def _batch(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    ref = case.get("batchRef") or (_lot(case) or {}).get("batch_id")
    if not ref:
        return None
    total, waiting = s.execute(
        text(
            "SELECT count(*), count(*) FILTER (WHERE data #> '{gateHold,gates}' @> CAST('[\"G-DEV-WIPE\"]' AS jsonb)) "
            "FROM case_record WHERE data ->> 'batchRef' = :b"
        ),
        {"b": str(ref)},
    ).one()
    return {"ref": str(ref), "total": total, "waiting": waiting}


def view(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The case page's `wipe`: the state, the certificate (camel case) and the batch's count of cases waiting for one. None
    for a case that is not a received device."""
    if _lot(case) is None:
        return None
    w = _wipe(case)
    c = w.get("certificate") or {}
    cert = None if w["state"] == "none" and not c else {
        "id": c.get("certificate_id"), "method": c.get("method"), "toolVersion": c.get("tool_version"),
        "verification": c.get("verification"), "operator": c.get("operator"), "at": c.get("at"),
    }  # fmt: skip
    return {"state": w["state"], "certificate": cert, "missing": list(w.get("missing") or []), "batch": _batch(s, case)}


# ---------------------------------------------------------------- the gate G-DEV-WIPE (guardrail GR-D1)
def gate_check(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """The gate's result on a received device (module docstring); None (the data's own evaluation) for any other case."""
    if _lot(case) is None:
        return None
    w = _wipe(case)
    keep = {str(r) for r in gate.params.get("kept_routes") or [KEPT_ROUTE]}
    routes = tuple(r.id for r in pack.routes if r.id not in keep and not keep & set(r.classes))

    def result(passed: bool, hold: bool, reason: str, step: str | None = None, missing: tuple[str, ...] = ()) -> GateResult:
        return GateResult(gate.id, passed, GateEffect("block", routes, hold, step), missing, reason)

    cert = w.get("certificate") or {}
    if w["state"] == "failed":
        why = f"Wipe verification failed (GR-D1): listing blocked, certificate {cert.get('certificate_id')}"
        return result(False, True, why, FAILED_STEP)  # held too: the next certificate (the re-run) releases the case
    if w["state"] == "ok":
        return result(True, False, f"Wipe certificate {cert.get('certificate_id')} on file: {cert.get('method')}")
    return result(False, True, NO_CERTIFICATE, None, ("data_wipe",))


CHECKS[GATE_ID] = gate_check
