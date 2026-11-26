"""Matching a returned asset to its system of record, and the chain of custody (plan 9, P9-1.10; story X-08; opens its
work through the case process layer, registry entry I-20).

    match(s, case, pack) -> MatchResult          is the asset's key held by the pack's system of record?
    check(s, case, pack, by=)                    on open and on every re-check: sets `case["recordMatch"]`, opens (once) or
                                                 closes the exception item, keeps the custody ("moved", "matched")
    receive(s, case, by)                         custody "received", when a case opens
    released(case, by)                           custody "released", when a gate hold clears
    reconcile(s, source_id) -> ReconcileReport   the job `case.recordMatch` at the end of each sync of that source:
                                                 `extra` (received, not in the owner's system), `matched`, `missing`
    is_record_source(s, source_id) -> bool       the end of a sync asks: is this source a pack's system of record?
    view(s, case, pack) -> dict | None           the case screen's `recordMatch`

The pack says where the record is (`data.record_match`: `source_type` the source id, `field` the canonical field the system
owns, `mode`, `missing_after_days`). Found: the canonical `asset` record of the case's asset key holds that field, a source of
that type wrote it, and its `owner_tenant` is the case's owner or empty. Mode "exception" (both pilot packs) opens an item and
the valuation goes on; mode "hold" leaves no recommendation until the record is found. Items are `not_in_system_of_record`
(a case, owner and SLA from the pack's exception type) and `expected_return_missing` (an asset the system says is on its way
back, with no case after `missing_after_days`, for the record's org). `case["custody"]` is append-only: `{at, event, source,
location, by}` with event "received", "matched", "moved" or "released"; it is never edited or removed, and a revalue keeps it.

A pack may name its own exception types (P9-12.2, the ITAD manifest): `record_match.extra_type` and `missing_type` (ids of its
`runtime.exception_types`, `type_id`), and `critical` (the ids whose items sort first, priority 10); an item's owner goes
through the pack's `roles`. A source that carries `asset.custody` (events with their times) gives the case's custody
itself (`receive`), in its order and under its own name.

Never does: decide, approve or resolve anything; an item waits for a person. The industrial pack has no `record_match` and
no custody, so the demo's cases are unchanged. Custody is a record the platform keeps; it makes no claim about legal
chain-of-custody requirements, which Kinective's Legal team reviews.
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.cases import process, store
from di.services.modeler.pack import Pack
from di.services.modeler.templates import TEMPLATE_KEYS

NOT_IN_RECORD = "not_in_system_of_record"
EXPECTED_MISSING = "expected_return_missing"
ON_THE_WAY = ("returned", "in_transit")  # asset.disposition values: the system says the asset is coming back


@dataclass(frozen=True)
class MatchResult:
    found: bool
    source: str  # the system's name
    key: str | None  # the record's key: the value of the pack's field
    synced_at: datetime | None
    reason: str


@dataclass
class ReconcileReport:
    missing: list[str] = field(default_factory=list)  # asset keys expected back with no case
    extra: list[str] = field(default_factory=list)  # case ids: received, not in the owner's system
    matched: list[str] = field(default_factory=list)  # case ids that are now found


# ---------------------------------------------------------------- the pack's setting
def _spec(pack: Pack) -> dict[str, Any] | None:
    rm = pack.data.record_match
    return rm if isinstance(rm, dict) and rm.get("source_type") and rm.get("field") else None


def system_name(s: Session, source_id: str) -> str:
    """The source system's name as the Connection Fabric shows it (its id when it is not registered)."""
    return str(s.execute(text("SELECT vendor FROM source_system WHERE id = :i"), {"i": source_id}).scalar() or source_id)


def _record_packs(s: Session, source_id: str) -> list[tuple[str, Pack]]:
    """The packs (key, pack in force) whose system of record is this source."""
    from di.services.cases import intake  # intake reads the pack store (the layer above this module's)

    out = []
    for key in [*TEMPLATE_KEYS, *sorted(intake.published_keys(s) - set(TEMPLATE_KEYS))]:
        pack = intake.active_pack(s, key, None)
        if (rm := _spec(pack)) and rm["source_type"] == source_id:
            out.append((key, pack))
    return out


def is_record_source(s: Session, source_id: str) -> bool:
    """True when a pack names this source as its system of record (a sync of it ends with `case.recordMatch`)."""
    return bool(_record_packs(s, source_id))


