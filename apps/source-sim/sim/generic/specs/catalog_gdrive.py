"""Google Drive (catalogue): shared inspection folders and photos. Synthetic; reads like the Drive API v3 files list
(`files`, `pageSize` / `pageToken` / `nextPageToken`, camelCase file fields). Bearer token."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    files = []
    sites = sorted({f.location for f in facts(s)})
    folders = {site: f"1F{h(site):010x}" for site in sites}
    for site, fid in folders.items():
        files.append(
            {"id": fid, "name": f"Inspections · {site}", "mimeType": "application/vnd.google-apps.folder", "parents": [],
             "modifiedTime": iso(ago(s, site, days=90)), "owners": [{"displayName": pick(PEOPLE, site)}]}
        )  # fmt: skip
    for f in facts(s):
        if h(f.id, "gd") % 3:
            continue
        files.append(
            {"id": f"1P{h(f.id, 'file'):010x}", "name": f"{f.asset_id}_overview.jpg", "mimeType": "image/jpeg",
             "parents": [folders[f.location]], "size": str(500_000 + h(f.id, "sz") % 2_000_000),
             "modifiedTime": iso(ago(s, f.id, "gd", days=30)), "owners": [{"displayName": pick(PEOPLE, f.id)}],
             "appProperties": {"assetId": f.asset_id, "returnRef": f.id}}
        )  # fmt: skip
    return {"files": files}


SPEC = Spec(
    source_id="gdrive",
    title="Google Drive",
    schema="cat_gdrive",
    base_path="/gdrive/drive/v3",
    auth=Auth("bearer"),
    paging=Paging(
        "cursor",
        limit_param="pageSize",
        cursor_param="pageToken",
        items_key="files",
        next_key="nextPageToken",
        total_key=None,
        max_size=100,
    ),
    resources=(Resource("files", "/files", "id", filters=("mimeType",)),),
    seed=seed,
)
