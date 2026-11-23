"""One case, from route drafts to ranked routes and a recommendation.

Two ways in:
- `build_routes(case, predictor)`: the seven standard routes valued by a Predictor, then every gate rule (the demo's
  buildRoutes). Used for a case nobody has hand-modelled.
- `evaluate(case, drafts, rules=...)`: routes whose terms are already known (hand-modelled by a planner, as the demo's
  hero cases are, or as received). The engine computes the net, range, gates, ranks and recommendation.

A draft is a route without its computed fields; a hand-modelled exclusion is given as `preset_fail: (gate, reason)`.

Business rules (a published flow compiled by `di.services.modeler`) run after the gate rules when given; the case
then gains `rulesApplied`, `rulesWaived` and `preferred`. Without them (None) nothing changes.
"""

import copy
import math
from collections.abc import Sequence

from di.services.engine.gates import apply_gate_rules
from di.services.engine.jsmath import js_round
from di.services.engine.predictor import Asset, Predictor
from di.services.engine.routes import Route, fail, mk_route, rank_routes, term
from di.services.modeler.apply import apply_rules
from di.services.modeler.compile import CompiledRule
from di.services.modeler.templates import Template, load_template

COMPUTED = ("gates", "excluded", "failGate", "failReason", "net", "p10", "p90", "rank")


def apply_business(case: dict, routes: list[Route], rules: Sequence[CompiledRule], template: Template | None) -> None:
    """Business rules after the gate rules, in place; the outcome is recorded on the case."""
    out = apply_rules(case, routes, rules, template or load_template("industrial"))
    case["rulesApplied"], case["rulesWaived"], case["preferred"] = out.ids, out.waived, out.preferred


def build_routes(
    case: dict, p: Predictor, rules: Sequence[CompiledRule] | None = None, template: Template | None = None
) -> list[Route]:
    """The demo's buildRoutes: value all seven routes for this asset and apply the gate rules, then any business
    rules (`template`: the pack whose dims scope them, by default `industrial`)."""
    routes = _value_routes(case, p)
    apply_gate_rules(case, routes)
    if rules is not None:
        apply_business(case, routes, rules, template)
    return routes


