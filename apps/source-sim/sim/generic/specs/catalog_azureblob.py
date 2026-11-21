"""Azure Blob Storage (catalogue): partner files in a container, with a signed manifest. Synthetic; reads like a List
Blobs answer (`Blobs`, `Name`, `Properties`, `marker` / `NextMarker` paging), served as JSON. Access key header."""

from sim.generic.catalog import ago, h, iso
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

PARTNERS = ("sims", "ecoparts", "metalcycle", "reman-co")


def seed(s: Seed) -> dict[str, list[dict]]:
    blobs = []
    for p in PARTNERS:
        for m in range(5, 11):
            for kind, ctype in (("rates", "text/csv"), ("manifest", "application/json")):
                name = f"{p}_{kind}_2026-{m:02d}.{'csv' if kind == 'rates' else 'json'}"
                blobs.append(
                    {"Name": name, "ContentType": ctype, "Partner": p,
                     "Properties": {"Content-Length": 2_000 + h(name) % 90_000, "Last-Modified": iso(ago(s, name, days=200)),
                                    "BlobType": "BlockBlob", "AccessTier": "Hot"}}
                )  # fmt: skip
    return {"blobs": blobs}


SPEC = Spec(
    source_id="azureblob",
    title="Azure Blob Storage",
    schema="cat_azureblob",
    base_path="/azureblob/partner-files",
    auth=Auth("api_key", header="x-ms-access-key"),
    paging=Paging(
        "cursor",
        limit_param="maxresults",
        cursor_param="marker",
        items_key="Blobs",
        next_key="NextMarker",
        total_key=None,
        max_size=100,
    ),
    resources=(Resource("blobs", "/blobs", "Name", filters=("ContentType", "Partner")),),
    seed=seed,
)