def _type(pack: Pack, type_id: str) -> Any:
    return next((t for t in pack.runtime.exception_types if t.id == type_id), None)


def type_id(pack: Pack, kind: str) -> str:
    """The exception type id for `kind` ("extra": received, not in the record; "missing": expected, no case): the pack's
    `record_match.extra_type` / `missing_type` when it names one (the ITAD manifest, P9-12.2), else the default."""
    spec = _spec(pack) or {}
    return str(spec.get(f"{kind}_type") or (NOT_IN_RECORD if kind == "extra" else EXPECTED_MISSING))


def _role(pack: Pack, kind: Any) -> str:
    """The app role an item of this exception type goes to: the type's owner through the pack's `roles`, else as written."""
    return pack.roles.get(kind.owner_role, kind.owner_role) if kind else "Planner"


def _critical(s: Session, pack: Pack, item_id: int, type_id_: str) -> None:
    """An item of a type the pack lists in `record_match.critical` sorts first in My work (priority 10)."""
    if type_id_ in ((_spec(pack) or {}).get("critical") or []):
        s.execute(text("UPDATE work_item SET priority = 10 WHERE id = :i"), {"i": item_id})


# ---------------------------------------------------------------- the match
def match(s: Session, case: Mapping[str, Any], pack: Pack) -> MatchResult:
    """Is the case's asset in the system of record? (module docstring)"""
    rm = _spec(pack)
    if rm is None:
        return MatchResult(False, "", None, None, "The pack has no system of record.")
    src, name = str(rm["source_type"]), system_name(s, str(rm["source_type"]))
    model, _, fld = str(rm["field"]).partition(".")
    row = s.execute(
        text(
            "SELECT c.data, (SELECT max(p.fetched_at) FROM provenance p WHERE p.model = c.model AND p.key = c.key "
            "AND p.field = :f AND p.source_id = :s) AS synced FROM canonical c WHERE c.model = :m AND c.key = :k"
        ),
        {"m": model, "k": case.get("assetId"), "f": fld, "s": src},
    ).first()
    if row is None or row.data.get(fld) in (None, "") or row.synced is None:
        return MatchResult(False, name, None, None, f"{name} holds no {fld} for {case.get('assetId')}.")
    tenant = row.data.get("owner_tenant")
    if tenant and tenant != case.get("owner"):
        return MatchResult(False, name, None, row.synced, f"{name} has the asset under {tenant}, not {case.get('owner')}.")
    return MatchResult(True, name, str(row.data[fld]), row.synced, f"Found in {name}.")


# ---------------------------------------------------------------- custody
def _now_iso() -> str:
    return clock.now().astimezone(UTC).isoformat()


def _add(case: MutableMapping[str, Any], event: str, source: str | None, location: str | None, by: str) -> None:
    case.setdefault("custody", []).append({"at": _now_iso(), "event": event, "source": source, "location": location, "by": by})


def _located(s: Session, asset_key: Any) -> tuple[str | None, str | None]:
    """The canonical location of the asset and the source that wrote it."""
    loc = s.execute(
        text("SELECT data ->> 'location' FROM canonical WHERE model = 'asset' AND key = :k"), {"k": asset_key}
    ).scalar()
    src = s.execute(
        text(
            "SELECT source_id FROM provenance WHERE model = 'asset' AND key = :k AND field = 'location' "
            "ORDER BY fetched_at DESC LIMIT 1"
        ),
        {"k": asset_key},
    ).scalar()
    return loc, src


def receive(s: Session, case: MutableMapping[str, Any], by: str) -> None:
    """Custody "received": the asset arrived, where the case says it is (a non-industrial case that has none yet)."""
    if case.get("template") in (None, "industrial") or case.get("custody"):
        return
    if _carried(s, case):
        return
    _, src = _located(s, case.get("assetId"))
    _add(case, "received", src, case.get("location"), by)


