"""Atlassian Confluence (catalogue): spaces and the pages that hold workflow documentation and evidence summaries.
Synthetic; reads like Confluence's REST API v2 (`results`, opaque `cursor` paging). Basic auth (API token)."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

SPACES = (("65537", "CIRC", "Circularity operations"), ("65538", "WFDOC", "Workflow documentation"))


def seed(s: Seed) -> dict[str, list[dict]]:
    spaces = [{"id": sid, "key": key, "name": name, "type": "global", "status": "current"} for sid, key, name in SPACES]
    pages = []
    for n, f in enumerate(f for f in facts(s) if h(f.id, "conf") % 3 == 0):
        sid, key, _ = SPACES[n % 2]
        pages.append(
            {"id": str(300000 + n), "spaceId": sid, "status": "current", "title": f"Evidence summary {f.id} ({f.asset_id})",
             "authorId": pick(PEOPLE, f.id, "author"), "createdAt": iso(ago(s, f.id, "conf", days=45)),
             "version": {"number": 1 + h(f.id, "v") % 4}, "body": {"representation": "storage",
             "value": f"<p>{f.product}: {f.assessment}</p>"}}
        )  # fmt: skip
    for i, title in enumerate(("Ingest workflow runbook", "Mapping conventions", "Escalation matrix")):
        pages.append(
            {"id": str(310000 + i), "spaceId": SPACES[1][0], "status": "current", "title": title,
             "authorId": pick(PEOPLE, title), "createdAt": iso(ago(s, title, days=120)), "version": {"number": 3},
             "body": {"representation": "storage", "value": f"<p>{title}</p>"}}
        )  # fmt: skip
    return {"spaces": spaces, "pages": pages}


SPEC = Spec(
    source_id="confluence",
    title="Atlassian Confluence",
    schema="cat_confluence",
    base_path="/confluence/wiki/api/v2",
    auth=Auth("basic"),
    paging=Paging(
        "cursor",
        limit_param="limit",
        cursor_param="cursor",
        items_key="results",
        next_key="nextCursor",
        total_key=None,
        max_size=100,
    ),
    resources=(
        Resource("spaces", "/spaces", "id", filters=("key", "type")),
        Resource("pages", "/pages", "id", filters=("spaceId", "status")),
    ),
    seed=seed,
)
