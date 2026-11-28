"""Analytics: the open decisions by age (plan 11, writer G1), the data of the "ageing" chart.

    GET /api/screens/analytics/open-age?tenant_filter=All&org=
        as_of     the workspace date the ages are counted to (days since each case was received)
        basis     what the value is: the net the recommended route is forecast to recover (modelled, not realised)
        total     {n, value}: every open decision (a live case awaiting approval)
        routes    [{id, name}] the proposed routes present, the reference routes first
        bands     [{key, label, n, value, rows, routes: [{id, name, n, value, rows}]}]: 0 to 7, 8 to 14, 15 to 30 and over 30
                  days; `rows` is the {source, chart, key} that opens the rows behind that number
                  (GET /api/screens/analytics/rows)

Over the same cases as the page's "awaiting approval" count: `visible_cases` (tenant boundary and warehouse lock), the
top bar's tenant filter and the org subtree. Section: pipeline (the route checks it).
"""

from typing import Any

from sqlalchemy.orm import Session

from di.core import clock
from di.core.auth import Principal
from di.repositories.constants import ROUTES
from di.services.screens.analytics_rows import BANDS, Filters, age_records, band_of

BASIS = "forecast net of the recommended route (modelled, not realised)"


def _ref(key: str) -> dict[str, str]:
    return {"source": "cases", "chart": "age", "key": key}


def open_age(session: Session, p: Principal, tenant_filter: str = "All", org: str = "") -> dict[str, Any]:
    recs = age_records(session, p, Filters(tenant_filter=tenant_filter, org=org))
    routes: dict[str, str] = {}
    for r in recs:
        if r["route_id"]:
            routes.setdefault(r["route_id"], r["route_name"])
    rank = {r["id"]: n for n, r in enumerate(ROUTES)}
    ordered = sorted(routes, key=lambda i: (rank.get(i, len(rank)), i))
    bands = []
    for key, label, _ in BANDS:
        inside = [r for r in recs if band_of(r["age"]) == key]
        by_route = []
        for rid in ordered:
            mine = [r for r in inside if r["route_id"] == rid]
            if mine:
                by_route.append(
                    {
                        "id": rid, "name": routes[rid], "n": len(mine), "value": sum(r["net"] or 0 for r in mine),
                        "rows": _ref(f"band:{key}|route:{rid}"),
                    }
                )  # fmt: skip
        bands.append(
            {
                "key": key, "label": label, "n": len(inside), "value": sum(r["net"] or 0 for r in inside),
                "rows": _ref(f"band:{key}"), "routes": by_route,
            }
        )  # fmt: skip
    return {
        "as_of": clock.now().date().isoformat(), "basis": BASIS,
        "total": {"n": len(recs), "value": sum(r["net"] or 0 for r in recs)},
        "routes": [{"id": i, "name": routes[i]} for i in ordered], "bands": bands,
    }  # fmt: skip
