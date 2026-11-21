"""PostgreSQL (catalogue): operational tables read through a read-only HTTP SQL gateway (PostgREST style: one path per
table, snake_case columns). Synthetic. Bearer token; offset paging with `next_offset` and `count`."""

from sim.generic.catalog import ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    assets, orders = [], []
    for f in facts(s):
        assets.append(
            {"asset_id": f.asset_id, "asset_class": f.cls, "description": f.product, "manufacturer": f.mfr,
             "site": f.location, "owner_tenant": f.owner, "age_years": round(f.age, 1), "quantity": f.qty,
             "updated_at": iso(ago(s, f.asset_id, "pg"))}
        )  # fmt: skip
        if h(f.id, "wo") % 2 == 0:
            orders.append(
                {"wo_id": f"WO-{10001 + len(orders)}", "asset_id": f.asset_id,
                 "state": pick(("open", "in_progress", "closed"), f.id), "opened_at": iso(ago(s, f.id, "wo-open")),
                 "summary": f"Inspect {f.product.lower()}"}
            )  # fmt: skip
    return {"asset_register": assets, "work_orders": orders}


SPEC = Spec(
    source_id="postgres",
    title="PostgreSQL",
    schema="cat_postgres",
    base_path="/postgres/rest/v1",
    auth=Auth("bearer"),
    paging=Paging("offset", items_key="rows", next_key="next_offset", total_key="count", max_size=200),
    resources=(
        Resource("asset_register", "/asset_register", "asset_id", filters=("site", "asset_class", "owner_tenant")),
        Resource("work_orders", "/work_orders", "wo_id", filters=("asset_id", "state")),
    ),
    seed=seed,
)
