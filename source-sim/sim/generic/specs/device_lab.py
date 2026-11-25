"""Device lab (`dvlab`, P9-6.1): trade-in intake, diagnostics, cosmetic grading, photos, data-wipe certificates, parts
declarations, repair quotes and grading disputes for the device-recommerce flow.
Read: GET /tradeins, /diagnostics, /gradings, /photos, /wipes, /parts-declarations, /repair-quotes, /disputes (filter `imei`).
Write: PATCH /tradeins/{id}; POST /wipes (a data-wipe certificate; event `devicelab.wipe.created`).
Synthetic; the data is sim/seed/devices.py (seed 4242), shared with the registry and the market. Not a demo source:
registered in sim/core/registry.py EXTRA_SYSTEMS.
"""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed
from sim.seed.devices import world


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - the world does not depend on the demo's seed
    w = world()
    return {
        "tradeins": w.tradeins,
        "diagnostics": w.diagnostics,
        "gradings": w.gradings,
        "photos": w.photos,
        "wipes": w.wipes,
        "partsDeclarations": w.parts_declarations,
        "repairQuotes": w.repair_quotes,
        "disputes": w.disputes,
    }


SPEC = Spec(
    source_id="dvlab",
    title="Device Lab",
    schema="device_lab",
    base_path="/device-lab/v1",
    auth=Auth("oauth_cc"),
    paging=Paging("offset", items_key="items", next_key="next", total_key="total"),
    resources=(
        Resource(
            "tradeins",
            "/tradeins",
            "tradeInId",
            filters=("imei", "batchId", "partner"),
            update=True,
            id_format="TI-N{n:05d}",
            event="devicelab.tradein",
        ),
        Resource("diagnostics", "/diagnostics", "imei", filters=("imei",)),
        Resource("gradings", "/gradings", "imei", filters=("imei",)),
        Resource("photos", "/photos", "photoId", filters=("imei", "view")),
        Resource(
            "wipes",
            "/wipes",
            "certificateId",
            filters=("imei", "method", "verification"),
            create=True,
            id_format="WCX-{n:05d}",
            event="devicelab.wipe",
        ),
        Resource("partsDeclarations", "/parts-declarations", "imei", filters=("imei", "status")),
        Resource("repairQuotes", "/repair-quotes", "quoteId", filters=("imei",)),
        Resource("disputes", "/disputes", "disputeId", filters=("imei", "partner", "status")),
    ),
    seed=seed,
)
