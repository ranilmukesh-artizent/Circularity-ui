"""Turnaround at the rental depots: the records, and the alert `AL-MR-TURNAROUND` (plan 9, P9-11.16, story MR-18).

    read(s, orgs)                         -> (depots, devices)  typed rows from the canonical store (`asset`, from mr_rental)
    alerts(depots, avg_gt, role, action)  -> [Alert]            pure: the depots whose average turnaround is above the limit
    alerts_for(s, orgs, pack)             -> [Alert]            the same over the store, params and owner role from the pack

`AL-MR-TURNAROUND` (pack `runtime.suggestion_rules`, params `avg_turnaround_days_gt` 2.5 and `window_days` 14, owner
`operations_manager`): the average days from return to ready to rent over the last 14 days (the window the rental system's
turnaround rows cover) above the limit at a depot -> one alert "Turnaround slipping at <Depot> depot" for the role the owner maps
to (Planner), action "Move decontamination capacity from a quieter depot". The worked question about it is in
`di.services.questions.medical_rental`, which reads the same typed rows.
Records: each returned device's `asset` fact holds its depot, `checked_in_at` and the `turnaround` object of its depot
(returns, avg_days, by_cause_avg_days, decon_lines, the device's own wait). A depot's returns in the 14 days before its latest
check-in come from the devices' `checked_in_at`. Rows of a unit outside `orgs` are never read (R21); `orgs` None reads all.
Never does: move capacity, write anything, read a clock or call a model; every number comes from the records.
Implements the medical side of registry entry I-4 (rules that run).
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import SHARED_ORG
from di.services.modeler.pack import Pack

ALERT_ID = "AL-MR-TURNAROUND"
QUESTION_ID = "turnaround_by_cause"
WINDOW_DAYS = 14


@dataclass(frozen=True)
class DepotFact:
    depot: str
    returns: int  # returned in the last 14 days
    prior_returns: int  # returned in the 14 days before
    avg_days: float
    by_cause: Mapping[str, float]  # average waiting days: decon_queue, service, transport
    lines: int | None  # decontamination lines, when the source gives them


@dataclass(frozen=True)
class DeviceWait:
    tag: str
    depot: str
    checked_in_on: date
    own_days: float
    waiting: Mapping[str, float]


@dataclass(frozen=True)
class Alert:
    id: str
    to_role: str
    depot: str
    avg_days: float
    text: str
    action: str
    question_id: str = QUESTION_ID

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "to_role": self.to_role, "depot": self.depot, "avg_days": self.avg_days, "text": self.text,
            "action": self.action, "question_id": self.question_id,
        }  # fmt: skip


def depot_label(depot: str) -> str:
    return depot[:1].upper() + depot[1:].lower()


def alerts(depots: Iterable[DepotFact], avg_gt: float, role: str, action: str) -> list[Alert]:
    """One alert per depot above `avg_gt` days, the slowest first."""
    slow = sorted((d for d in depots if d.avg_days > avg_gt), key=lambda d: (-d.avg_days, d.depot))
    return [
        Alert(ALERT_ID, role, d.depot, d.avg_days, f"Turnaround slipping at {depot_label(d.depot)} depot", action) for d in slow
    ]


def _allowed(key: str, orgs: Sequence[str] | None) -> bool:
    return orgs is None or key.partition(":")[0] in (*orgs, SHARED_ORG)


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def read(s: Session, orgs: Sequence[str] | None) -> tuple[list[DepotFact], list[DeviceWait]]:
    """The depots and the returned devices of the org units (and `shared`) from the canonical store."""
    seen: dict[str, Mapping[str, Any]] = {}
    devices: list[DeviceWait] = []
    stamps: dict[str, list[date]] = {}
    rows = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'asset' AND (data ? 'turnaround' OR data ? 'checked_in_at')")
    )
    for key, d in rows:
        t = d.get("turnaround") or {}
        depot, on = str(t.get("depot") or d.get("depot") or ""), _day(d.get("checked_in_at"))
        if not depot or not _allowed(key, orgs):
            continue
        if t:
            seen.setdefault(depot, t)
        if on is not None:
            stamps.setdefault(depot, []).append(on)
            if t.get("own_days") is not None:
                devices.append(
                    DeviceWait(str(d.get("tag") or key.partition(":")[2]), depot, on, float(t["own_days"]),
                               dict(t.get("own_waiting_days") or {}))
                )  # fmt: skip
    depots = []
    for depot, t in sorted(seen.items()):
        latest = max(stamps.get(depot, []), default=None)
        prior = 0
        if latest is not None:
            lo, hi = latest - timedelta(days=2 * WINDOW_DAYS), latest - timedelta(days=WINDOW_DAYS)
            prior = sum(1 for on in stamps[depot] if lo < on <= hi)
        depots.append(
            DepotFact(depot, int(t.get("returns") or 0), prior, float(t.get("avg_days") or 0),
                      dict(t.get("by_cause_avg_days") or {}),
                      int(t["decon_lines"]) if t.get("decon_lines") is not None else None)
        )  # fmt: skip
    return depots, sorted(devices, key=lambda x: (x.depot, x.tag))


def _rule(pack: Pack) -> dict[str, Any]:
    return next((r for r in pack.runtime.suggestion_rules if r.get("id") == ALERT_ID), {})


def alerts_for(s: Session, orgs: Sequence[str] | None, pack: Pack) -> list[Alert]:
    al = _rule(pack)
    depots, _ = read(s, orgs)
    role = pack.roles.get(str(al.get("owner")), "Planner")
    limit = float((al.get("params") or {}).get("avg_turnaround_days_gt", 2.5))
    return alerts(depots, limit, role, str(al.get("action") or "Move decontamination capacity from a quieter depot"))
