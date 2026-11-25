"""Gates on a case: evidence attached, gates applied to the routes, a hold until evidence arrives, release (plan 9,
P9-1.2; stories X-03 and X-07). Uses registry entries I-2 (`gates`) and I-3 (`evidence`).

    attach_evidence(s, case)   the canonical `compliance` records of the case's asset become `case["evidenceRecords"]`
    apply(case, routes)        gates evaluated for the case's pack, applied to the routes, then `hold` (R20: before the
                               business rules and before ranking; `decide.decide_case` calls it)
    hold(case, results)        a failed gate that holds sets `case["gateHold"]` and leaves no recommendation (stage
                               `none`); a failed gate with a step appends it to `case["requiredSteps"]`
    recheck(s, asset_key)      the worker job `case.gateRecheck`: evidence landed, so every held case of the asset is
                               valued again; a case that clears is released with a stage log row by `system`
    batch_status(s, ref)       {total, held, released} of the cases opened with the same `facts.batch`

A hold also opens one exception item for the case (`sync_item`, type `evidence_missing`, P9-1.7: My work lists it, the
pack's SLA escalates it) and a release closes it with the outcome "released".

Owns: those functions and the case keys `evidenceRecords`, `gates` (one row per gate result, as the Case page shows it),
`gateHold` and `requiredSteps`. Never does: approve anything. A release makes the case decidable again; a person still
approves the decision.

The pack file of a case is `base_pack(case)`: `default_pack_of(case)`, the pack file of its template. Tests and
`recheck(pack_of=...)` replace it; intake lays the owner's customer overlay on it (`live_rules.live_pack`) and passes
the result to `apply`. The shipped packs have no active gates, so no shipped case is gated.
"""

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.cases import lifecycle, store
from di.services.engine.routes import Route
from di.services.modeler.evidence import evidence_of, label_of, records_of
from di.services.modeler.gates import GateResult, apply_gate_results, catalogue, evaluate_gates
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.stages import STAGE_LABELS

PackOf = Callable[[Mapping[str, Any]], Pack]
_override: ContextVar[PackOf | None] = ContextVar("gate_hold_pack_of", default=None)
# The session and case id `attach_evidence` was called with: the very next `apply` for that case uses it to open or close
# the case's exception item (P9-1.7), once. `apply` has no session of its own (`decide_case` is pure on the case).
_bound: ContextVar[tuple[Session, str] | None] = ContextVar("gate_hold_session", default=None)
EVIDENCE_MISSING = "evidence_missing"  # the type of the exception item a hold opens


def default_pack_of(case: Mapping[str, Any]) -> Pack:
    """The pack the case is gated by: its template's pack file."""
    return load_pack(case.get("template") or "industrial")


# ---------------------------------------------------------------- evidence
def attach_evidence(s: Session, case: MutableMapping[str, Any]) -> None:
    """Set `case["evidenceRecords"]` from the canonical `compliance` records of the case's asset key (each with the
    source that wrote its result). A case with none and no earlier list is left as it is."""
    rows = s.execute(
        text(
            "SELECT c.data, (SELECT p.source_id FROM provenance p WHERE p.model = 'compliance' AND p.key = c.key "
            "AND p.field = 'result' ORDER BY p.fetched_at DESC LIMIT 1) AS source "
            "FROM canonical c WHERE c.model = 'compliance' AND c.data ->> 'asset_key' = :a ORDER BY c.key"
        ),
        {"a": case.get("assetId")},
    ).all()
    recs = [
        {k: d.get(k) for k in ("type", "result", "at", "valid_until", "method", "tool", "ref", "operator")}
        | {"source": src or "", "value": d.get("value") if isinstance(d.get("value"), dict) else {}}
        for d, src in rows
    ]
    if recs or "evidenceRecords" in case:
        case["evidenceRecords"] = recs
    _bound.set((s, str(case.get("id"))))


