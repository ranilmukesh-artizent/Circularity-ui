"""Safety recall register (plan 9, P9-3.2): the recall notices that the tool-fleet pack's gate GR-12 checks a returned
tool against.

    GET {base}/notices

Synthetic, like every mock here. Not a demo source: it is in sim/core/registry.py EXTRA_SYSTEMS (source id `recall`).
API key in `x-api-key` (demo key `recall-demo-key`), offset paging (`items`, `next`, `total`), `?updated_since=` deltas.

Three notices: `RC-2026-014` (CRH serials `CRH-44000` to `CRH-44999`, remedy replace, the brushless motor) and
`RC-2026-017` (BRK serials `BRK-51000` to `BRK-51999`, remedy repair, the impact mechanism) are active; `RC-2026-009`
(DCD, refund, the drill stand) is closed, so a check that reads only active notices has a notice to skip. `affectedParts`
are component names of the pack's class (tool_fleet.json `classes.<cls>.parts`).
"""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

NOTICES = [
    {"recallId": "RC-2026-009", "toolClass": "DCD", "model": "DCD-250 Rig", "serialFrom": "DCD-30000", "serialTo": "DCD-30999",
     "remedy": "refund", "affectedParts": ["Drill stand"], "status": "closed", "publishedAt": "2026-03-02T09:00:00+00:00"},
    {"recallId": "RC-2026-014", "toolClass": "CRH", "model": "CRH-22V Plus", "serialFrom": "CRH-44000", "serialTo": "CRH-44999",
     "remedy": "replace", "affectedParts": ["Brushless motor"], "status": "active", "publishedAt": "2026-08-12T09:00:00+00:00"},
    {"recallId": "RC-2026-017", "toolClass": "BRK", "model": "BRK-30 Heavy", "serialFrom": "BRK-51000", "serialTo": "BRK-51999",
     "remedy": "repair", "affectedParts": ["Impact mechanism"], "status": "active", "publishedAt": "2026-09-18T09:00:00+00:00"},
]  # fmt: skip


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - fixed notices
    return {"notices": [dict(n, affectedParts=list(n["affectedParts"])) for n in NOTICES]}


SPEC = Spec(
    source_id="recall",
    title="Safety recall register (synthetic)",
    schema="recall",
    base_path="/recalls/api",
    auth=Auth("api_key", header="x-api-key"),
    paging=Paging("offset", limit_param="limit", offset_param="offset", items_key="items", next_key="next", total_key="total"),
    resources=(Resource("notices", "/notices", "recallId", filters=("toolClass", "status", "remedy")),),
    seed=seed,
)
