"""A battery pack valued as its own class (plan 9, P9-3.19, story TF-16). Pure.

    decide(case, params) -> Decision            the four paths of a pack, the same keys as `tool_fleet.Decision`
    gate_facts(case) -> dict                    the case with the `battery` facts the G-BAT gates read
    sample_evidence(soh, at, damaged) -> list   the records of a pack with a read state of health, a safety class, a permit

`params` is the tool-fleet pack's `valuer.params.battery` (its own figures: the pack's price, the state-of-health floors, the
material credit, the hazardous-transport and take-back lines). The case is a mapping: `id`, `cls` "BAT", `soh` (percent, or
None when no state of health has been read), `sohRead` (the date it was read, ISO), `damaged`, `site` and `dem` (the named
orders, as the tool fleet keeps them: `lease` a list, `proj` the pool request or None, `bid` a list, `rcq` the recycler quote).

Rules, in the order the paths are listed (`release`, `redeploy`, `resell`, `exit`; no refurbish and no harvest):
- `release` needs a state of health of at least 80% with a read date and a named fleet order;
- `redeploy` needs at least 70% with a read date and a pool request;
- `resell` needs at least 70% with a read date;
- a damaged pack (`damaged: true`) takes none of those three;
- `exit` (shown as "Take-back recycling") is always possible: value "Material credit (cells)", costs "Hazardous transport
  (lithium-ion, UN 3480)" and "Take-back scheme fee", and "Damaged-battery packaging" for a damaged pack.
A damaged pack takes no standard lane (G-BAT-4), so `resell` says so; the gates (G-BAT-1 state of health, G-BAT-4, G-BAT-5 a
permitted recycler) fail the same paths in `decide_case`, and the flow's business rules act afterwards. Battery regulation per
market is unconfirmed: the gates are marked for Legal's review in the pack.

Never does: use a model (a pack's value is arithmetic on the figures above), read the database or the clock, write a case, or
approve anything. `tool_fleet.CLS` is not changed: the sample world draws exactly what it did.
"""

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from di.services.modeler.valuers.tool_fleet import Decision, PathValue, ValueLine

CLASS = "BAT"
PATHS = ("release", "redeploy", "resell", "exit")
DEFAULT = "exit"  # the standard route of a battery pack: take-back
GATE_IDS = ("G-BAT-1", "G-BAT-4", "G-BAT-5")
DAMAGED_WHY = "Damaged battery transport: a damaged pack takes no standard lane and is not resold"
HAZMAT, FEE, PACKAGING, CREDIT = (
    "Hazardous transport (lithium-ion, UN 3480)", "Take-back scheme fee", "Damaged-battery packaging", "Material credit (cells)",
)  # fmt: skip


def _money(n: float) -> str:
    return ("−" if n < 0 else "") + "$" + f"{round(abs(n)):,}"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _soh(c: Mapping[str, Any]) -> float | None:
    """The state of health to rely on: a reading with a read date; nothing is assumed without one."""
    v = c.get("soh")
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and c.get("sohRead") else None


def gate_facts(case: Mapping[str, Any]) -> dict[str, Any]:
    """The case with `battery` set: a pack is rechargeable (G-BAT-1 reads it) and `damaged` as the case says (G-BAT-4)."""
    return dict(case) | {"battery": {"rechargeable": True, "damaged": bool(case.get("damaged"))}}


def sample_evidence(soh: float, at: datetime, damaged: bool = False) -> list[dict[str, Any]]:
    """The records a pack decided with its gates passing has: the state of health with its read date, the safety class and
    packaging, and a recycler's permit. As case `evidenceRecords`."""
    when = at.isoformat()
    return [
        {
            "type": "battery_soh", "source": "tooltel", "at": when, "result": "pass",
            "value": {"soh_pct": soh, "read_at": when[:10], "damaged": damaged},
        },
        {
            "type": "battery_safety_class", "source": "sample", "at": when, "result": "pass",
            "value": {"class": "UN 3480", "damaged": damaged},
        },
        {"type": "recycler_permit", "source": "sample", "at": when, "result": "pass", "value": {"recycler": "take-back scheme"}},
    ]  # fmt: skip


def decide(case: Mapping[str, Any], params: Mapping[str, Any]) -> Decision:
    """The four paths valued, the best eligible by net, the runner-up, the standard route (take-back) and the uplift over it."""
    values = [_value(case, k, params) for k in PATHS]
    ok = sorted((v for v in values if v["ok"]), key=lambda v: -v["net"])  # stable, like the tool fleet's
    best = ok[0]  # exit is always possible
    dv = next(v for v in values if v["k"] == DEFAULT)
    return {
        "all": values, "best": best, "dk": DEFAULT, "dv": dv, "uplift": best["net"] - dv["net"],
        "second": ok[1] if len(ok) > 1 else None, "rules": [],
    }  # fmt: skip


