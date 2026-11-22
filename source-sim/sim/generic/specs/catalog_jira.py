"""Atlassian Jira (catalogue): projects and the engineering issues raised from failed inspections or workflow errors.
Synthetic; reads like Jira's REST API v3 (startAt / maxResults paging, `values`, `fields`). Basic auth (API token)."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

PROJECTS = (("10001", "RET", "Returns engineering"), ("10002", "INT", "Integration"), ("10003", "QA", "Quality"))


def seed(s: Seed) -> dict[str, list[dict]]:
    projects = [
        {"id": pid, "key": key, "name": name, "projectTypeKey": "software", "lead": {"displayName": pick(PEOPLE, key)}}
        for pid, key, name in PROJECTS
    ]
    issues = []
    for n, f in enumerate(f for f in facts(s) if f.grade in ("C", "D") or h(f.id, "jira") % 4 == 0):
        _, key, _ = PROJECTS[h(f.id, "proj") % len(PROJECTS)]
        created = ago(s, f.id, "jira", days=60)
        issues.append(
            {"id": str(20000 + n), "key": f"{key}-{100 + n}", "projectKey": key,
             "status": pick(("To Do", "In Progress", "Done"), f.id, "st"),
             "priority": "High" if f.grade == "D" else pick(("Medium", "Low"), f.id),
             "fields": {"summary": f"{f.asset_id}: {f.condition}", "issuetype": {"name": pick(("Bug", "Task"), f.id)},
                        "assignee": {"displayName": pick(PEOPLE, f.id, "a")}, "labels": [f.cls, f.location.split()[0]],
                        "customfield_asset": f.asset_id, "customfield_return": f.id},
             "created": iso(created), "updated": iso(min(created.replace(microsecond=0), s.world.as_of))}
        )  # fmt: skip
    return {"projects": projects, "issues": issues}


SPEC = Spec(
    source_id="jira",
    title="Atlassian Jira",
    schema="cat_jira",
    base_path="/jira/rest/api/3",
    auth=Auth("basic"),
    paging=Paging(
        "offset",
        limit_param="maxResults",
        offset_param="startAt",
        items_key="values",
        next_key="nextStartAt",
        total_key="total",
        max_size=100,
    ),
    resources=(
        Resource("projects", "/project", "id", filters=("key",)),
        Resource("issues", "/issue", "id", filters=("projectKey", "status", "priority")),
    ),
    updated_since_param="updatedSince",
    seed=seed,
)
