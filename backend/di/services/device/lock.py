"""The blacklist and lock gate for a received device (plan 9, P9-6.6, story DV-03; gate G-DEV-LOCK of the catalogue, I-2; its
exception item is a work item, I-20).

    registry_view(cond, now, recheck_days, source) -> dict   the registry's answer on a device: state, hits, check date, age
    refresh(s, case, pack)                                   the case's registry view from the canonical `condition`, kept on
                                                             its snapshot (`valuer.inputs.registry`) on every valuation
    check(s, case, pack)                                     a hit opens (once per check) the `blacklist_hit` exception item
    resolve_refusal(s, case, pack) -> str | None             why a person may not release a hit yet (needs a newer check)
    view(s, case, pack) -> dict | None                       the case page's `registry` block
    gate_check(case, pack, gate) -> GateResult | None        the check of G-DEV-LOCK (guardrail GR-D7), registered in CHECKS

The registry (dvreg, synthetic) writes `condition.device_blacklist` (`clear`, `reported_lost`, `reported_stolen`),
`device_lock` (`on`, `off`), `device_finance` (`clear`, `balance_owed`) and `registry_checked_at`. States, in this order:
`none` (no check on file) and `stale` (checked longer ago than the gate's `recheck_days`, 7) hold the case until a new check
arrives; `hit` (blacklist not clear, activation lock on, or a balance owed) fails every channel but the gate's
`locked_routes` (`parts`, `recycle`, P9-6.15) with "Blacklist or lock check hit (GR-D7): <status>, checked <date>" and opens one
`blacklist_hit` item (role Approver, owner label "Compliance") with the registry evidence; `clear` lets the case go on.
Only a person releases a hit (`work.resolve`, which agents may not run), and only with a registry check newer than the hit
that shows the device clear. Only a received device (`valuer.imei`) has the gate; a PO lot has none.
Never does: decline, approve, resolve or override anything (a fraud or lock outcome is a hold for a person, never an automatic
decline). Policy on locked or blacklisted devices differs by market; Kinective's Legal team reviews it.
Model first (R16): the gate and its text are computed from the registry's fields; nothing here drafts or explains, so there is
no model call.
"""

from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.cases import process, record_match
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult, pack_gates
from di.services.modeler.pack import Pack

GATE_ID = "G-DEV-LOCK"
BLACKLIST_HIT = "blacklist_hit"
OWNER_LABEL = "Compliance"
SOURCE_ID = "dvreg"
DEFAULT_RECHECK_DAYS = 7.0


def params(pack: Pack) -> dict[str, Any]:
    """The gate's parameters in the pack: `recheck_days` and `locked_routes` (defaults when the pack has no such gate)."""
    got = next((g.params for g in pack_gates(pack) if g.id == GATE_ID), {})
    return {"recheck_days": DEFAULT_RECHECK_DAYS, "locked_routes": []} | dict(got)


def _time(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        t = v
    elif isinstance(v, str) and v:
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def registry_view(cond: Mapping[str, Any], now: datetime, recheck_days: float, source: str = "") -> dict[str, Any]:
    """The registry's answer on a device from its canonical `condition` data (module docstring)."""
    black, lock, fin = cond.get("device_blacklist"), cond.get("device_lock"), cond.get("device_finance")
    at = _time(cond.get("registry_checked_at"))
    hits = []
    if black not in (None, "", "clear"):
        hits.append(str(black).replace("_", " "))
    if lock == "on":
        hits.append("activation lock on")
    if fin == "balance_owed":
        hits.append("balance owed")
    age = round((now - at).total_seconds() / 86400, 1) if at else None
    if all(v in (None, "") for v in (black, lock, fin, at)):
        state = "none"
    elif hits:
        state = "hit"
    elif at is None or (age is not None and age > recheck_days):
        state = "stale"
    else:
        state = "clear"
    return {
        "state": state, "status": "; ".join(hits) or "clear", "hits": hits, "blacklist": black, "lock": lock, "finance": fin,
        "checked_at": at.date().isoformat() if at else None, "checked_ts": at.isoformat() if at else None,
        "age_days": age, "recheck_days": recheck_days, "source": source,
    }  # fmt: skip


def _lot(case: Mapping[str, Any]) -> dict[str, Any] | None:
    v = case.get("valuer")
    return v if isinstance(v, dict) and v.get("imei") else None


def current(s: Session, lot: Mapping[str, Any], pack: Pack, now: datetime | None = None) -> dict[str, Any]:
    """The registry's answer on the lot's device as the canonical store holds it now."""
    cond = (canonical.get(s, "condition", f"IMEI:{lot['imei']}") or {}).get("data") or {}
    return registry_view(cond, now or clock.now(), float(params(pack)["recheck_days"]), record_match.system_name(s, SOURCE_ID))


def refresh(s: Session, case: MutableMapping[str, Any], pack: Pack) -> None:
    """Keep the registry view on the case's snapshot (`valuer.inputs.registry`); a case that is not a received device is left."""
    lot = _lot(case)
    if lot is not None:
        lot.setdefault("inputs", {})["registry"] = current(s, lot, pack)


def _open_item(s: Session, case_id: str) -> int | None:
    r = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id LIMIT 1"),
        {"c": case_id, "t": BLACKLIST_HIT},
    ).scalar()
    return int(r) if r is not None else None