def _as_of(case: Mapping[str, Any]) -> datetime:
    """The time gates read evidence at: now, or the newest record's time when that is later (a source's clock may run
    ahead of ours; evidence on file is never ignored for being from the future)."""
    return max([clock.now(), *(e.at for e in records_of(case))])


# ---------------------------------------------------------------- gates on a case
def _rows(case: Mapping[str, Any], pack: Pack, results: Sequence[GateResult], as_of: datetime) -> list[dict[str, Any]]:
    cat = catalogue()
    names = {r.id: r.name for r in pack.routes}
    out = []
    for r in results:
        g = cat[r.gate_id]
        on_file = [
            {"type": t, "label": label_of(t), "source": e.source, "at": e.at.isoformat()}
            for t in g.evidence
            if (e := evidence_of(case, t, as_of)) is not None and e.result == "pass"
        ]
        out.append({
            "id": g.id, "name": g.name, "type": g.type, "stage": g.stage, "stageLabel": STAGE_LABELS[g.stage],
            "passed": r.passed, "kind": r.effect.kind, "routes": list(r.effect.routes),
            "routeNames": [names[i] for i in r.effect.routes if i in names], "hold": r.effect.hold, "step": r.effect.step,
            "owner": g.owner, "evidence": on_file, "missing": [label_of(t) for t in r.evidence_missing], "reason": r.reason,
            "locked": g.locked,
        })  # fmt: skip
    return out


def hold(case: MutableMapping[str, Any], results: Sequence[GateResult]) -> bool:
    """Set the hold and the required steps from the gate results; True when the case is held. A failed result that
    holds sets `gateHold` {gates, since, batch}, leaves no recommendation and stage `none`; the time it has been held
    since stays when it is held again. A failed result with a step lists {gate, step, owner} in `requiredSteps`."""
    cat = catalogue()
    failed = [r for r in results if not r.passed]
    held = [r.gate_id for r in failed if r.effect.hold]
    steps = [{"gate": r.gate_id, "step": r.effect.step, "owner": cat[r.gate_id].owner} for r in failed if r.effect.step]
    if steps:
        case["requiredSteps"] = steps
    else:
        case.pop("requiredSteps", None)
    if not held:
        if case.get("gateHold") is not None:
            case["gateHold"] = None
        return False
    prior = case.get("gateHold") or {}
    case["gateHold"] = {"gates": held, "since": prior.get("since") or clock.now().isoformat(), "batch": case.get("batchRef")}
    case["recommendation"] = None
    case["stage"] = "none"
    return True


def base_pack(case: Mapping[str, Any], published: Pack | None = None) -> Pack:
    """The pack the case's customer overlay is laid on: the pack a `recheck` is given, else `published` (the pack version
    published for the case's owner, P9-1.6; the caller reads it), else `default_pack_of`."""
    if (given := _override.get()) is not None:
        return given(case)
    return published or default_pack_of(case)


def apply(
    case: MutableMapping[str, Any], routes: list[Route], pack: Pack | None = None, as_of: datetime | None = None
) -> list[GateResult]:
    """Evaluate the case's gates, fail the blocked routes and hold the case (R20: call it before the business rules
    and before ranking). `pack` (default: `base_pack(case)`) and `as_of` (default: `_as_of(case)`) are what `decide_case`
    decides with. A case that no gate applies to, and has none recorded, is left untouched."""
    bound = _bound.get()
    _bound.set(None)  # taken once, whether or not a gate applies
    pack = pack or base_pack(case)
    as_of = as_of or _as_of(case)
    results = evaluate_gates(case, pack, as_of)
    if not results and "gates" not in case:
        return results
    apply_gate_results(routes, results)
    case["gates"] = _rows(case, pack, results, as_of)
    hold(case, results)
    if bound is not None and bound[1] == str(case.get("id")):
        sync_item(bound[0], case, pack)
    return results


