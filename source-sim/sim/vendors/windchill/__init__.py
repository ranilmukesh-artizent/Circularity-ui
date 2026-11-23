"""PTC Windchill mock (plan 8, MVP-9.2): a second PLM system beside Teamcenter, read-only, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `plm_wc`, schema `windchill`),
so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its Windchill adapter
(MVP-9.3), which maps the parts to the canonical `part` model and the structures to `bom` lines.

Windchill REST Services (WRS), ProdMgmt domain, OData v4 under /Windchill/servlet/odata (see routes.py): the Parts
entity set with $top / $skip and server-driven paging, and the bound action PTC.ProdMgmt.GetPartStructure.
Data in Postgres schema `windchill` (models.py, seed.py): 8 assemblies and 40 parts, 5 of them with part numbers of
the Aras mock, so where-used across the two PLM systems is testable.

Documentation followed
    PTC Windchill REST Services documentation (Windchill Help Center, "Windchill REST Services" and its ProdMgmt
        domain): the service root /Windchill/servlet/odata/ProdMgmt, the Parts entity set with the WTPart properties
        ID (the object reference "OR:wt.part.WTPart:<n>"), Number, Name, Version, Iteration and State (an enum type
        with Value and Display), and the bound action PTC.ProdMgmt.GetPartStructure whose result lists, for a part,
        the parts it uses with their quantity. Only the shapes the plan names are served.

Demo credentials: di_connector / Circularity-demo-wc-1 (HTTP Basic).

ASSUMPTION: UnitCost is a soft attribute (IBA) of the customer's part type, a number per unit in the site's currency.
ASSUMPTION: GetPartStructure answers one level (the part and its direct uses), with each used part's current
    version; the navigation criteria in the body are accepted but not applied.
ASSUMPTION: the server's page size is 25 (`@odata.nextLink` carries $skip and the rest of the caller's $top); WRS
    numbers its links with $skiptoken, which a client follows the same way.
ASSUMPTION: the CSRF nonce WRS asks of other POST calls is not checked (GetPartStructure only reads).
ASSUMPTION: fault injection (sim/core/faults.py) covers the demo systems only, so this mock has none.
"""

from sim.core.mock import Mock
from sim.vendors.windchill.routes import router
from sim.vendors.windchill.seed import ensure, reset

MOCK = Mock("plm_wc", router, ensure, reset, "PTC Windchill")
