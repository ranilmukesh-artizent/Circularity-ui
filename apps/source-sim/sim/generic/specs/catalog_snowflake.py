"""Snowflake (catalogue): governed warehouse history for analytics and model training. Synthetic; reads like rows from
the SQL API (upper-case column names, `data`, page / pageSize paging with `nextPage` and `total`). OAuth 2.0."""

from sim.generic.catalog import ago, facts, h, iso
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    history, prices = [], []
    for n, f in enumerate(facts(s)):
        history.append(
            {"ROW_ID": f"AH-{n + 1:05d}", "ASSET_ID": f.asset_id, "ASSET_CLASS": f.cls.upper(), "SITE": f.location,
             "GRADE": f.grade, "AGE_YEARS": round(f.age, 2), "RECEIVED_AT": iso(f.received),
             "LOADED_AT": iso(ago(s, f.id, "sf", days=7))}
        )  # fmt: skip
    classes = sorted(s.world.classes)
    for m, month in enumerate(s.world.months):
        for c in classes:
            key = f"{c}|{month}"
            prices.append(
                {"ROW_ID": f"PH-{m + 1:02d}-{c.upper()}", "ASSET_CLASS": c.upper(), "MONTH": month,
                 "INDEX_VALUE": round(80 + (h(key) % 400) / 10, 1), "CURRENCY": "USD"}
            )  # fmt: skip
    return {"asset_history": history, "price_history": prices}


SPEC = Spec(
    source_id="snowflake",
    title="Snowflake",
    schema="cat_snowflake",
    base_path="/snowflake/api/v2/databases/CIRCULARITY/schemas/HISTORY",
    auth=Auth("oauth_cc", token_path="/oauth/token"),  # noqa: S106 - a URL path
    paging=Paging(
        "page", page_param="page", size_param="pageSize", items_key="data", next_key="nextPage", total_key="total", max_size=100
    ),
    resources=(
        Resource("asset_history", "/asset_history", "ROW_ID", filters=("ASSET_CLASS", "SITE")),
        Resource("price_history", "/price_history", "ROW_ID", filters=("ASSET_CLASS", "MONTH")),
    ),
    seed=seed,
)