# ---------------------------------------------------------------- the exception item of a hold (P9-1.7)
def sync_item(s: Session, case: Mapping[str, Any], pack: Pack) -> None:
    """One open exception item (type `evidence_missing`) while the case is held, none after: a hold opens it for the owner
    of the pack's exception type of that id, else the role of the failed gate's owner, with the pack's `exception` SLA; a
    release closes it with the outcome "released". A case already held keeps its item. In the caller's transaction."""
    from di.services.cases import process

    cid = str(case["id"])
    open_id = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id LIMIT 1"),
        {"c": cid, "t": EVIDENCE_MISSING},
    ).scalar()
    held = isinstance(case.get("gateHold"), dict)
    if not held:
        if open_id is not None:
            process.close_item(s, int(open_id), "released", "system")
        return
    if open_id is not None:
        return
    failed = [g for g in case.get("gates") or [] if not g["passed"] and g["hold"]]
    missing = list(dict.fromkeys(m for g in failed for m in g["missing"]))
    kind = next((t for t in pack.runtime.exception_types if t.id == EVIDENCE_MISSING), None)
    role = kind.owner_role if kind else process.role_of_owner(failed[0]["owner"] if failed else "")
    what = ", ".join(missing) or "the evidence"
    process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=EVIDENCE_MISSING,
        title=f"{cid} is held: {what} missing",
        cause="; ".join(g["reason"] for g in failed if g.get("reason")) or "A gate needs evidence the case does not have",
        action=kind.action if kind else f"Wait for {what} or chase the source system", owner_role=role,
        due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip


# ---------------------------------------------------------------- release on evidence
def _released_line(case: Mapping[str, Any], gate_ids: Sequence[str]) -> str:
    as_of = _as_of(case)
    cat = catalogue()
    parts = []
    for gid in gate_ids:
        for t in cat[gid].evidence if gid in cat else ():
            if (e := evidence_of(case, t, as_of)) is not None and e.result == "pass":
                parts.append(f"{label_of(t)} from {e.source or 'a source'} at {e.at.strftime('%Y-%m-%d %H:%M UTC')}")
    return "Released: " + ("; ".join(dict.fromkeys(parts)) or "the evidence arrived")


def recheck(s: Session, asset_key: str, *, pack_of: PackOf | None = None) -> list[str]:
    """Every open case of the asset that is held gets its evidence attached and its gates evaluated again (it is valued
    again, `intake.revalue`). A case that clears is released: `gateHold` is None, it moves on from `none` and a stage
    log row by `system` says why. A case still missing evidence stays held. Returns the released case ids. In the
    caller's transaction."""
    from di.services.cases import intake  # intake imports this module

    held = s.execute(
        text(
            "SELECT id FROM case_record WHERE data ->> 'assetId' = :a AND stage <> 'closed' "
            "AND jsonb_typeof(data -> 'gateHold') = 'object' ORDER BY id"
        ),
        {"a": asset_key},
    ).scalars().all()  # fmt: skip
    released: list[str] = []
    token = _override.set(pack_of)
    try:
        for cid in held:
            c = store.get(s, cid, for_update=True)
            if c is None or not isinstance(c.get("gateHold"), dict):
                continue
            was = list(c["gateHold"].get("gates") or [])
            intake.revalue(s, c)
            if c.get("gateHold") is not None:
                store.save(s, c)
                continue
            lifecycle.move(s, c, "awaiting_approval" if c.get("recommendation") else "none", _released_line(c, was), "system")
            released.append(cid)
    finally:
        _override.reset(token)
    return released


def batch_status(s: Session, batch_ref: str) -> dict[str, int]:
    """{total, held, released} of the cases opened with this batch: held are those with a gateHold, the rest are
    released."""
    row = s.execute(
        text(
            "SELECT count(*), count(*) FILTER (WHERE jsonb_typeof(data -> 'gateHold') = 'object') "
            "FROM case_record WHERE data ->> 'batchRef' = :b"
        ),
        {"b": batch_ref},
    ).one()
    return {"total": row[0], "held": row[1], "released": row[0] - row[1]}
