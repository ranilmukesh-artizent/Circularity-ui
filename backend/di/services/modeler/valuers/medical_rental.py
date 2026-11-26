"""The medical rental valuer (plan 9, P9-11.8, story MR-08; registry entry I-21: `VALUERS["medical_rental"]`). It prices what a
returned rental device can do next, on one basis (relative to keeping the device idle): re-rent to each open request of its
class, service then re-rent, refurbish, retire.

    value_routes(facts, pack, as_of) -> list[PathValue]

Facts it reads (the case as the decider holds it; a fact it lacks makes the routes that need it not ok, with the field in
`misses`): `cls` (device class), `age_years`, `book_value`, `residual_sale_value`, `repair_estimate`, `harvest_values`
([{harvest_value}], the parts portal), `rentalRequests` ([{req_id, hospital_id, hospital?, start_date, days, distance_miles}],
the rental system; `distance_miles` is what the case's request list must carry for the transport cost).
Every number is the pack's `valuer.params.params` (rates, per-mile cost, preparation, PM kit and hours, refurbishment, disposal),
read at call time so a changed pack changes the values; the pack is never modified.

Routes, in this order: `rerent:<req id>` per request (best net first, ties by transport cost, then distance, then request
order: the "least travel" rule is inside the value, not a route), `service_rerent`, `refurbish`, `retire`. A device with no
request has one `rerent` and its `service_rerent` not ok. `dest` is {name, distance?, start?, days?, confidence} on every
route. Never does: read a session or the clock, write anything, decide a gate (a gate's result fails routes after the
valuer, `apply_gate_results`), or explain: wording of a recommendation is the agents' job (R16), the numbers are code.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from di.services.modeler.pack import Pack
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

# How sure each route's figures are: a request is a named demand; a service or refurbishment rests on estimates; a sale value
# and a harvest list rest on the asset system and the parts portal. Information on the route, never an input to a net.
CONFIDENCE = {"rerent": 0.9, "service_rerent": 0.8, "refurbish": 0.7, "retire": 0.85}
LOW = 0.6  # a figure the facts did not carry (the pack's default is used)
LABEL = {"rerent": "Re-rent", "service_rerent": "Service then re-rent", "refurbish": "Refurbish", "retire": "Retire"}


def _by_class(table: Mapping[str, Any], cls: Any) -> float:
    return float(table.get(cls, table.get("default", 0)))


def _line(type_: str, label: str, basis: str, amt: float, kind: str) -> ValueLine:
    return {"type": type_, "label": label, "basis": basis, "amt": amt, "kind": kind}


def _value(k: str, lines: list[ValueLine], dest: dict[str, Any], *, ok: bool = True, why: str = "",
           misses: tuple[str, ...] = ()) -> PathValue:  # fmt: skip
    t = {x: sum(ln["amt"] for ln in lines if ln["type"] == x) for x in ("v", "c", "h")}
    return {
        "k": k, "ok": ok, "gross": t["v"], "cost": t["c"], "hold": t["h"], "net": t["v"] - t["c"] - t["h"], "why": why,
        "lines": lines, "dest": dest, "misses": list(misses), "co2": None, "co2Prov": None,
    }  # fmt: skip


def _not_ok(k: str, why: str, *misses: str) -> PathValue:
    return _value(k, [], {"name": LABEL[k], "confidence": CONFIDENCE[k]}, ok=False, why=why, misses=misses)


def _requests(facts: Mapping[str, Any], p: Mapping[str, Any], rate: float) -> list[PathValue]:
    out = []
    for q in facts.get("rentalRequests") or []:
        miles = float(q.get("distance_miles") or 0)
        days = float(q.get("days") or 0)
        transport = miles * p["transport_per_mile"]
        who = q.get("hospital") or q.get("hospital_id") or q.get("req_id")
        out.append(_value(
            f"rerent:{q.get('req_id')}",
            [
                _line("v", "Rental income", f"{days:g} days at {rate:g} a day", rate * days, "lease"),
                _line("c", "Transport", f"{miles:g} miles at {p['transport_per_mile']:g}", transport, "fees"),
                _line("c", "Preparation", "per rental", p["prep_cost"], "prep"),
            ],
            {"name": f"Re-rent · {who}", "distance": miles, "start": q.get("start_date"), "days": days,
             "confidence": CONFIDENCE["rerent"]},
        ))  # fmt: skip
    out.sort(
        key=lambda v: (-round(v["net"], 6), v["lines"][1]["amt"], (v["dest"] or {})["distance"])
    )  # least travel: transport cost
    return out


def value_routes(facts: Mapping[str, Any], pack: Pack, _as_of: datetime | None = None) -> list[PathValue]:
    """The four routes of the module docstring for the device the facts describe."""
    p = pack.valuer.params["params"]
    cls = facts.get("cls")
    rate = p["daily_rate"].get(cls)
    reqs = _requests(facts, p, float(rate)) if rate is not None else []
    out: list[PathValue] = list(reqs)
    if rate is None:
        why = f"No daily rate for the device class {cls}" if cls else "The device class is not known"
        out += [_not_ok("rerent", why, "cls"), _not_ok("service_rerent", why, "cls")]
    elif not reqs:
        why = "No open rental request for this device class"
        out += [_not_ok("rerent", why), _not_ok("service_rerent", why)]
    else:
        best = reqs[0]  # service then re-rent serves the best request, after the service days
        best_dest = dict(best["dest"] or {})
        income = best["gross"] - best["lines"][1]["amt"]
        repair = float(facts.get("repair_estimate") or 0)
        kit = _by_class(p["pm_kit"], cls)
        service = (
            _line("c", "Repair", "the biomedical estimate", repair, "prep")
            if repair > 0
            else _line("c", "PM kit and labour", f"{p['pm_hours']:g} hours at {p['service_labour_per_hour']:g} plus the kit",
                       kit + p["pm_hours"] * p["service_labour_per_hour"], "prep")
        )  # fmt: skip
        out.append(
            _value(
                "service_rerent",
                [
                    _line("v", "Rental income", f"{best_dest['name']}, net of transport", income, "lease"),
                    _line("c", "Preparation", "per rental", p["prep_cost"], "prep"),
                    service,
                    _line(
                        "c", "Rental days lost", f"{p['service_days']:g} days at {rate:g} a day", p["service_days"] * rate, "risk"
                    ),
                ],
                {**best_dest, "name": f"Service then {best_dest['name']}", "confidence": CONFIDENCE["service_rerent"]},
            )
        )
    out.append(_refurbish(facts, p, cls, rate))
    out.append(_retire(facts, pack, p, cls))
    return out


def _refurbish(facts: Mapping[str, Any], p: Mapping[str, Any], cls: Any, rate: float | None) -> PathValue:
    age = facts.get("age_years")
    if age is None:
        return _not_ok("refurbish", "The device's age is not known", "age_years")
    if age < p["refurb_min_age_years"]:
        return _not_ok("refurbish", f"Not considered: device under {p['refurb_min_age_years']:g} years")
    if rate is None:
        return _not_ok("refurbish", "No daily rate for the device class", "cls")
    return _value(
        "refurbish",
        [
            _line("v", "Extra years in service", f"{p['refurb_extra_years']:g} years at the annual margin",
                  p["refurb_extra_years"] * _by_class(p["annual_margin"], cls), "lease"),
            _line("c", "Refurbishment", "the class cost", _by_class(p["refurb_cost"], cls), "prep"),
            _line("h", "Downtime", f"{p['refurb_downtime_days']:g} days at {rate:g} a day",
                  p["refurb_downtime_days"] * rate, "fees"),  # fmt: skip
        ],
        {"name": LABEL["refurbish"], "confidence": CONFIDENCE["refurbish"]},
    )  # fmt: skip


def _retire(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], cls: Any) -> PathValue:
    book = facts.get("book_value")
    if book is None:
        return _not_ok("retire", "The device's book value is not known", "book_value")
    sale = float(facts.get("residual_sale_value") or 0)
    parts = sum(float(h.get("harvest_value") or 0) for h in facts.get("harvest_values") or [])
    known = facts.get("residual_sale_value") is not None or bool(facts.get("harvest_values"))
    lines = [
        _line("v", "Residual sale" if sale >= parts else "Harvested parts", "the higher of sale and parts", max(sale, parts),
              "sale" if sale >= parts else "parts"),
        _line("v", "Service avoided", "12 months", _by_class(p["service_avoided_12m"], cls), "prep"),
        _line("c", "Book value written off", "asset record", float(book), "risk"),
        _line("c", "Disposal fee", "per device", p["disposal_fee"], "fees"),
    ]  # fmt: skip
    cl = next((c for c in pack.classes if c.id == cls), None)
    if cl is not None and cl.attrs.patient_data:
        lines.append(_line("c", "Data sanitisation", "patient-data class", p["sanitisation_cost"], "fees"))
    return _value("retire", lines, {"name": LABEL["retire"], "confidence": CONFIDENCE["retire"] if known else LOW})
