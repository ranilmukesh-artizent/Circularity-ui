"""The lines of a telecom CPE lot (plan 9, P9-12.6; stories NS-CPE-01, NS-CPE-02): one case per lot of one model and grade
per week, each device of the lot a line that is released or held for its factory-reset record.

    refresh(s, case, pack)   the case's `lot`, read from the canonical store: the lot's serials (`asset.lot_serials` of the lot's
                             asset key) and each serial's `condition.factory_reset`; every valuation does it first
    recheck(s, lot_key)      the open lots holding a line for a record that arrived are valued again (worker `case.gateRecheck`)

`case["lot"]` is `{id, model, week, grade, qty, released, held, heldKeys, lines}`; a line is `{serial, status: "released" |
"held", reset: {method, at} | None, why}`. The pack's standard valuer reads `lot.released` for the route that puts devices with
a new subscriber (G-DATA-1 of the pack, `accept_methods_for_redeploy`: a factory reset counts as "clear"): a device with no
record, or a method the gate does not accept, is a held line and is left out of that route's value, while the rest of the lot
goes on. A record that arrives releases its line on its own: `canonical.store.apply` queues `case.gateRecheck` for the lot.

Never does: approve a lot, write a canonical record, or invent a record. A lot with no serials on file has no lines (`lot` is
absent) and the redeploy route is not valued ("No device of the lot has a reset record yet"). NIST SP 800-88 Rev. 2 and the
customer's rules are the sources of the gate; Kinective's Legal team reviews it before it is relied on.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import serial_key
from di.services.cases import store
from di.services.modeler.pack import Pack

PACK = "telecom_cpe"
GATE = "G-DATA-1"
EQUIVALENT = {"factory_reset": "clear"}  # a reset record's method, as the gate's `accept_methods_for_redeploy` names it
OPEN = ("none", "awaiting_approval")  # a lot whose decision is still open is valued again; a decided one keeps its numbers


def accepted(pack: Pack) -> set[str]:
    """The methods that release a line, from the pack's gate G-DATA-1 (default: clear)."""
    params = next((g.params for g in pack.gates if g.id == GATE), {})
    return {str(m) for m in params.get("accept_methods_for_redeploy") or ["clear"]}


def _line(serial: str, rec: dict[str, Any] | None, ok: set[str]) -> dict[str, Any]:
    if rec is None:
        return {"serial": serial, "status": "held", "reset": None, "why": "No factory-reset record"}
    method = EQUIVALENT.get(str(rec.get("method")), str(rec.get("method")))
    reset = {"method": rec.get("method"), "at": rec.get("at")}
    if method in ok:
        return {"serial": serial, "status": "released", "reset": reset, "why": None}
    return {"serial": serial, "status": "held", "reset": reset, "why": f"Reset method {rec.get('method')} is not accepted"}


def refresh(s: Session, c: store.Case, pack: Pack) -> None:
    """Set `c["lot"]` from the canonical store (module docstring); remove it when the lot has no serials on file."""
    found = s.execute(text("SELECT data FROM canonical WHERE model = 'asset' AND key = :k"), {"k": c.get("assetId")}).scalar()
    lot: dict[str, Any] = found or {}
    serials = lot.get("lot_serials")
    if not isinstance(serials, list) or not serials:
        c.pop("lot", None)
        return
    keys = {x: serial_key(c.get("owner"), x) for x in serials}
    rows = s.execute(
        text("SELECT key, data -> 'factory_reset' FROM canonical WHERE model = 'condition' AND key = ANY(:k)"),
        {"k": list(keys.values())},
    )
    resets = {key: rec for key, rec in rows if isinstance(rec, dict)}
    ok = accepted(pack)
    lines = [_line(x, resets.get(keys[x]), ok) for x in serials]
    held = [x for x in lines if x["status"] == "held"]
    c["lot"] = {
        "id": lot.get("lot_id"), "model": lot.get("model"), "week": lot.get("lot_week"), "grade": c.get("grade"),
        "qty": len(lines), "released": len(lines) - len(held), "held": len(held),
        "heldKeys": [keys[x["serial"]] for x in held], "lines": lines,
    }  # fmt: skip


def recheck(s: Session, lot_key: str) -> list[str]:
    """Every open lot case of the lot that holds a line is valued again, so a line whose record arrived is released. Returns the
    case ids valued. In the caller's transaction."""
    from di.services.cases import intake  # intake imports this module

    ids = s.execute(
        text(
            "SELECT id FROM case_record WHERE data ->> 'assetId' = :a AND data ->> 'template' = :t AND stage = ANY(:o) "
            "AND jsonb_array_length(COALESCE(data -> 'lot' -> 'heldKeys', '[]'::jsonb)) > 0 ORDER BY id"
        ),
        {"a": lot_key, "t": PACK, "o": list(OPEN)},
    ).scalars().all()  # fmt: skip
    done: list[str] = []
    for cid in ids:
        c = store.get(s, cid, for_update=True)
        if c is None or c.get("approval") or c.get("submitted"):
            continue
        intake.revalue(s, c)
        store.save(s, c)
        done.append(cid)
    return done
