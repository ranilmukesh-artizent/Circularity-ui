"""Workday HCM (catalogue): workers, supervisory organizations and cost centres, so owners and approvers resolve to real
teams. Synthetic; reads like Workday's REST API (camelCase, descriptor objects). Offset paging, total in `total`."""

from sim.generic.catalog import PEOPLE, TEAMS, ago, email, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    sites = [x.name for x in s.world.sites]
    orgs = [
        {"id": f"SUP-{i + 1:03d}", "descriptor": team, "code": cc, "manager": {"descriptor": pick(PEOPLE, team, "mgr")},
         "lastUpdated": iso(ago(s, "wd-org", team))}
        for i, (team, cc) in enumerate(TEAMS)
    ]  # fmt: skip
    centres = [
        {"id": cc, "descriptor": f"{cc} {team}", "costCenterCode": cc, "organization": {"id": f"SUP-{i + 1:03d}"},
         "active": True}
        for i, (team, cc) in enumerate(TEAMS)
    ]  # fmt: skip
    workers = []
    for i, name in enumerate(PEOPLE * 2):
        wid = f"W-{1001 + i}"
        team, cc = pick(TEAMS, wid)
        first = name if i < len(PEOPLE) else name.split()[0] + " " + chr(65 + i % 26) + ". " + name.split()[1]
        workers.append(
            {"id": wid, "descriptor": first, "primaryWorkEmail": email(first.replace(".", "")), "businessTitle": pick(
                ("Planner", "Approver", "Engineer", "Analyst", "Manager", "Coordinator"), wid),
             "supervisoryOrganization": next(o["id"] for o in orgs if o["descriptor"] == team), "costCenter": cc,
             "location": sites[h(wid) % len(sites)], "hireDate": ago(s, wid, days=3650).date().isoformat(),
             "workerType": "Employee" if h(wid, "t") % 5 else "Contingent Worker"}
        )  # fmt: skip
    return {"workers": workers, "supervisoryOrganizations": orgs, "costCenters": centres}


SPEC = Spec(
    source_id="workday",
    title="Workday HCM",
    schema="cat_workday",
    base_path="/workday/ccx/api/v1/northfield",
    auth=Auth("oauth_cc", token_path="/oauth2/token"),  # noqa: S106 - a URL path
    paging=Paging(
        "offset",
        limit_param="limit",
        offset_param="offset",
        items_key="data",
        next_key="nextOffset",
        total_key="total",
        max_size=100,
    ),
    resources=(
        Resource("workers", "/workers", "id", filters=("costCenter", "location", "supervisoryOrganization")),
        Resource("supervisoryOrganizations", "/supervisoryOrganizations", "id"),
        Resource("costCenters", "/costCenters", "id"),
    ),
    updated_since_param="updatedFrom",
    seed=seed,
)
