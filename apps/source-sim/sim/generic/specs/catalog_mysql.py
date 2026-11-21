"""MySQL (catalogue): legacy site databases read through a read-only HTTP gateway (one path per table). Synthetic.
API key in X-Api-Key; page paging (`page`, `per_page`, `next_page`, `total_rows`)."""

from sim.generic.catalog import ago, facts, h, iso
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    tags, readings = [], []
    for f in facts(s):
        tag = "TAG-" + f.asset_id.replace("-", "")
        tags.append({"asset_tag": tag, "site_code": f.location.split()[0].upper(), "equipment": f.product, "mfr": f.mfr})
        for k in range(1 + h(f.id, "mysql") % 3):
            readings.append(
                {"reading_id": f"{tag}-{k + 1}", "asset_tag": tag, "meter": ("run_hours", "starts", "kwh")[k],
                 "value": h(f.id, "m", k) % 50000, "read_at": iso(ago(s, f.id, "read", k, days=30))}
            )  # fmt: skip
    return {"site_assets": tags, "meter_readings": readings}


SPEC = Spec(
    source_id="mysql",
    title="MySQL",
    schema="cat_mysql",
    base_path="/mysql/api/v1",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging(
        "page",
        page_param="page",
        size_param="per_page",
        items_key="rows",
        next_key="next_page",
        total_key="total_rows",
        max_size=100,
    ),
    resources=(
        Resource("site_assets", "/site_assets", "asset_tag", filters=("site_code",)),
        Resource("meter_readings", "/meter_readings", "reading_id", filters=("asset_tag", "meter")),
    ),
    seed=seed,
)
