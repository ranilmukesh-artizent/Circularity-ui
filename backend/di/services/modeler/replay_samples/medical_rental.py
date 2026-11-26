"""The medical rental pack's replay history (plan 9, P9-11.13; story MR-20; registry entries I-16 and I-17): 1,880 rental device
returns decided over the 27 days from 28 October to 23 November 2026, and the 20 percent canary the flow is published to.

    rows() -> list[dict[str, str]]          the history as CSV rows (what `history.import_history` reads), `mulberry32(1606)`
    items(rows, pack, now) -> list[dict]    the rows checked by `import_history`, then each item's facts completed for the decider
    replay(batch, items, flow_ver, pack, runner) -> (ReplayReport, figures)    the replay and its `modelled` figures
    figures(report) -> dict                 the four figures of the pack's replay part, each labelled `modelled`
    CANARY                                  the publish step: version 1.0 to the East region at 20 percent

Owns: the invented history and the way a row becomes the case the decider reads. A row holds scalar facts only (CSV cannot hold a
list): the device's age and money, whether a decontamination record exists, the days left on its certification and preventive
maintenance, whether a field safety notice is open, and the nearest rental request (miles, days,
start). `items` turns them into what the gates and the valuer read: the case's `evidenceRecords` (decontamination, service
record, field safety status and servicing assessment) and its `rentalRequests`, with every
record dated before the decision (a replay uses only facts known at the time). The shares below are tuned so the figures of
the pack's replay part hold; the replay code is never touched for that.
Never does: read a clock, a database or a file, or run a replay itself (`replay` takes the runner, di.services.replay.run.replay,
as an argument: the Modeler's policy core is pure and may not import it). No row holds a name, an address or any patient data:
every value is invented. Publishing and widening a canary stay a person's (maker-checker, `rollout.` in
di.services.agents.forbidden): `CANARY` is only the step's settings.

Figures, per business day (Monday to Friday, `measures.business_days`: 19 for these 27 days): approvals are repairs over the
AP-MR-REPAIR limit, exceptions are devices held by a gate (no decontamination record, an open field safety notice); a
further share is neither (a unit whose certification ends during every request, G-MED-SVC, needs another unit and no
person's approval), which is why the straight-through share is 83 percent while approvals and exceptions add up to about 12
a day (the spec's 17 percent held over 27 calendar days, but the measures count business days). Utilisation is the change
in device-days on rent / device-days available when the devices decided straight through turn round in the pack's flow
turnaround (1.6 days) instead of the history's (2.9). Every figure is a counterfactual estimate, so `modelled`.
"""

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from di.services.modeler.pack import Pack
from di.services.modeler.valuers.rng import mulberry32

SEED = 1606
DEVICES = 1880
FIRST_DAY = date(2026, 10, 28)
DAYS = 27  # 28 October to 23 November
YOUNG_RETIRED = 11  # MR-11: retired devices under 5 years old
COMMAND = "python -m di.services.modeler.replay_samples.medical_rental"

# The mix of the fleet: (class, share, oldest age in years, new price used for book value)
CLASSES: tuple[tuple[str, float, int, int], ...] = (
    ("infusion_pump", 0.38, 9, 2400),
    ("patient_monitor", 0.17, 9, 5200),
    ("electric_bed", 0.14, 12, 3600),
    ("syringe_driver", 0.12, 8, 1700),
    ("transport_ventilator", 0.06, 9, 9000),
    ("pulse_oximeter", 0.13, 8, 700),
)
# Shares of the history; tuned until the figures hold (module docstring).
P_NO_DECON = 0.0480  # no decontamination record at the decision: held, an exception
P_NOTICE = 0.0060  # an open field safety notice: held, an exception
P_REPAIR = 0.0710  # a repair estimate over the $1,000 limit: an approval
P_SHORT = 0.0520  # certification ends during every request: another unit goes, no approval
P_RETIRE = 0.0660  # the depot retired it
P_REFURB = 0.0380  # the depot refurbished it
P_SERVICE = 0.1500  # the depot serviced it first
AGE_SKEW = 3.5  # the exponent of the age draw (1 would be an even spread of ages)
RENTAL_DAYS = (6, 20)  # the nearest request's days

