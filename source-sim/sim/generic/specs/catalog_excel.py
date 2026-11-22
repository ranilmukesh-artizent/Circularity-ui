"""Microsoft Excel and SharePoint (catalogue): spreadsheets kept in a SharePoint drive and their worksheet rows, for a
controlled import. Synthetic; reads like Microsoft Graph (`value`, `$top` / `$skiptoken`, driveItem fields). OAuth 2.0."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BOOKS = ("Partner rate card.xlsx", "Refurbishment costs.xlsx", "Site capacity plan.xlsx")


def seed(s: Seed) -> dict[str, list[dict]]:
    items = [
        {"id": f"01NFLD{h(b):08X}", "name": b, "file": {"mimeType": XLSX},
         "size": 30_000 + h(b) % 200_000, "lastModifiedDateTime": iso(ago(s, b, days=60)),
         "lastModifiedBy": {"user": {"displayName": pick(PEOPLE, b)}}}
        for b in BOOKS
    ]  # fmt: skip
    rows = []
    for n, f in enumerate(f for f in facts(s) if h(f.id, "xl") % 3 == 0):
        book = items[n % len(items)]
        rows.append(
            {"rowId": f"{book['id']}-{n + 2}", "workbookId": book["id"], "index": n + 2,
             "values": [[f.asset_id, f.product, f.location, round(f.age, 1), f.grade or ""]]}
        )  # fmt: skip
    return {"items": items, "worksheet_rows": rows}


SPEC = Spec(
    source_id="excel",
    title="Microsoft Excel and SharePoint",
    schema="cat_excel",
    base_path="/excel/v1.0/sites/northfield/drive",
    auth=Auth("oauth_cc", token_path="/oauth2/v2.0/token"),  # noqa: S106 - a URL path
    paging=Paging(
        "cursor",
        limit_param="$top",
        cursor_param="$skiptoken",
        items_key="value",
        next_key="skipToken",
        total_key=None,
        max_size=100,
    ),
    resources=(
        Resource("items", "/items", "id"),
        Resource("worksheet_rows", "/worksheet_rows", "rowId", filters=("workbookId",)),
    ),
    seed=seed,
)
