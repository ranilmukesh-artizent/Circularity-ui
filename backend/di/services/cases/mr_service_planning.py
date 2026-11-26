"""Service planning around regional demand for rental devices (plan 9, P9-11.15, story MR-17).

    pick_week(forecast, as_of, due)       the forecast week of lowest demand that ends today or later and starts by the due date
    suggestions(s, as_of, window_days)    one `SR-MR-SVCWEEK` suggestion per rental case whose device is due for preventive
                                          maintenance or certification within the next rental period
    open_items(s, as_of, window_days)     the same as one open work item per case and week (type `SR-MR-SVCWEEK`), for the owner
                                          role of the pack's operations manager to adopt

A device whose `condition.pm_due` or `certification_expiry` falls within `window_days` of `as_of` (30 by default: the next rental
period; a published `BR-MR-SVC` scope may widen it by the caller) is suggested "Service <tag> in the week of <date> (lowest demand
in <region>)". The week is chosen from the device's `demand.region_forecast` (the depot's region, `{week_start, requests}` per
week): among the weeks that are not over yet and start no later than the due date, the one with the fewest requests, the earlier
on a tie. A device with no forecast, no date in the window or a booked order for the same kind and week is not suggested. The
earlier of the two dates names the kind (`pm` or `certification`).

Adopting is the person's own `service.book` call with the suggestion's `book.input` (`di.services.actions.service_booking`,
Admin, Engineer or Planner; an agent's call is held for a person, I-10). Never does: book, write the case, clear a gate or use a
language model: the week and every date come from the records (R16). Implements the medical half of the suggestion rule
`SR-MR-SVCWEEK` of the pack (registry entry I-4); the device-side ageing rules are `di.services.device.ageing`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.cases import process, store

RULE = "SR-MR-SVCWEEK"
WINDOW_DAYS = 30
TEMPLATE = "medical_rental"
KINDS = (("pm", "pm_due"), ("certification", "certification_expiry"))


@dataclass(frozen=True)
class WeekSuggestion:
    case_id: str
    tag: str
    kind: str  # "pm" or "certification"
    due: str  # the ISO date it falls due
    week: str  # the ISO start of the chosen week
    region: str
    requests: int  # the forecast requests of that week
    text: str
    org_unit_id: str | None

    @property
    def book(self) -> dict[str, Any]:
        return {
            "action": "service.book",
            "input": {"case_id": self.case_id, "asset_tag": self.tag, "kind": self.kind, "due_by": self.week},
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": RULE, "case_id": self.case_id, "tag": self.tag, "kind": self.kind, "due": self.due, "week": self.week,
            "region": self.region, "requests": self.requests, "text": self.text, "book": self.book,
        }  # fmt: skip


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def pick_week(forecast: Sequence[Mapping[str, Any]], as_of: date, due: date) -> tuple[date, int] | None:
    """(start, requests) of the quietest forecast week not over on `as_of` and starting by `due`; None without one."""
    weeks = []
    for w in forecast:
        start = _day(w.get("week_start"))
        if start is not None and start + timedelta(days=6) >= as_of and start <= due:
            weeks.append((int(w.get("requests") or 0), start))
    if not weeks:
        return None
    requests, start = min(weeks)
    return start, requests


def _label(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def _due(cond: Mapping[str, Any], as_of: date, window_days: int) -> tuple[str, date] | None:
    """The earliest of the two dates that falls in [as_of, as_of + window_days], with its kind."""
    hits = [
        (d, k) for k, f in KINDS if (d := _day(cond.get(f))) is not None and as_of <= d <= as_of + timedelta(days=window_days)
    ]
    if not hits:
        return None
    d, k = min(hits)
    return k, d


def suggest_case(s: Session, case: Mapping[str, Any], as_of: date, window_days: int = WINDOW_DAYS) -> WeekSuggestion | None:
    """The suggestion for one rental case's device, or None."""
    key = str(case.get("assetId") or "")
    if case.get("template") != TEMPLATE or not key:
        return None
    cond = ((canonical.get(s, "condition", key) or {}).get("data")) or {}
    due = _due(cond, as_of, window_days)
    forecast = (((canonical.get(s, "demand", key) or {}).get("data")) or {}).get("region_forecast") or []
    if due is None or not forecast:
        return None
    picked = pick_week(forecast, as_of, due[1])
    if picked is None:
        return None
    week, requests = picked
    tag = key.split(":", 1)[-1]
    if any(o.get("asset_tag") == tag and o.get("kind") == due[0] and o.get("due_by") == week.isoformat()
           for o in case.get("serviceOrders") or []):  # fmt: skip
        return None
    region = str(((canonical.get(s, "asset", key) or {}).get("data") or {}).get("depot") or "")
    where = f" in {region}" if region else ""
    return WeekSuggestion(
        str(case["id"]), tag, due[0], due[1].isoformat(), week.isoformat(), region, requests,
        f"Service {tag} in the week of {_label(week)} (lowest demand{where})", case.get("owner"),
    )  # fmt: skip


def suggestions(s: Session, as_of: date, window_days: int = WINDOW_DAYS) -> list[WeekSuggestion]:
    """The suggestions for the open rental cases, the soonest due first."""
    out = [x for c in store.all_cases(s) if (x := suggest_case(s, c, as_of, window_days)) is not None]
    return sorted(out, key=lambda x: (x.due, x.case_id))


def open_items(s: Session, as_of: date, window_days: int = WINDOW_DAYS) -> list[int]:
    """One open work item (type `SR-MR-SVCWEEK`) per case and suggested week that has none yet; the ids opened. In the caller's
    transaction. The item only points at the suggestion: the person books it with `service.book`."""
    ids: list[int] = []
    for x in suggestions(s, as_of, window_days):
        title = f"{x.case_id}: {x.text}"
        if s.execute(
            text("SELECT 1 FROM work_item WHERE type = :t AND case_id = :c AND title = :ti AND status = 'open'"),
            {"t": RULE, "c": x.case_id, "ti": title},
        ).first():
            continue
        ids.append(
            process.open_item(
                s, kind="step", case_id=x.case_id, org_unit_id=x.org_unit_id, type=RULE, title=title,
                cause=f"{x.kind} falls due {x.due}; {x.requests} requests are forecast that week",
                action=f"Book {x.kind} for {x.tag} by {x.week}", owner_role="Planner", due_hours=None, by="system",
            )
        )  # fmt: skip
    return ids