CANARY = {"version": "1.0", "region_key": "region", "region": "East", "share": 20}
FIGURE_NAMES = ("straight_through_pct", "approvals_per_day", "exceptions_per_day", "utilisation_points")
HEADERS = (
    "item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "market",
    "fact.age_years", "fact.age_years.at", "fact.book_value", "fact.book_value.at",
    "fact.residual_sale_value", "fact.residual_sale_value.at", "fact.repair_estimate", "fact.repair_estimate.at",
    "fact.decon", "fact.decon.at", "fact.cert_days_left", "fact.cert_days_left.at", "fact.pm_days_left",
    "fact.pm_days_left.at", "fact.fsn", "fact.fsn.at", "fact.request_miles",
    "fact.request_miles.at", "fact.request_days", "fact.request_days.at", "fact.request_in_days",
    "fact.request_in_days.at", "fact.requests", "fact.requests.at",
)  # fmt: skip
FACTS = tuple(h[5:] for h in HEADERS if h.startswith("fact.") and not h.endswith(".at"))


def request_spec(start_in: int, rental: int, n: int) -> list[tuple[int, int]]:
    """(days from the decision to the start, rental days) of each of the `n` requests of a device: the first is the nearest, the
    others start a little later and are shorter, so the best one leads clearly and the choice needs no person."""
    return [(start_in + 2 * k, rental if k == 0 else max(3, rental // 3)) for k in range(n)]


class _Draw:
    """The seeded draws, in one fixed order per device."""

    def __init__(self) -> None:
        self.next = mulberry32(SEED)

    def between(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.next()

    def whole(self, lo: int, hi: int) -> int:
        return lo + int(self.next() * (hi - lo + 1))

    def below(self, p: float) -> bool:
        return self.next() < p

    def pick(self, weights: Sequence[float]) -> int:
        x, acc = self.next() * sum(weights), 0.0
        for k, w in enumerate(weights):
            acc += w
            if x < acc:
                return k
        return len(weights) - 1


def _money(x: float) -> str:
    return f"{x:.2f}"


def _device(d: _Draw, k: int) -> dict[str, Any]:
    cls, _, oldest, price = CLASSES[d.pick([c[1] for c in CLASSES])]
    age = int((oldest + 1) * d.next() ** AGE_SKEW)  # a rental fleet is young: few devices are 6 or older
    book = round(price * max(0.1, 1 - 0.11 * age) * d.between(0.9, 1.1), 2)
    sale = round(book * d.between(0.2, 0.45), 2)
    repair = round(d.between(1050, 2400), 2) if d.below(P_REPAIR) else round(d.between(0, 640), 2) if d.below(0.3) else 0.0
    held = d.next()
    decon = "none" if held < P_NO_DECON else "ok"
    notice = "open" if P_NO_DECON <= held < P_NO_DECON + P_NOTICE else "clear"
    short = d.below(P_SHORT)
    nearest = round(d.between(4, 55), 1)
    rental = d.whole(*RENTAL_DAYS)
    start_in = d.whole(3, 9)
    n_requests = d.whole(1, 3)
    first_end = min(a + b for a, b in request_spec(start_in, rental, n_requests))
    cert = d.whole(0, first_end - 1) if short else d.whole(220, 700)  # ends before every request does
    pm = d.whole(150, 360)
    return {
        "class": cls, "age": age, "book": book, "sale": sale, "repair": repair, "decon": decon, "notice": notice,
        "short": short, "nearest": nearest, "rental": rental, "start_in": start_in, "cert": cert, "pm": pm,
        "requests": n_requests, "k": k,
    }  # fmt: skip


def _route(d: _Draw, dev: Mapping[str, Any]) -> str:
    """The route the depot took. Retiring a device under 5 years old is not drawn here: the 11 of MR-11 are set after."""
    age = int(dev["age"])
    r_retire = d.below(P_RETIRE) and age >= 5
    r_refurb = d.below(P_REFURB) and age >= 6
    r_service = d.below(P_SERVICE)
    return "retire" if r_retire else "refurbish" if r_refurb else "service_rerent" if r_service else "rerent"


def _realised(d: _Draw, route: str, dev: Mapping[str, Any]) -> float:
    base = {"rerent": 520.0, "service_rerent": 400.0, "refurbish": 300.0, "retire": 150.0}[route]
    return round(base * d.between(0.55, 1.4) * (0.7 + 0.3 * float(dev["book"]) / 3000), 2)


def rows() -> list[dict[str, str]]:
    """The 1,880 devices, in date order, as CSV rows. Exactly 11 rows retire a device under 5 years old (MR-11). Twice gives the
    same rows."""
    d = _Draw()
    devs: list[dict[str, Any]] = []
    for k in range(DEVICES):
        dev = _device(d, k)
        dev["route"] = _route(d, dev)
        dev["hour"] = d.whole(7, 17)
        dev["day"] = (k * DAYS) // DEVICES  # about 70 a day, every day of the 27
        dev["realised"] = 0.0
        devs.append(dev)
    young = [x for x in devs if int(x["age"]) < 5 and x["route"] != "retire"]
    for x in devs:  # a retire under 5 years old only where the rule picks it: exactly 11
        if x["route"] == "retire" and int(x["age"]) < 5:
            x["route"] = "rerent"
    step = len(young) // YOUNG_RETIRED
    for j in range(YOUNG_RETIRED):
        young[j * step]["route"] = "retire"
    for x in devs:
        x["realised"] = _realised(d, x["route"], x)
    out: list[dict[str, str]] = []
    for n, x in enumerate(devs, start=1):
        at = datetime.combine(FIRST_DAY + timedelta(days=int(x["day"])), datetime.min.time(), UTC) + timedelta(
            hours=int(x["hour"])
        )
        known = (at - timedelta(hours=1)).isoformat()
        facts = {
            "age_years": str(x["age"]), "book_value": _money(x["book"]), "residual_sale_value": _money(x["sale"]),
            "repair_estimate": _money(x["repair"]), "decon": x["decon"], "cert_days_left": str(x["cert"]),
            "pm_days_left": str(x["pm"]), "fsn": x["notice"], "request_miles": f"{x['nearest']:.1f}",
            "request_days": str(x["rental"]), "request_in_days": str(x["start_in"]), "requests": str(x["requests"]),
        }  # fmt: skip
        row = {
            "item_id": f"MR-H{n:05d}", "class": x["class"], "decided_at": at.isoformat(), "reason": "rental return",
            "actual_route": x["route"], "realised_value": _money(x["realised"]), "market": "US" if n % 4 else "UK",
        }  # fmt: skip
        for name in FACTS:
            row[f"fact.{name}"] = facts[name]
            row[f"fact.{name}.at"] = known
        out.append(row)
    return out


def csv_text(rows_: Sequence[Mapping[str, str]] | None = None) -> str:
    """The history as CSV text, its first line a comment with the command that made it (`COMMAND`)."""
    out = io.StringIO()
    out.write(f"# {COMMAND}\n")
    w = csv.DictWriter(out, fieldnames=list(HEADERS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_ if rows_ is not None else rows())
    return out.getvalue()


# ---------------------------------------------------------------- from a row to the case the decider reads
def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _record(kind: str, source: str, at: datetime, result: str, value: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": kind, "source": source, "at": at.isoformat(), "result": result, "value": dict(value)}


def completed_facts(item: Mapping[str, Any]) -> dict[str, Any]:
    """The item's facts with the structured ones the decider reads added (`evidenceRecords`, `rentalRequests`), each dated at the
    time the row's own facts were known (before the decision)."""
    at: datetime = item["decided_at"]
    f = {k: v["value"] for k, v in (item.get("facts") or {}).items()}
    known = max((v["at"] for v in (item.get("facts") or {}).values()), default=at)
    checked_in, ended = at - timedelta(hours=8), at - timedelta(hours=3)
    today = at.date()
    recs: list[dict[str, Any]] = []
    if f.get("decon") == "ok":
        recs.append(_record("decontamination", "mr_decon", ended,
                            "pass", {"checked_in_at": checked_in.isoformat(), "decon_ended_at": ended.isoformat()}))  # fmt: skip
    recs.append(_record("service_record", "mr_biomed", known, "pass", {
        "certification_expiry": (today + timedelta(days=int(_num(f.get("cert_days_left"), 365)))).isoformat(),
        "pm_due": (today + timedelta(days=int(_num(f.get("pm_days_left"), 200)))).isoformat(),
    }))  # fmt: skip
    notice = f.get("fsn") == "open"
    recs.append(_record("field_safety_status", "mr_assets", known, "fail" if notice else "pass",
                        {"notice_id": "FSN-S001"} if notice else {}))  # fmt: skip
    recs.append(_record("servicing_assessment", "mr_biomed", known, "pass", {"assessment": "routine"}))
    miles = _num(f.get("request_miles"), 20.0)
    spec = request_spec(
        int(_num(f.get("request_in_days"), 5)), int(_num(f.get("request_days"), 14)), int(_num(f.get("requests"), 1))
    )
    requests = [
        {"req_id": f"REQ-{k + 1}", "hospital_id": f"HOSP-{k + 1}", "start_date": (today + timedelta(days=a)).isoformat(),
         "days": b, "distance_miles": round(miles + 11 * k, 1), "ends": (today + timedelta(days=a + b)).isoformat()}
        for k, (a, b) in enumerate(spec)
    ]  # fmt: skip
    return {"evidenceRecords": recs, "rentalRequests": requests}


def items(rows_: Sequence[Mapping[str, str]], pack: Pack, now: datetime) -> list[dict[str, Any]]:
    """The rows checked by `import_history` (a held row is dropped; the sample has none), each item's facts completed for the
    decider. `now` is the time of the import: a decision date after it is held by the check."""
    from di.services.replay import history  # lazy: history reads the pack only, and nothing here may import the run

    ok, _held = history.import_history([dict(r) for r in rows_], pack, now=now)
    for it in ok:
        at = it["decided_at"] - timedelta(hours=1)
        for name, value in completed_facts(it).items():
            it["facts"][name] = {"value": value, "at": at}
    return ok


# ---------------------------------------------------------------- the replay and its figures
def turnaround(pack: Pack) -> tuple[float, float]:
    """(days from return to ready to rent in the history, under the flow): the pack's modelled turnaround trend, 2.9 to 1.6."""
    t = (pack.replay.example or {}).get("turnaround_days") or {}
    return float(t.get("history", 2.9)), float(t.get("flow", 1.6))


def utilisation_points(items_: Sequence[Mapping[str, Any]], straight_pct: float, pack: Pack) -> float:
    """The change in fleet utilisation (device-days on rent / device-days available, the pack's KPI) in points. A device that goes
    back out is on rent for its request's days and idle for its turnaround. In the history every device turns round in the
    history's days; under the flow the devices decided straight through turn round in the flow's days, the rest as before.
    The rental days are the mean of the devices the depot re-rented."""
    rented = [
        float(it["facts"]["request_days"]["value"])
        for it in items_
        if it.get("actual_route") in ("rerent", "service_rerent") and "request_days" in it.get("facts", {})
    ]
    if not rented:
        return 0.0
    days, (before, after) = sum(rented) / len(rented), turnaround(pack)
    used_before = days / (days + before)
    used_after = (straight_pct / 100) * (days / (days + after)) + (1 - straight_pct / 100) * used_before
    return round(100 * (used_after - used_before), 1)


def figures(report: Mapping[str, Any], items_: Sequence[Mapping[str, Any]], pack: Pack) -> dict[str, dict[str, Any]]:
    """The pack's four replay figures from a report (`ReplayReport.model_dump()`): `{name: {value, basis: "modelled"}}`."""
    straight = float(report["straight_through_pct"])
    value = {
        "straight_through_pct": straight,
        "approvals_per_day": float(report["approvals_per_day"]),
        "exceptions_per_day": float(report["exceptions_per_day"]),
        "utilisation_points": utilisation_points(items_, straight, pack),
    }
    return {k: {"value": v, "basis": "modelled"} for k, v in value.items()}


def replay(
    batch: Any, items_: Sequence[Mapping[str, Any]], flow_ver: Any, pack: Pack, runner: Callable[..., Any]
) -> tuple[Any, dict[str, dict[str, Any]]]:
    """(the report, its figures). `runner` is `di.services.replay.run.replay`: the Modeler's pure core does not import it."""
    report = runner(batch, items_, flow_ver, pack=pack)
    return report, figures(report.model_dump(), items_, pack)


if __name__ == "__main__":
    import sys

    sys.stdout.write(csv_text())
