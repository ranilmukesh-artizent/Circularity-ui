"""Connected-tool telematics (plan 9, P9-3.2): run hours, load share and events of the tools that report, for the
remaining-life estimate of the tool-fleet pack.

    GET {base}/tools

Synthetic, like every mock here. Not a demo source: it is in sim/core/registry.py EXTRA_SYSTEMS (source id `tooltel`).
Bearer token from the client-credentials grant at `{base}/oauth/token` (demo client `di-connector`, secret
`tooltel-demo-secret`), offset paging (`items`, `next`, `total`).

One document per connected serial. The serials are the lines of the fleet contract system
(sim/generic/specs/fleet_contracts.py) except 30 that are not connected: they have no document at all. Named fixtures:
`CMH-48213` 820 h, 30% high load, no events, last seen 2026-10-04, 95% coverage; `CMH-48777` last seen 2026-09-29 (eight
days before the anchor 2026-10-07; not a fleet line); `CRH-44120` coverage 80%. `coveragePct` is the share of contract
days with a reading. The data is deterministic (md5) and anchored on 2026-10-07.
"""

from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs import fleet_contracts as fleet
from sim.seed import Seed

h, frac, AS_OF = fleet.h, fleet.frac, fleet.AS_OF
NAMED = {
    "CMH-48213": {"runHours": 820, "highLoadShare": 0.3, "events": (0, 0, 0), "lastSeen": "2026-10-04T08:15:00+00:00", "coveragePct": 95},
    "CMH-48777": {"runHours": 640, "highLoadShare": 0.22, "events": (0, 0, 0), "lastSeen": "2026-09-29T07:40:00+00:00", "coveragePct": 92},
    "CRH-44120": {"runHours": 1240, "highLoadShare": 0.41, "events": (0, 1, 0), "coveragePct": 80},
}  # fmt: skip
NOT_CONNECTED = 30
KEEP = {*NAMED, "BRK-51007", "AGR-20991"}  # the fleet mock's named returned serials stay connected


def _doc(serial: str) -> dict:
    n = NAMED.get(serial, {})
    ov, dr, ol = n.get("events") or (
        int(h("ov", serial) % 9 == 0) * (1 + h("ov2", serial) % 3), int(h("dr", serial) % 7 == 0), int(h("ol", serial) % 8 == 0) * (1 + h("ol2", serial) % 2),
    )  # fmt: skip
    seen = n.get("lastSeen") or (AS_OF - timedelta(days=h("seen", serial) % 3, minutes=h("seenm", serial) % 600)).isoformat()
    return {
        "serial": serial,
        "runHours": n.get("runHours", 150 + h("rh", serial) % 3400),
        "highLoadShare": n.get("highLoadShare", round(0.1 + frac("hl", serial) * 0.5, 2)),
        "events": {"overheat": ov, "drop": dr, "overload": ol},
        "lastSeen": seen,
        "coveragePct": n.get("coveragePct", 85 + h("cov", serial) % 16),
    }


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - anchored on its own date
    serials = [ln["serial"] for ln in fleet.build()["lines"]]
    free = sorted((x for x in serials if x not in KEEP), key=lambda x: h("nc", x))
    off = set(free[:NOT_CONNECTED])
    connected = [x for x in serials if x not in off]
    extra = [x for x in NAMED if x not in connected]
    return {"tools": [_doc(x) for x in (*connected, *extra)]}


SPEC = Spec(
    source_id="tooltel",
    title="Connected-tool telematics (synthetic)",
    schema="tooltel",
    base_path="/tooltel/v2",
    auth=Auth("oauth_cc"),
    paging=Paging("offset", limit_param="limit", offset_param="offset", items_key="items", next_key="next", total_key="total"),
    resources=(Resource("tools", "/tools", "serial"),),
    seed=seed,
)
