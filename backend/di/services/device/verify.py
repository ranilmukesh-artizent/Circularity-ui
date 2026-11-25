"""Verify the device against the quote (plan 9, P9-6.5, story DV-02; opens its work through the case process layer, I-20).

    compare_quote(quote, diagnostics) -> list[Mismatch]   IMEI, model and storage as quoted against as the lab read them
    mismatch_line(m) -> str                               "Storage quoted 256 GB, read 128 GB"
    comparison(quote, diagnostics) -> dict                the result the valuer snapshot keeps (`inputs.comparison`)
    refresh(s, case)                                      the case comparison from the canonical diagnostics, kept on it
    check(s, case, pack)                                  opens (once) the `quote_mismatch` exception item of a mismatch
    resolved(case, item, outcome, by, at) -> bool         a person resolved the item: the gate lets the channels go (or not)
    view(case, item) -> dict                              the case page's `quoteCheck`
    gate_check(case, pack, gate) -> GateResult | None     the check of the gate G-DEV-QUOTE (guardrail GR-D13), see `CHECKS`

A mismatch holds every channel of the case, through the gate G-DEV-QUOTE (Data quality, stage "match"; the gate's reason names
both values), until a person resolves the exception with `work.resolve` (I-20): a re-quote accepted releases the channels;
the trade-in returned keeps them held. Diagnostics not yet received: no exception, the comparison waits ("waiting"). A field
the lab did not read is not a mismatch. Only on a received device (`valuer.imei`); a PO lot has no quote gate.
Never does: decline, approve or resolve anything (golden rule 10): the item waits for a person.
Model first (R16): the comparison is computed from the two records, and the text is fixed wording over the two values read.
No model drafts or explains here, so there is no model call to check; every figure and word comes from the records.
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.cases import process
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

QUOTE_MISMATCH = "quote_mismatch"
GATE_ID = "G-DEV-QUOTE"
OWNER_LABEL = "Customer care"  # the owner label of GR-D13 (role Planner)
FIELDS = ("imei", "model", "storage")
Field = Literal["imei", "model", "storage"]
_LABEL = {"imei": "IMEI", "model": "Model", "storage": "Storage"}


@dataclass(frozen=True)
class Mismatch:
    field: Field
    quoted: Any
    read: Any


def _norm(field: str, v: Any) -> Any:
    if field == "storage":
        return float(v)
    return str(v).strip().lower()


def _shown(field: str, v: Any) -> Any:
    """The value as it is said: a storage in whole GB, text trimmed."""
    if field == "storage":
        return int(v) if float(v) == int(float(v)) else float(v)
    return str(v).strip()


def compare_quote(quote: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> list[Mismatch]:
    """The differences between the quote (`imei`, `model`, `storage_gb`) and the lab's diagnostics (`imei_read`, `model_read`,
    `storage_read_gb`), in the order IMEI, model, storage. Text compares trimmed and without case, storage as a number. A
    field either side lacks is left out (it is not a mismatch)."""
    pairs = (("imei", "imei", "imei_read"), ("model", "model", "model_read"), ("storage", "storage_gb", "storage_read_gb"))
    out: list[Mismatch] = []
    for field, q, r in pairs:
        quoted, read = quote.get(q), diagnostics.get(r)
        if quoted in (None, "") or read in (None, ""):
            continue
        try:
            same = _norm(field, quoted) == _norm(field, read)
        except (TypeError, ValueError):
            same = False
        if not same:
            out.append(Mismatch(field, _shown(field, quoted), _shown(field, read)))  # type: ignore[arg-type]
    return out


def _say(field: str, v: Any) -> str:
    return f"{v} GB" if field == "storage" else str(v)


def mismatch_line(m: Mismatch) -> str:
    """ "Storage quoted 256 GB, read 128 GB"; "Model quoted iPhone 14, read iPhone 13"."""
    return f"{_LABEL[m.field]} quoted {_say(m.field, m.quoted)}, read {_say(m.field, m.read)}"


def diagnostics_of(cond: Mapping[str, Any]) -> dict[str, Any] | None:
    """The lab's read of the device out of its canonical `condition` data, or None when it has read none of the three."""
    d = {k: cond.get(k) for k in ("imei_read", "model_read", "storage_read_gb")}
    return d if any(v not in (None, "") for v in d.values()) else None


def comparison(quote: Mapping[str, Any], diagnostics: Mapping[str, Any] | None) -> dict[str, Any]:
    """`{state, mismatches: [{field, quoted, read, line}]}`: "waiting" with no diagnostics, else "match" or "mismatch"."""
    if diagnostics is None:
        return {"state": "waiting", "mismatches": []}
    found = compare_quote(quote, diagnostics)
    return {
        "state": "mismatch" if found else "match",
        "mismatches": [{"field": m.field, "quoted": m.quoted, "read": m.read, "line": mismatch_line(m)} for m in found],
    }


def quote_of(valuer: Mapping[str, Any]) -> dict[str, Any]:
    """What the trade-in quoted, from the device case's valuer snapshot."""
    return {"imei": valuer.get("imei"), "model": valuer.get("model"), "storage_gb": valuer.get("storage_gb")}


