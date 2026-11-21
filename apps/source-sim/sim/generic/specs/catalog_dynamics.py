"""Microsoft Dynamics 365 (catalogue): opportunities and accounts from a second CRM used by one region. Synthetic;
reads like the Dataverse Web API (lower-case logical names, `value`, `$top` / `$skip`, `@odata.count`). OAuth 2.0."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    accounts = [
        {"accountid": f"a{h(t):07x}-0000-4000-8000-{h(t, 'id'):012x}", "name": t, "accountnumber": f"ACC-{i + 1:04d}",
         "address1_city": pick(("Pune", "Chennai", "Rotterdam", "Houston"), t), "statecode": 0}
        for i, t in enumerate(s.world.tenants)
    ]  # fmt: skip
    by_name = {a["name"]: a["accountid"] for a in accounts}
    opps = []
    for f in facts(s):
        if h(f.id, "dyn") % 3:
            continue
        opps.append(
            {"opportunityid": f"o{h(f.id):07x}-0000-4000-8000-{h(f.id, 'id'):012x}", "name": f"{f.product} · {f.asset_id}",
             "_parentaccountid_value": by_name.get(f.owner), "estimatedvalue": float(500 + h(f.id, "v") % 20000),
             "transactioncurrencyid": pick(("EUR", "USD"), f.id), "statecode": pick((0, 0, 1, 2), f.id),
             "ownerid": pick(PEOPLE, f.id, "own"), "modifiedon": iso(ago(s, f.id, "dyn"))}
        )  # fmt: skip
    return {"opportunities": opps, "accounts": accounts}


SPEC = Spec(
    source_id="dynamics",
    title="Microsoft Dynamics 365",
    schema="cat_dynamics",
    base_path="/dynamics/api/data/v9.2",
    auth=Auth("oauth_cc", token_path="/oauth2/token"),  # noqa: S106 - a URL path
    paging=Paging(
        "offset",
        limit_param="$top",
        offset_param="$skip",
        items_key="value",
        next_key="nextSkip",
        total_key="@odata.count",
        max_size=100,
    ),
    resources=(
        Resource("opportunities", "/opportunities", "opportunityid", filters=("transactioncurrencyid",)),
        Resource("accounts", "/accounts", "accountid", filters=("name",)),
    ),
    seed=seed,
)
