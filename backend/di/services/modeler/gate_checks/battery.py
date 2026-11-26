"""The battery gates (plan 9: P9-10.16 the dangerous-goods lane, story TN-23; P9-12.7 the battery pack, stories NS-BAT-01 to
NS-BAT-03). Pure. Implements the checks of registry entry I-2 for the catalogue gates `G-BAT-1` to `G-BAT-5`; they run before any
business rule (R20).

    check_battery_lane(case, pack, gate) -> GateResult | None   G-BAT-4
    check_soh_read(case, pack, gate) -> GateResult | None       G-BAT-1 (the `battery` pack)
    check_repurpose_fitness(...) -> GateResult | None           G-BAT-2 (the `battery` pack)
    check_passport(...) -> GateResult | None                    G-BAT-3 (the `battery` pack)
    check_recycler_chemistry(...) -> GateResult | None          G-BAT-5 (the `battery` pack)
    case_view(facts) -> dict                                    the `battery` facts the gates read, from a pack's facts

**Equipment with a battery (P9-10.16).** The case's `battery` is the test bench's read of the unit (`chemistry`, `damaged`: the
facts `condition.battery_chemistry` and `condition.battery_damaged`). A unit with no battery fact is left to the gate's
data (None).
  - `chemistry == "lithium"`: every shipping route of the pack takes the dangerous-goods lane. The result fails with effect
    `require_step` and the step `dg_lane`, routes the pack's.
  - `damaged` true as well: `resell` fails "Damaged lithium battery: no resale" (effect `block`, step `dg_lane` kept), and a
    standard lane is refused for the rest by the same step.

**The `battery` pack (P9-12.7).** Its case keeps `battery` = `case_view(...)`: `packId`, `chemistry`, `soh_pct`,
`expected_life_years`, `read_at` (the BMS's read), `thermal_event`, `damaged` (true for a thermal event too), `safety_class`,
`market`, and the flags the catalogue triggers read (`rechargeable`, `waste`, `eu_market`). The four checks leave a case of
another pack to the data (None); the gates' `params.routes` name the routes they act on.
  - G-BAT-1: without `soh_pct`, `expected_life_years` and `read_at` the routes of the gate fail ("State of health and expected
    life not read from the BMS"), so only `recycle` is left; with them the gate passes ("State of health 74% read 2026-11-10").
  - G-BAT-2: `repurpose` needs the evidence `repurpose_fitness` (a pass).
  - G-BAT-3: a pack of a market in `params.markets` needs the step `battery_passport` for the gate's routes on or after
    `params.passport_from` (the case's `gateNow`; a case read without it is judged as after). Before it the gate passes with
    "Battery passport not yet required (from 18 Feb 2027, indicative)" and requires nothing. The date is indicative.
  - G-BAT-4: a damaged or thermal-event pack fails every route but `recycle` ("Damaged or thermal-event pack: dangerous-goods
    lane only, no resale", effect `block`, step `dg_lane`); recycling it goes through that lane.
  - G-BAT-5: `recycle` needs the evidence `recycler_permit` whose `chemistries` include the pack's chemistry.
Never does: read the store or the clock, choose a carrier, or write a case. Reg. (EU) 2023/1542 has been amended (due diligence
moved to 18 Aug 2027 by Reg. 2025/1561), which provisions the ELV Regulation (EU) 2026/1738 changes is unconfirmed, and the
ADR and IATA special provisions are unconfirmed in the pack; the wording needs review by Kinective's Legal team before it is
relied on.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from di.services.modeler.evidence import evidence_of, parse_time
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

BATTERY_GATE = "G-BAT-4"
SOH_GATE, FITNESS_GATE, PASSPORT_GATE, RECYCLER_GATE = "G-BAT-1", "G-BAT-2", "G-BAT-3", "G-BAT-5"
STEP_DG = "dg_lane"
STEP_PASSPORT = "battery_passport"
REASON_DAMAGED = "Damaged lithium battery: no resale"
REASON_LITHIUM = "Lithium battery: dangerous-goods lane only"
REASON_PACK_DAMAGED = "Damaged or thermal-event pack: dangerous-goods lane only, no resale"
REASON_NO_READ = "State of health and expected life not read from the BMS"
REASON_FITNESS = "Repurposing fitness documentation required"
REASON_NO_RECYCLER = "A permitted battery recycler is not on file"
RESELL = "resell"
RECYCLE = "recycle"
PACK_KEY = "battery"
NOW_KEY = "gateNow"  # the time `gate_hold` reads a case at (as the vehicle gates; not imported from the valuers: a cycle)


def case_view(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The `battery` facts of a pack case from its facts (`packId`, `chemistry`, `soh_pct`, `expected_life_years`, `read_at`,
    `thermal_event`, `damaged`, `safety_class`, `market`): a thermal event makes the pack damaged; a pack is
    rechargeable and, at the end of its first life, waste; `eu_market` is whether it is placed on the EU market (the catalogue's
    triggers read these)."""
    thermal = bool(facts.get("thermal_event"))
    return {
        "packId": facts.get("packId"), "chemistry": facts.get("chemistry"), "soh_pct": facts.get("soh_pct"),
        "expected_life_years": facts.get("expected_life_years"), "read_at": facts.get("read_at"), "thermal_event": thermal,
        "damaged": bool(facts.get("damaged")) or thermal, "safety_class": facts.get("safety_class"),
        "market": facts.get("market"), "rechargeable": True, "waste": True, "eu_market": facts.get("market") == "EU",
    }  # fmt: skip


