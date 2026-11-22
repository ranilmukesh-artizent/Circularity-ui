"""Oracle NetSuite (catalogue): vendor bills and subsidiaries for the subsidiary that runs on NetSuite. Synthetic;
reads like SuiteTalk REST record services (camelCase records, `items`, limit / offset, `totalResults`). OAuth 2.0."""

from sim.generic.catalog import ago, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

SUBS = (("3", "Northfield Equipment Pte Ltd", "SGD"), ("4", "Northfield Recovery GmbH", "EUR"))


def seed(s: Seed) -> dict[str, list[dict]]:
    subs = [{"id": sid, "name": name, "currency": {"refName": cur}, "isInactive": False} for sid, name, cur in SUBS]
    bills = []
    for n in range(40):
        sid, _, cur = SUBS[n % 2]
        key = f"bill-{n}"
        bills.append(
            {"id": str(51000 + n), "tranId": f"VB{20260 + n}", "subsidiary": sid, "currency": cur,
             "status": pick(("Open", "Paid In Full", "Pending Approval"), key), "total": float(200 + h(key) % 15000),
             "entity": {"refName": pick(("EcoParts Recovery", "MetalCycle Ltd", "Reman Co"), key, "e")},
             "tranDate": ago(s, key, days=120).date().isoformat(), "lastModifiedDate": iso(ago(s, key, "m", days=30))}
        )  # fmt: skip
    return {"vendorBill": bills, "subsidiary": subs}


SPEC = Spec(
    source_id="netsuite",
    title="Oracle NetSuite",
    schema="cat_netsuite",
    base_path="/netsuite/services/rest/record/v1",
    auth=Auth("oauth_cc", token_path="/oauth2/token"),  # noqa: S106 - a URL path
    paging=Paging("offset", items_key="items", next_key="nextOffset", total_key="totalResults", max_size=100),
    resources=(
        Resource("vendorBill", "/vendorBill", "id", filters=("subsidiary", "status")),
        Resource("subsidiary", "/subsidiary", "id"),
    ),
    seed=seed,
)