def _carried(s: Session, case: MutableMapping[str, Any]) -> bool:
    """A source that carries the chain of custody itself (`asset.custody`, the ITAD logistics, P9-12.2): its events, in its
    order, with that source, become the case's custody. True when it had some."""
    row = s.execute(
        text(
            "SELECT c.data -> 'custody' AS ev, (SELECT p.source_id FROM provenance p WHERE p.model = 'asset' AND p.key = c.key "
            "AND p.field = 'custody' ORDER BY p.fetched_at DESC LIMIT 1) AS src FROM canonical c "
            "WHERE c.model = 'asset' AND c.key = :k"
        ),
        {"k": case.get("assetId")},
    ).first()
    if row is None or not isinstance(row.ev, list) or not row.ev:
        return False
    events = row.ev
    for e in events:
        case.setdefault("custody", []).append(
            {"at": e.get("at"), "event": e.get("event"), "source": row.src, "location": case.get("location"), "by": e.get("by")}
        )
    return True


def released(case: MutableMapping[str, Any], by: str = "system") -> None:
    """Custody "released": a gate hold cleared."""
    if case.get("custody") is not None:
        last = case["custody"][-1] if case["custody"] else {}
        _add(case, "released", None, last.get("location"), by)


def _moved(s: Session, case: MutableMapping[str, Any], by: str) -> None:
    """Custody "moved" when the canonical location differs from the last entry's."""
    custody = case.get("custody")
    if not custody:
        return
    loc, src = _located(s, case.get("assetId"))
    if loc and loc != custody[-1].get("location"):
        _add(case, "moved", src, loc, by)


# ---------------------------------------------------------------- the check on a case
def _open_item(s: Session, case_id: str, type_id: str) -> int | None:
    row = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id LIMIT 1"),
        {"c": case_id, "t": type_id},
    ).scalar()
    return int(row) if row is not None else None


def _open_exception(s: Session, case: Mapping[str, Any], pack: Pack, res: MatchResult) -> None:
    """The case's one `not_in_system_of_record` item, opened for the pack's owner with the pack's `exception` SLA."""
    cid = str(case["id"])
    tid = type_id(pack, "extra")
    if _open_item(s, cid, tid) is not None:
        return
    kind = _type(pack, tid)
    item = process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=tid,
        title=f"{cid} is not in {res.source}", cause=res.reason,
        action=(kind.action if kind and tid != NOT_IN_RECORD else f"Check the serial in {res.source}, or correct the asset key"),
        owner_role=_role(pack, kind), due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip
    _critical(s, pack, item, tid)


def check(s: Session, case: MutableMapping[str, Any], pack: Pack, by: str = "system") -> None:
    """Match the case (on open and on every re-check; the module docstring says what changes). In the caller's transaction."""
    if pack.key == "industrial":
        return
    _moved(s, case, by)
    spec = _spec(pack)
    if spec is None:
        return
    res, prev = match(s, case, pack), case.get("recordMatch")
    cid = str(case["id"])
    if res.found:
        synced = res.synced_at.isoformat() if res.synced_at else None
        case["recordMatch"] = {"found": True, "source": res.source, "key": res.key, "syncedAt": synced}
        if isinstance(prev, dict) and prev.get("since"):
            case["recordMatch"]["since"] = prev["since"]
        if isinstance(prev, dict) and prev.get("found") is False:
            _add(case, "matched", str(spec["source_type"]), (case.get("custody") or [{}])[-1].get("location"), by)
        if (item := _open_item(s, cid, type_id(pack, "extra"))) is not None:
            process.close_item(s, item, f"Found in {res.source}", by)
        return
    since = prev["since"] if isinstance(prev, dict) and prev.get("found") is False and prev.get("since") else _now_iso()
    case["recordMatch"] = {"found": False, "source": res.source, "since": since}
    _open_exception(s, case, pack, res)
    if spec.get("mode") == "hold":
        case["recommendation"] = None


# ---------------------------------------------------------------- the job at the end of a sync
def _case_ids(s: Session, template: str) -> list[str]:
    return list(
        s.execute(
            text(
                "SELECT id FROM case_record WHERE data ->> 'template' = :t AND stage <> 'closed' "
                "AND data -> 'recordMatch' ->> 'found' = 'false' ORDER BY id"
            ),
            {"t": template},
        ).scalars()
    )


def _recheck(s: Session, case_id: str, template: str, report: ReconcileReport) -> None:
    from di.services.cases import intake  # intake imports this module

    c = store.get(s, case_id, for_update=True)
    if c is None:
        return
    pack = intake.active_pack(s, template, c["owner"])
    if match(s, c, pack).found:
        if (_spec(pack) or {}).get("mode") == "hold" and c["stage"] in ("none", "awaiting_approval"):
            intake.revalue(s, c)  # valued again: it had no recommendation while it was held
        else:
            check(s, c, pack)
        store.save(s, c)
        report.matched.append(case_id)
    else:
        check(s, c, pack)
        store.save(s, c)
        report.extra.append(case_id)