def _lot(case: Mapping[str, Any]) -> dict[str, Any] | None:
    v = case.get("valuer")
    return v if isinstance(v, dict) and v.get("imei") else None


# ---------------------------------------------------------------- on a case
def refresh(s: Session, case: MutableMapping[str, Any]) -> None:
    """Read the device's diagnostics now and keep the comparison on the case's snapshot (`valuer.inputs.comparison`). A case
    that is not a received device is left alone."""
    lot = _lot(case)
    if lot is None:
        return
    cond = (canonical.get(s, "condition", f"IMEI:{lot['imei']}") or {}).get("data") or {}
    lot.setdefault("inputs", {})["comparison"] = comparison(quote_of(lot), diagnostics_of(cond))


def _item(s: Session, case_id: str) -> dict[str, Any] | None:
    """The case's newest `quote_mismatch` item (any status)."""
    r = s.execute(
        text("SELECT id, status, outcome FROM work_item WHERE case_id = :c AND type = :t ORDER BY id DESC LIMIT 1"),
        {"c": case_id, "t": QUOTE_MISMATCH},
    ).mappings().first()  # fmt: skip
    return dict(r) if r else None


def check(s: Session, case: Mapping[str, Any], pack: Pack) -> None:
    """A mismatch opens the case's one `quote_mismatch` item (never a second, even after it is resolved: a person's answer
    stands). The owner is the pack's exception type's role, else Planner, under the label "Customer care"; the SLA is the
    pack's `exception` one. In the caller's transaction."""
    comp = (_lot(case) or {}).get("inputs", {}).get("comparison") or {}
    if comp.get("state") != "mismatch" or _item(s, str(case["id"])) is not None:
        return
    kind = next((t for t in pack.runtime.exception_types if t.id == QUOTE_MISMATCH), None)
    lines = "; ".join(m["line"] for m in comp["mismatches"])
    cid = str(case["id"])
    process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=QUOTE_MISMATCH,
        title=f"{cid}: {lines}", cause=f"The lab read the device differently from the quote: {lines}",
        action=f"{OWNER_LABEL}: " + (kind.action if kind else "Accept a re-quote or return the trade-in"),
        owner_role=kind.owner_role if kind else "Planner", due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip


def resolved(case: MutableMapping[str, Any], outcome: str, by: str, at: str) -> bool:
    """Record a person's answer on the case (`quoteResolved`); True when it lets the channels go (a re-quote accepted),
    False when the trade-in is returned (the channels stay held)."""
    accepted = "return" not in outcome.lower()
    case["quoteResolved"] = {"outcome": outcome, "accepted": accepted, "by": by, "at": at}
    return accepted


def view(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The case page's `quoteCheck`: the state, a row per field (quoted, read, whether it differs), the owner label and the
    exception's state. None for a case that is not a received device."""
    lot = _lot(case)
    if lot is None:
        return None
    comp = (lot.get("inputs") or {}).get("comparison") or {"state": "waiting", "mismatches": []}
    cond = (canonical.get(s, "condition", f"IMEI:{lot['imei']}") or {}).get("data") or {}
    read = {"imei": cond.get("imei_read"), "model": cond.get("model_read"), "storage": cond.get("storage_read_gb")}
    quote = {"imei": lot.get("imei"), "model": lot.get("model"), "storage": lot.get("storage_gb")}
    bad = {m["field"] for m in comp["mismatches"]}
    rows = [
        {"field": f, "quoted": quote[f], "read": _shown(f, read[f]) if read[f] not in (None, "") else None, "mismatch": f in bad}
        for f in FIELDS
    ]  # fmt: skip
    item = _item(s, str(case["id"]))
    answer = case.get("quoteResolved") or {}
    return {
        "state": comp["state"], "rows": rows, "owner": OWNER_LABEL,
        "item": {"id": item["id"], "state": "open" if item["status"] == "open" else "done", "outcome": item["outcome"],
                 "by": answer.get("by")} if item else None,
    }  # fmt: skip


# ---------------------------------------------------------------- the gate G-DEV-QUOTE (guardrail GR-D13)
def gate_check(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """Every channel holds on a mismatch (the reason names both values) until a person accepts a re-quote; a match, or no
    diagnostics yet, lets the channels through."""
    lot = _lot(case)
    if lot is None:
        return None
    routes = tuple(r.id for r in pack.routes)
    comp = (lot.get("inputs") or {}).get("comparison") or {}
    answer = case.get("quoteResolved") or {}

    def result(passed: bool, reason: str) -> GateResult:
        return GateResult(gate.id, passed, GateEffect("block", routes, False, None), (), reason)

    if comp.get("state") != "mismatch":
        return result(
            True, "Waiting for the lab's diagnostics" if comp.get("state") == "waiting" else "Quote matches the device read"
        )
    if answer.get("accepted"):
        return result(True, f"Mismatch resolved by {answer.get('by')}: {answer.get('outcome')}")
    return result(False, "; ".join(m["line"] for m in comp["mismatches"]))


CHECKS[GATE_ID] = gate_check