def _value(c: Mapping[str, Any], k: str, p: Mapping[str, Any]) -> PathValue:
    soh, damaged, dem = _soh(c), bool(c.get("damaged")), c.get("dem") or {}
    lead = p["lead"][k]
    lines: list[ValueLine] = []

    def add(type_: str, label: str, basis: str, amt: float, kind: str) -> None:
        lines.append({"type": type_, "label": label, "basis": basis, "amt": round(amt, 2), "kind": kind})

    def floor_why(floor: float) -> str:
        if soh is None:
            return "No state of health with a read date: the pack is not relied on for this path"
        return f"State of health {soh:g}% is under the {floor:g}% this path needs"

    ok, why, dest, misses = False, "", None, []
    if k == "release":
        floor = p["min_soh"]["release"]
        orders = list(dem.get("lease") or [])
        d = max(orders, key=lambda x: x["rate"] * x["term"], default=None)
        if d:
            mr = p["rate"] / 12
            n = d["term"]
            inc = d["rate"] * (1 - math.pow(1 + mr, -n)) / mr
            add(
                "v",
                f"Fleet order {d['id']} · {d['who']}, {n} months in today's money",
                f"${d['rate']:,} a month × {n} months, discounted at {_pct(p['rate'])} a year",
                inc,
                "lease",
            )
            add("c", "Test and repack", "flat per pack", p["test"], "prep")
            buffer = d["need"] - lead
            dest = {
                **d,
                "ready": lead,
                "buffer": buffer,
                "tr": 0,
                "verb": f"issue to {d['who']} on fleet order {d['id']}",
                "short": f"{d['who']} ({d['id']})",
            }
            if buffer < 0:
                misses.append(f"{d['id']} ({d['who']}) needs it in {d['need']} days; the pack is ready in {lead}")
        ok = bool(d) and soh is not None and soh >= floor and not misses and not damaged
        why = (f"Test, repack and issue to {d['who']} ({d['id']})" if ok and d else DAMAGED_WHY if damaged
               else misses[0] if misses and soh is not None and soh >= floor
               else floor_why(floor) if soh is None or soh < floor else "No open fleet order for this pack")  # fmt: skip
    elif k == "redeploy":
        floor = p["min_soh"]["redeploy"]
        d = dem.get("proj")
        if d:
            add(
                "v",
                f"New pool pack avoided · {d['id']}",
                f"purchase requisition {d['quote']} for 1 new pool pack",
                d["rental"],
                "purchase",
            )
            add("c", "Test and repack", "flat per pack", p["test"], "prep")
            buffer = d["need"] - lead
            dest = {
                **d,
                "ready": lead,
                "buffer": buffer,
                "tr": 0,
                "verb": f"place in the {d['site']} loaner pool ({d['id']})",
                "short": f"pool · {d['site']}",
            }
            if buffer < 0:
                misses.append(f"{d['id']} needs it in {d['need']} days; the pack is ready in {lead}")
        ok = bool(d) and soh is not None and soh >= floor and not misses and not damaged
        why = (f"Place in the {d['site']} loaner pool ({d['id']})" if ok and d else DAMAGED_WHY if damaged
               else misses[0] if misses and soh is not None and soh >= floor
               else floor_why(floor) if soh is None or soh < floor else "No service center pool is short of this pack"
               )  # fmt: skip
    elif k == "resell":
        floor = p["min_soh"]["resell"]
        bids = sorted(dem.get("bid") or [], key=lambda b: -b["price"])
        b = bids[0] if bids else None
        sale = b["price"] if b else p["newP"] * p["res"] * (soh if soh is not None else 0) / 100
        if b:
            add("v", f"Bid {b['id']} · {b['who']}", "firm bid for a tested pack", sale, "sale")
        else:
            basis = f"{_money(p['newP'])} new × {_pct(p['res'])} × {soh if soh is not None else 0:g}% state of health"
            add("v", "Outlet sale (estimate)", basis, sale, "sale")
        add("c", "Test for sale", "flat per pack", p["test"], "prep")
        add("c", "Channel fees", f"{_pct(p['sale_fee'])} of sale price", sale * p["sale_fee"], "fees")
        dest = {
            "kind": "bid" if b else "market", "id": b["id"] if b else "listing",
            "who": b["who"] if b else "pre-owned outlet", "need": 9, "ready": 9, "buffer": 0, "tr": 0,
            "verb": f"sell to {b['who']} ({b['id']})" if b else "list in the pre-owned outlet",
            "short": "bid" if b else "outlet", "committed": bool(b),
        }  # fmt: skip
        ok = not damaged and soh is not None and soh >= floor
        why = (DAMAGED_WHY if damaged else floor_why(floor) if not ok
               else f"Test and sell to {b['who']} on bid {b['id']}" if b
               else f"No live bid; outlet estimate at {soh:g}% state of health")  # fmt: skip
    else:
        add("v", CREDIT, f"recycler quote {dem.get('rcq') or 'on file'}", p["mat"], "material")
        add("c", HAZMAT, "dangerous goods, flat per pack", p["hazmat"], "fees")
        add("c", FEE, "producer take-back scheme", p["fee"], "fees")
        if damaged:
            add("c", PACKAGING, "damaged-pack packaging", p["damaged_pack"], "prep")
        dest = {
            "kind": "exit", "id": dem.get("rcq") or "take-back", "who": "permitted recycler", "name": p["names"]["exit"],
            "need": lead, "ready": lead, "buffer": 0, "tr": 0,
            "verb": "send to the permitted recycler under the take-back scheme", "short": "take-back",
        }  # fmt: skip
        ok, why = True, "Take-back recycling under the producer scheme"
        if damaged:
            why += " (damaged pack, dangerous-goods packaging)"
    add("h", "Holding until done", f"{_money(p['hold'])} a day × {lead} days to complete", p["hold"] * lead, "fees")
    gross = sum(x["amt"] for x in lines if x["type"] == "v")
    cost = sum(x["amt"] for x in lines if x["type"] == "c")
    hold = p["hold"] * lead
    return {
        "k": k, "ok": bool(ok), "gross": gross, "cost": cost, "hold": hold, "net": gross - cost - hold,
        "why": why, "lines": lines,
        "dest": dest, "misses": misses, "co2": None, "co2Prov": None,
    }  # fmt: skip
