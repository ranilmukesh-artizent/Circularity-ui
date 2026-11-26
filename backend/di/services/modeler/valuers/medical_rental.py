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

A request the unit is not in date for (the case's `serviceCheck.requests`, the service gate's result per request, P9-11.7) is not
ok on its route, with the gate's reason, and service then re-rent serves the best request that is: the service window picks the
requests (P9-11.9). Hooks beside `value_routes` (P9-11.9): `evidence_lines(facts, best, pack, as_of)`, the four facts behind a
re-rent, and `approval_holds(facts, pack, values)`, the hold of AP-MR-REPAIR for a repair over the limit.

Routes, in this order: `rerent:<req id>` per request (best net first, ties by transport cost, then distance, then request
order: the "least travel" rule is inside the value, not a route), `service_rerent`, `refurbish`, `retire`. A device with no
request has one `rerent` and its `service_rerent` not ok. `dest` is {name, distance?, start?, days?, confidence} on every
route. Never does: read a session or the clock, write anything, decide a gate (a gate's result fails routes after the
valuer, `apply_gate_results`), or explain: wording of a recommendation is the agents' job (R16), the numbers are code.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from di.services.modeler.evidence import parse_time
from di.services.modeler.pack import Pack
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

# How sure each route's figures are: a request is a named demand; a service or refurbishment rests on estimates; a sale value
# and a harvest list rest on the asset system and the parts portal. Information on the route, never an input to a net.
CONFIDENCE = {"rerent": 0.9, "service_rerent": 0.8, "refurbish": 0.7, "retire": 0.85}
LOW = 0.6  # a figure the facts did not carry (the pack's default is used)
REPAIR_APPROVAL = "AP-MR-REPAIR"  # the guardrail: a repair estimate over its limit goes to the fleet manager
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


def _short(facts: Mapping[str, Any]) -> dict[str, str]:
    """The reason the unit is not in date for a request, by request id (`serviceCheck`, written by the service evidence)."""
    rows = (facts.get("serviceCheck") or {}).get("requests") or []
    return {str(c.get("req_id")): str(c.get("reason")) for c in rows if isinstance(c, Mapping) and not c.get("ok", True)}


def _requests(facts: Mapping[str, Any], p: Mapping[str, Any], rate: float) -> list[PathValue]:
    out = []
    short = _short(facts)
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
            ok=str(q.get("req_id")) not in short, why=short.get(str(q.get("req_id")), ""),
        ))  # fmt: skip
    out.sort(
        key=lambda v: (not v["ok"], -round(v["net"], 6), v["lines"][1]["amt"], (v["dest"] or {})["distance"])
    )  # the requests the service window covers first, then the best value, then the least travel: transport cost
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
        best = next((q for q in reqs if q["ok"]), reqs[0])  # serves the best request the window covers, after the service days
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


def _fact_date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def evidence_lines(facts: Mapping[str, Any], best: PathValue | None, _pack: Pack, as_of: datetime | None = None) -> list[str]:
    """The plain facts behind a re-rent, for the request the best route serves: "<hospital> <distance> miles, request date
    <date>", "Service due <date>, after the rental ends <date>" ("before" when it falls due first), "Certification to <date>"
    and "Decontaminated <hours> h ago" (needs `as_of`: the valuer reads no clock). A line is left out when its facts are
    missing. Never a number the valuer did not compute."""
    if best is None or not best["k"].startswith("rerent:"):
        return []
    req = next((q for q in facts.get("rentalRequests") or [] if f"rerent:{q.get('req_id')}" == best["k"]), None)
    if req is None:
        return []
    out: list[str] = []
    miles = req.get("distance_miles")
    who = req.get("hospital") or req.get("hospital_id")
    asked = _fact_date(req.get("requested_at") or req.get("start_date"))
    if miles is not None and who and asked:
        out.append(f"{who} {float(miles):g} miles, request date {asked.isoformat()}")
    read = facts.get("serviceRead") or {}
    due, cert = _fact_date(read.get("pmDue")), _fact_date(read.get("certificationExpiry"))
    end = _fact_date(req.get("ends"))
    first = _fact_date(req.get("start_date"))
    if end is None and first is not None and isinstance(req.get("days"), int | float):
        end = date.fromordinal(first.toordinal() + int(req["days"]))
    if due and end:
        out.append(f"Service due {due.isoformat()}, {'after' if due > end else 'before'} the rental ends {end.isoformat()}")
    if cert:
        out.append(f"Certification to {cert.isoformat()}")
    decon = next((r for r in facts.get("evidenceRecords") or [] if r.get("type") == "decontamination"), None)
    ended = parse_time(decon.get("at")) if decon else None
    if ended is not None and as_of is not None:
        out.append(f"Decontaminated {round(max(0.0, (as_of - ended).total_seconds()) / 3600, 1):g} h ago")
    return out


def _money(v: float) -> Decimal:
    return Decimal(str(round(v, 6))).quantize(Decimal("0.01"), ROUND_HALF_UP)


def approval_holds(facts: Mapping[str, Any], pack: Pack, values: Sequence[PathValue]) -> list[dict[str, Any]]:
    """AP-MR-REPAIR (P9-11.9, story MR-10): a repair estimate over the guardrail's limit (the pack's own value, or the customer's
    stricter one) holds the decision for the owner of the guardrail, the fleet manager, who approves the repair or retires the
    device. The item carries what the person decides on, all computed here: the repair estimate and the limit, the modelled rental
    income over the next period (`utilisation_forecast_days` x `utilisation_rate` x the class's daily rate) and the alternative,
    retire, with its net. [] when there is no estimate, it is within the limit, or the pack has no such guardrail. A person
    approves it (`decision.approve`); an agent only proposes, whatever the headers say."""
    g = next((x for x in pack.guardrails if x.id == REPAIR_APPROVAL and x.param is not None), None)
    repair = facts.get("repair_estimate")
    if g is None or g.param is None or not isinstance(repair, int | float) or isinstance(repair, bool):
        return []
    limit = g.param.value
    if repair <= limit:
        return []
    p = pack.valuer.params["params"]
    rate = p["daily_rate"].get(facts.get("cls"))
    days, use = float(p["utilisation_forecast_days"]), float(p["utilisation_rate"])
    income = None if rate is None else _money(days * use * float(rate))
    retire = next((v for v in values if v["k"] == "retire" and v["ok"]), None)
    who = g.owner.replace("_", " ")
    return [
        {
            "id": g.id, "owner": g.owner, "route": None,
            "reason": f"The repair estimate of ${repair:,.2f} is over the ${limit:,.0f} limit: the {who} approves ({g.id})",
            "repairEstimate": float(repair), "limit": float(limit),
            "income": None if income is None else float(income),
            "incomeBasis": None if rate is None else f"{days:g} days at {use * 100:g}% utilisation at {float(rate):g} a day",
            "alternative": None if retire is None else {"route": "retire", "net": float(_money(retire["net"]))},
        }
    ]  # fmt: skip