def _registry(case: Mapping[str, Any]) -> dict[str, Any]:
    return ((_lot(case) or {}).get("inputs") or {}).get("registry") or {}


def check(s: Session, case: MutableMapping[str, Any], pack: Pack) -> None:
    """A hit opens the `blacklist_hit` item (role of the pack's exception type, else Approver; label "Compliance"; the pack's
    `exception` SLA) with the registry evidence, once per check: the case remembers the check it opened for (`registryHit`)."""
    reg = _registry(case)
    cid = str(case["id"])
    if reg.get("state") != "hit" or _open_item(s, cid) is not None:
        return
    if (case.get("registryHit") or {}).get("checked_ts") == reg.get("checked_ts"):
        return  # a person already answered this very check
    case["registryHit"] = {"checked_ts": reg.get("checked_ts"), "status": reg["hits"]}
    kind = next((t for t in pack.runtime.exception_types if t.id == BLACKLIST_HIT), None)
    process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=BLACKLIST_HIT,
        title=f"{cid}: registry hit, {reg['status']}",
        cause=(f"{reg['source']} reports {reg['status']} for IMEI {_lot(case)['imei']}, checked {reg['checked_at']} "  # type: ignore[index]
               f"(blacklist {reg['blacklist']}, activation lock {reg['lock']}, finance {reg['finance']})"),
        action=f"{OWNER_LABEL}: " + (kind.action if kind else "Hold the device; release only with a newer registry check"),
        owner_role=kind.owner_role if kind else "Approver", due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip


def resolve_refusal(s: Session, case: Mapping[str, Any], pack: Pack) -> str | None:
    """Why a hit may not be released yet: it needs a registry check newer than the hit that shows the device clear."""
    lot, hit = _lot(case), case.get("registryHit") or {}
    if lot is None or not hit:
        return None
    now = current(s, lot, pack)
    newer = now["checked_ts"] is not None and now["checked_ts"] > str(hit.get("checked_ts") or "")
    if newer and now["state"] == "clear":
        return None
    return "A release needs a registry check newer than the hit that shows the device clear."


def view(s: Session, case: Mapping[str, Any], pack: Pack) -> dict[str, Any] | None:
    """The case page's `registry`: the status, check date and source, and on a hit the owner, the item's state and the routes
    the device may still take. None for a case that is not a received device."""
    lot = _lot(case)
    if lot is None:
        return None
    reg = _registry(case) or current(s, lot, pack)
    row = s.execute(
        text("SELECT status FROM work_item WHERE case_id = :c AND type = :t ORDER BY id DESC LIMIT 1"),
        {"c": str(case["id"]), "t": BLACKLIST_HIT},
    ).scalar()
    return {
        "state": reg["state"], "status": reg["status"], "checkedAt": reg["checked_at"], "source": reg["source"],
        "ageDays": reg["age_days"], "recheckDays": reg["recheck_days"], "owner": OWNER_LABEL,
        "item": None if row is None else ("open" if row == "open" else "done"),
        "allowedRoutes": list(params(pack)["locked_routes"]) if reg["state"] == "hit" else [],
    }  # fmt: skip


# ---------------------------------------------------------------- the gate G-DEV-LOCK (guardrail GR-D7)
def _date(reg: Mapping[str, Any]) -> str:
    return str(reg.get("checked_at") or "no date")


def gate_check(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """The gate's result on a received device (module docstring); None (the data's own evaluation) for any other case."""
    if _lot(case) is None:
        return None
    reg = _registry(case)
    state = reg.get("state") or "none"
    # only a hit leaves the locked routes open (P9-6.15); with no check or a stale one the case waits, and no route is open
    keep = {str(r) for r in gate.params.get("locked_routes") or []} if state == "hit" else set()
    routes = tuple(r.id for r in pack.routes if r.id not in keep)

    def result(passed: bool, hold: bool, reason: str, missing: tuple[str, ...] = ()) -> GateResult:
        return GateResult(gate.id, passed, GateEffect("block", routes, hold, None), missing, reason)

    if state == "hit":
        return result(False, False, f"Blacklist or lock check hit (GR-D7): {reg['status']}, checked {_date(reg)}")
    if state == "none":
        return result(False, True, "No registry check on file", ("device_registry_check",))
    if state == "stale":
        why = f"checked {_date(reg)}, older than {reg.get('recheck_days'):g} days"
        return result(False, True, f"Evidence stale: registry check {why}", ("device_registry_check",))
    return result(True, False, f"Registry clear, checked {_date(reg)}")


CHECKS[GATE_ID] = gate_check