def _value_routes(case: dict, p: Predictor) -> list[Route]:
    """The seven standard routes valued by the predictor, before any rule."""
    a = Asset(case["cls"], case.get("grade") or "C", case["age"], case.get("qty") or 1)
    dem = case.get("demand") or {}
    q = a.qty
    mv = p.market_value(a)
    routes: list[Route] = []

    # whole-asset resale: as-is, or refurbished first, whichever nets more
    sale, fees = p.sale(a, mv)
    ref_add, ref_cost = p.refurbishment(a, sale)
    as_is = mk_route({
        "id": "resale", "plan": "Sell whole asset as-is",
        "demandLabel": "External buyer · " + ("refurbisher auction" if a.cls == "it" else "dealer network"),
        "demandStatus": "forecast",
        "terms": [term("Expected sale proceeds", sale, "sale"), term("Fees and freight", -fees, "fees"),
                  term("Unsold-risk allowance", -js_round(sale * 0.04), "risk")],
        "unc": "Price, sale timing, unsold risk", "why": "Direct sale; no workshop capacity used", "sigma": 0.14,
    })  # fmt: skip
    refurb = mk_route({
        "id": "resale", "variant": "refurb", "plan": "Refurbish, then sell",
        "demandLabel": "External buyer · higher grade", "demandStatus": "forecast",
        "terms": [term("Expected sale proceeds", sale + ref_add, "sale"), term("Refurbishment", -ref_cost, "prep"),
                  term("Fees and freight", -fees, "fees"),
                  term("Unsold and repair-failure allowance", -js_round(sale * 0.07), "risk")],
        "unc": "Repair success and resulting grade", "why": "Adds value only if grade lift lands", "sigma": 0.2,
    })  # fmt: skip
    best = as_is if as_is["net"] >= refurb["net"] else refurb
    best["refurbDelta"] = refurb["net"] - as_is["net"]
    routes.append(best)

    # redeploy: avoids buying a new unit
    avoid, prep, svc, res = p.avoided_purchase(a), p.prep_cost(a), p.service_cost(a), p.residual(a)
    site = dem.get("site") or "Site 2"
    rd_terms = [term("Avoided equivalent purchase", avoid, "purchase"), term("Preparation and transfer", -prep, "prep"),
                term("Service exposure", -svc, "service"), term("Residual value adjustment", res, "residual")]  # fmt: skip
    if not dem.get("confirmed"):
        rd_terms.append(term("Non-realization allowance", -js_round(avoid * 0.12), "risk"))
    routes.append(mk_route({
        "id": "redeploy", "plan": "Redeploy to " + site,
        "demandLabel": site + " · " + ("confirmed internal need" if dem.get("confirmed") else "forecast replacement"),
        "demandStatus": "confirmed" if dem.get("confirmed") else "forecast", "terms": rd_terms,
        "unc": "Cost and service forecasts", "why": "Avoids purchase; fits duty and due date", "sigma": 0.13,
    }))  # fmt: skip

    # re-lease
    li = p.lease_income(a)
    lease = dem.get("lease")
    routes.append(mk_route({
        "id": "relase", "plan": "Re-lease " + ("to " + lease if lease else "(no prospect)"),
        "demandLabel": "Lease opportunity · pipeline" if lease else "No lease opportunity", "demandStatus": "forecast",
        "terms": [term("Lease income over 30 months", li, "lease"), term("Preparation", -js_round(li * 0.14), "prep"),
                  term("Operating and service costs", -js_round(li * 0.2), "service"),
                  term("Non-realization allowance", -js_round(li * 0.1), "risk")],
        "unc": "Utilisation, service and residual", "why": "Keeps ownership; lower contribution over same horizon",
        "sigma": 0.18,
    }))  # fmt: skip

    # internal recovered-part use
    pv = p.parts_value(a, internal=True)
    routes.append(mk_route({
        "id": "intparts", "plan": "Recover parts for internal use",
        "demandLabel": "Component demand · service stock" if dem.get("parts") else "No component demand",
        "demandStatus": "confirmed" if dem.get("parts") else "forecast",
        "terms": [term("Value of parts consumed internally", pv, "parts"),
                  term("Extraction and testing", -js_round(pv * 0.2), "prep"), term("Logistics", -js_round(pv * 0.07), "fees"),
                  term("Source-asset value lost", -js_round(mv * 0.12), "residual")],
        "unc": "Recovery yield and part consumption", "why": "Recovery is below whole-asset benefit", "sigma": 0.22,
    }))  # fmt: skip

    # external parts sale
    ev = p.parts_value(a, internal=False)
    routes.append(mk_route({
        "id": "extparts", "plan": "Sell parts externally", "demandLabel": "Accepting external buyer",
        "demandStatus": "forecast",
        "terms": [term("Parts sale proceeds", ev, "parts"), term("Extraction and testing", -js_round(ev * 0.16), "prep"),
                  term("Selling and freight", -js_round(ev * 0.12), "fees"),
                  term("Unsold-risk allowance", -js_round(ev * 0.06), "risk")],
        "unc": "Buyer acceptance and qualification", "why": "Below internal use on the same cost basis", "sigma": 0.24,
    }))  # fmt: skip

    # material recovery: the floor value
    mat, proc = p.material(a)
    routes.append(mk_route({
        "id": "material", "plan": "Recover material", "demandLabel": "Certified recycler · spot prices",
        "terms": [term("Metals and recoverable materials", mat, "material"), term("Processing and logistics", -proc, "fees"),
                  term("Disposal cost avoided", js_round(25 * math.sqrt(q)), "avoid")],
        "unc": "Yield and commodity price", "why": "Floor value; lowest uncertainty", "sigma": 0.2,
    }))  # fmt: skip

    # responsible exit: the compliant fallback
    routes.append(mk_route({
        "id": "exit", "plan": "Responsible exit (approved vendor)", "demandLabel": "Approved exit vendor A",
        "terms": [term("Collection", -js_round(20 * math.sqrt(q)), "fees"),
                  term("Processing", -js_round(70 * math.sqrt(q)), "fees"),
                  term("Vendor credit", js_round(30 * math.sqrt(q)), "credit")],
        "unc": "Vendor fees", "why": "Compliant fallback only", "sigma": 0.08,
    }))  # fmt: skip
    return routes


def draft_of(route: Route, keep_exclusion: bool) -> Route:
    """A computed route back to its draft: drop what the engine computes. `keep_exclusion` keeps a hand-modelled
    exclusion as `preset_fail`; without it the gate rules must find the exclusion again."""
    d = {k: copy.deepcopy(v) for k, v in route.items() if k not in COMPUTED}
    if keep_exclusion and route.get("excluded") and route.get("failGate", -1) >= 0:
        d["preset_fail"] = (route["failGate"], route["failReason"])
    return d


def evaluate(
    case: dict,
    drafts: list[Route],
    rules: bool,
    business: Sequence[CompiledRule] | None = None,
    template: Template | None = None,
) -> tuple[list[Route], Route | None]:
    """Route drafts to ranked routes and the recommendation. `rules=True` runs the gate rules (a case valued by
    the formulas); `False` keeps only the hand-modelled exclusions (`preset_fail`), as the demo's hero cases do.
    `business`: rules applied after them; a preferred eligible route then ranks first."""
    routes = []
    for d in drafts:
        d = dict(d)
        preset = d.pop("preset_fail", None)
        r = mk_route(d)
        if preset:
            fail(r, *preset)
        routes.append(r)
    if rules:
        apply_gate_rules(case, routes)
    if business is None:
        return routes, rank_routes(routes, case.get("blocked"))
    apply_business(case, routes, business, template)
    return routes, rank_routes(routes, case.get("blocked"), case["preferred"])
