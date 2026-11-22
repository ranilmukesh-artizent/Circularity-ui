"""Amazon S3 (catalogue): partner files and photos in a bucket, with signed manifests. Synthetic; reads like a
ListObjectsV2 answer (`Contents`, `Key`, `ETag`, `continuation-token` paging), served as JSON. Bearer token."""

from sim.generic.catalog import ago, facts, h, iso
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    objects, manifests = [], []
    for f in facts(s):
        if h(f.id, "s3") % 2:
            continue
        for k in range(1 + h(f.id, "n") % 3):
            key = f"photos_{f.asset_id}_{k + 1:02d}.jpg"
            objects.append(
                {"Key": key, "Size": 400_000 + h(key) % 3_000_000, "ETag": f'"{h(key, "e"):08x}"',
                 "StorageClass": "STANDARD", "LastModified": iso(ago(s, key, days=30)), "ContentType": "image/jpeg",
                 "Metadata": {"asset-id": f.asset_id, "return-ref": f.id}}
            )  # fmt: skip
    for m in range(6):
        mid = f"manifest-2026-{m + 5:02d}"
        manifests.append(
            {"ManifestId": mid, "Key": f"{mid}.json", "Signed": True, "Algorithm": "Ed25519",
             "Files": 10 + h(mid) % 30, "LastModified": iso(ago(s, mid, days=200))}
        )  # fmt: skip
    return {"objects": objects, "manifests": manifests}


SPEC = Spec(
    source_id="s3",
    title="Amazon S3",
    schema="cat_s3",
    base_path="/s3/northfield-partner-drop",
    auth=Auth("bearer"),
    paging=Paging(
        "cursor",
        limit_param="max-keys",
        cursor_param="continuation-token",
        items_key="Contents",
        next_key="NextContinuationToken",
        total_key=None,
        max_size=200,
    ),
    resources=(
        Resource("objects", "/objects", "Key", filters=("StorageClass", "ContentType")),
        Resource("manifests", "/manifests", "ManifestId"),
    ),
    seed=seed,
)
