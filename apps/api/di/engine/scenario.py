"""What-if: re-rank a case's routes under changed assumptions (the demo's scenRoutes, scenNet and case.whatIf).

Assumptions are multipliers on the kinds of term (purchase price; prep and fees; service; market prices), and
"confirmed demand off" excludes the routes that rely on confirmed demand. Nothing is stored: the approved decision
is unchanged.
"""

from dataclasses import dataclass

from di.engine.jsmath import js_round, js_sum
from di.engine.routes import Route

KIND_MULT = {
    "purchase": "purchase",
    "prep": "cost",
    "fees": "cost",
    "service": "service",
    "sale": "market",
    "parts": "market",
    "material": "market",
    "lease": "market",
}
WHY_DEMAND = "Confirmed demand cancelled in this scenario"
# RT-1052's routes allocate across a pool whose demand lines are locked at pool level, so cancelling one confirmed
# demand line does not remove them (as in the demo)
POOL_LOCKED_CASES = {"RT-1052"}


@dataclass(frozen=True)
class Assumptions:
    purchase: float = 1
    cost: float = 1
    service: float = 1
    market: float = 1
    demand_off: bool = False

    @classmethod
    def of(cls, i: dict) -> "Assumptions":
        # 0 or missing means "unchanged", as in the demo (`i.purchase || 1`)
        return cls(
            i.get("purchase") or 1, i.get("cost") or 1, i.get("service") or 1, i.get("market") or 1,
            bool(i.get("demandOff")),
        )  # fmt: skip

    @property
    def active(self) -> bool:
        return (self.purchase, self.cost, self.service, self.market) != (1, 1, 1, 1) or self.demand_off

    def mult(self, kind: str) -> float:
        name = KIND_MULT.get(kind)
        return (getattr(self, name) or 1) if name else 1


def scenario_net(r: Route, a: Assumptions) -> int:
    return js_round(js_sum(t["amt"] * a.mult(t["kind"]) for t in r["terms"]))


def scenario_routes(case: dict, a: Assumptions) -> tuple[list[dict], list[dict]]:
    """Every route with its scenario net and whether it stays eligible; and the eligible ones ranked."""
    rows = []
    for r in case["routes"]:
        dem = (
            a.demand_off
            and r.get("demandStatus") == "confirmed"
            and r["id"] in ("redeploy", "intparts")
            and case["id"] not in POOL_LOCKED_CASES
        )
        rows.append({
            "r": r,
            "ex": r["excluded"] or dem,
            "why": None if r["excluded"] else (WHY_DEMAND if dem else None),
            "sn": scenario_net(r, a) if a.active else r["net"],
        })  # fmt: skip
    el = sorted((x for x in rows if not x["ex"]), key=lambda x: -x["sn"])
    for i, x in enumerate(el):
        x["rank"] = i + 1
    return rows, el


def what_if(case: dict, i: dict) -> dict:
    """The output of the case.whatIf action."""
    a = Assumptions.of(i)
    rows, el = scenario_routes(case, a)
    _, base_el = scenario_routes(case, Assumptions())
    base, sim = (base_el[0] if base_el else None), (el[0] if el else None)
    out_rows = sorted(
        (
            {"plan": x["r"]["plan"], "base": x["r"]["net"], "sim": x["sn"], "eligible": not x["ex"], "why": x["why"] or ""}
            for x in rows
            if not x["r"]["excluded"]
        ),
        key=lambda z: -z["sim"],
    )

    def pct(v):
        return js_round(((v or 1) - 1) * 100)

    return {
        "case_id": case["id"],
        "assumptions": {
            "purchase": a.purchase,
            "cost": a.cost,
            "service": a.service,
            "market": a.market,
            "demandOff": a.demand_off,
        },
        "pcts": {k: pct(i.get(k)) for k in ("purchase", "cost", "service", "market")},
        "base": {"plan": base["r"]["plan"], "net": base["sn"]} if base else None,
        "sim": {"plan": sim["r"]["plan"], "net": sim["sn"]} if sim else None,
        "rank_changed": bool(base and sim and base["r"] is not sim["r"]),
        "change": sim["sn"] - base["sn"] if base and sim else 0,
        "rows": out_rows,
        "decision_unchanged": True,
    }