def _asset_time(row: Any) -> datetime:
    got = row.data.get("received_at")
    if isinstance(got, str):
        try:
            t = datetime.fromisoformat(got)
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        except ValueError:
            pass
    return row.synced


def _missing(s: Session, source_id: str, pack: Pack, report: ReconcileReport) -> None:
    """Assets of the source the system says are on their way back, with no case after the pack's wait: one item each."""
    days = float((_spec(pack) or {}).get("missing_after_days", 2))
    rows = s.execute(
        text(
            "SELECT c.key, c.data, (SELECT max(p.fetched_at) FROM provenance p WHERE p.model = 'asset' AND p.key = c.key "
            "AND p.source_id = :s) AS synced FROM canonical c WHERE c.model = 'asset' "
            "AND c.data ->> 'disposition' = ANY(:d) AND EXISTS (SELECT 1 FROM provenance p WHERE p.model = 'asset' "
            "AND p.key = c.key AND p.source_id = :s) ORDER BY c.key"
        ),
        {"s": source_id, "d": list(ON_THE_WAY)},
    ).all()
    tid = type_id(pack, "missing")
    kind, now = _type(pack, tid), clock.now()
    for r in rows:
        title = f"{r.key} was expected back and has no case"
        has_case = s.execute(text("SELECT 1 FROM case_record WHERE data ->> 'assetId' = :k LIMIT 1"), {"k": r.key}).first()
        if has_case:
            s.execute(  # the unit arrived: its item is done
                text(
                    "UPDATE work_item SET status = 'done', outcome = 'A case is open', closed_by = 'system', closed_at = :n "
                    "WHERE type = :t AND title = :ti AND status = 'open'"
                ),
                {"n": now, "t": tid, "ti": title},
            )
            continue
        if now - _asset_time(r) < timedelta(days=days):
            continue
        report.missing.append(r.key)
        seen = s.execute(text("SELECT 1 FROM work_item WHERE type = :t AND title = :ti LIMIT 1"), {"t": tid, "ti": title}).first()
        if seen:
            continue  # opened before (open, or resolved by a person): not again
        org = r.data.get("owner_tenant")
        known = s.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": org}).first() if org else None
        item = process.open_item(
            s, kind="exception", case_id=None, org_unit_id=org if known else None, type=tid, title=title,
            cause=f"{system_name(s, source_id)} lists {r.key} as {r.data.get('disposition')}; no case has been opened for it",
            action=kind.action if kind else "Find the unit or confirm it was not returned",
            owner_role=_role(pack, kind), due_hours=pack.runtime.sla_hours.get("exception"), by="system",
        )  # fmt: skip
        _critical(s, pack, item, tid)


def reconcile(s: Session, source_id: str) -> ReconcileReport:
    """The end of a sync of the source (module docstring): the cases still not found are `extra` and stay with their
    exception; the ones now found are `matched`; the assets expected back with no case are `missing`. In the caller's
    transaction."""
    report = ReconcileReport()
    for key, pack in _record_packs(s, source_id):
        for cid in _case_ids(s, key):
            _recheck(s, cid, key, report)
        _missing(s, source_id, pack, report)
    report.missing = sorted(dict.fromkeys(report.missing))
    return report


# ---------------------------------------------------------------- the screen
def view(case: Mapping[str, Any], pack: Pack) -> dict[str, Any] | None:
    """The case page's `recordMatch`: found, the system's name, the record's key and how long ago it synced (minutes by the
    workspace clock), or the owner the exception went to. None for a case of a pack with no system of record."""
    rm = case.get("recordMatch")
    if not isinstance(rm, dict):
        return None
    out: dict[str, Any] = {"found": bool(rm.get("found")), "system": rm.get("source"), "key": rm.get("key"),
                           "syncedAt": rm.get("syncedAt"), "since": rm.get("since"), "owner": None}  # fmt: skip
    if rm.get("syncedAt"):
        out["syncedMinutesAgo"] = max(0, int((clock.now() - datetime.fromisoformat(rm["syncedAt"])).total_seconds() // 60))
    if not out["found"]:
        out["owner"] = _role(pack, _type(pack, type_id(pack, "extra")))
    return out