def _pack_case(case: Mapping[str, Any], pack: Pack) -> Mapping[str, Any] | None:
    b = case.get("battery")
    return b if pack.key == PACK_KEY and isinstance(b, Mapping) else None


def _routes(gate: GateDef, pack: Pack, default: tuple[str, ...]) -> tuple[str, ...]:
    """The pack's routes among the ref's `params.routes` (the gate's own default when it names none)."""
    mine = {r.id for r in pack.routes}
    return tuple(r for r in gate.params.get("routes") or default if r in mine)


def check_battery_lane(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-4 (module docstring); None when the case holds no battery fact for a lithium unit."""
    b = case.get("battery")
    if pack.key == PACK_KEY:  # a battery pack: damaged or thermal-event, only the dangerous-goods lane of recycling is left
        if not isinstance(b, Mapping) or not b.get("damaged"):
            return None
        others = tuple(r.id for r in pack.routes if r.id != RECYCLE)
        return GateResult(
            gate.id, False, GateEffect("block", others, False, STEP_DG), (), REASON_PACK_DAMAGED,
            route_reasons=tuple((r, REASON_PACK_DAMAGED) for r in others),
        )  # fmt: skip
    if not isinstance(b, Mapping) or str(b.get("chemistry") or "").lower() != "lithium":
        return None
    routes = tuple(r.id for r in pack.routes)
    if b.get("damaged") is True:
        return GateResult(
            gate.id, False, GateEffect("block", (RESELL,) if RESELL in routes else (), False, STEP_DG), (), REASON_DAMAGED,
            route_reasons=((RESELL, REASON_DAMAGED),),
        )  # fmt: skip
    return GateResult(gate.id, False, GateEffect("require_step", routes, False, STEP_DG), (), REASON_LITHIUM)


def check_soh_read(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-1 (module docstring): the BMS's state of health and expected life, with the read date."""
    b = _pack_case(case, pack)
    if b is None:
        return None
    if any(b.get(k) is None for k in ("soh_pct", "expected_life_years", "read_at")):
        routes = _routes(gate, pack, tuple(r.id for r in pack.routes if r.id != RECYCLE))
        return GateResult(gate.id, False, GateEffect("block", routes, False, None), ("battery_soh",), REASON_NO_READ)
    reason = f"State of health {b['soh_pct']}% read {b['read_at']}"
    return GateResult(gate.id, True, GateEffect("block", (), False, None), (), reason)


def check_repurpose_fitness(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-2 (module docstring): a repurposed pack needs its fitness documentation."""
    if _pack_case(case, pack) is None:
        return None
    e = evidence_of(case, "repurpose_fitness")
    if e is not None and e.result == "pass":
        return GateResult(gate.id, True, GateEffect("block", (), False, None), (), "Repurposing fitness documentation on file")
    routes = _routes(gate, pack, ("repurpose",))
    return GateResult(gate.id, False, GateEffect("block", routes, False, None), ("repurpose_fitness",), REASON_FITNESS)


def _from_text(d: date) -> str:
    return f"{d.day} {d:%b} {d.year}"


def check_passport(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-3 (module docstring): the battery passport step from `params.passport_from` (indicative), for the EU market."""
    b = _pack_case(case, pack)
    if b is None:
        return None
    markets = gate.params.get("markets") or ["EU"]
    start = date.fromisoformat(str(gate.params.get("passport_from") or "2027-02-18"))
    now = parse_time(case.get(NOW_KEY))
    if b.get("market") not in markets or (now is not None and now.date() < start):
        reason = f"Battery passport not yet required (from {_from_text(start)}, indicative)"
        return GateResult(gate.id, True, GateEffect("require_step", (), False, None), (), reason)
    e = evidence_of(case, STEP_PASSPORT)
    if e is not None and e.result == "pass":
        return GateResult(gate.id, True, GateEffect("require_step", (), False, None), (), "Battery passport on file")
    routes = _routes(gate, pack, ("repurpose", "remanufacture"))
    reason = f"Battery passport required (from {_from_text(start)}, indicative)"
    return GateResult(gate.id, False, GateEffect("require_step", routes, False, STEP_PASSPORT), (STEP_PASSPORT,), reason)


def check_recycler_chemistry(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-5 (module docstring): a permitted recycler whose permit covers the pack's chemistry."""
    b = _pack_case(case, pack)
    if b is None:
        return None
    routes = _routes(gate, pack, (RECYCLE,))
    e = evidence_of(case, "recycler_permit")
    if e is None or e.result != "pass":
        return GateResult(gate.id, False, GateEffect("block", routes, False, None), ("recycler_permit",), REASON_NO_RECYCLER)
    chem = str(b.get("chemistry") or "")
    if chem and chem not in [str(c) for c in e.value.get("chemistries") or []]:
        return GateResult(
            gate.id, False, GateEffect("block", routes, False, None), (), f"Recycler's permit does not cover {chem}"
        )
    return GateResult(
        gate.id, True, GateEffect("block", (), False, None), (), f"Permitted recycler on file: {e.value.get('permit_ref')}"
    )


CHECKS[BATTERY_GATE] = check_battery_lane
CHECKS[SOH_GATE] = check_soh_read
CHECKS[FITNESS_GATE] = check_repurpose_fitness
CHECKS[PASSPORT_GATE] = check_passport
CHECKS[RECYCLER_GATE] = check_recycler_chemistry
