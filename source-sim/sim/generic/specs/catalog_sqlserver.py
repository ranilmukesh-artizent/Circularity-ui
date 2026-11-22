"""Microsoft SQL Server (catalogue): plant historian and maintenance tables through a read-only HTTP gateway
(PascalCase columns, `value`, `$top`-style top / skip paging with `count`). Synthetic. Basic auth."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed


def seed(s: Seed) -> dict[str, list[dict]]:
    tags, logs = [], []
    for n, f in enumerate(f for f in facts(s) if f.cls in ("motor", "pump", "control")):
        eq = f.asset_id
        for unit in ("degC", "mm/s"):
            tags.append(
                {"TagName": f"{eq}.{'TEMP' if unit == 'degC' else 'VIB'}", "EquipmentID": eq, "EngUnit": unit,
                 "LastValue": round((h(eq, unit) % 900) / 10, 1), "LastTimestamp": iso(ago(s, eq, unit, days=2))}
            )  # fmt: skip
        logs.append(
            {"LogID": 70001 + n, "EquipmentID": eq, "Technician": pick(PEOPLE, f.id, "tech"),
             "WorkType": pick(("PM", "CM", "Inspection"), f.id), "LoggedAt": iso(ago(s, f.id, "log", days=180)),
             "Notes": f.condition}
        )  # fmt: skip
    return {"historian_tags": tags, "maintenance_log": logs}


SPEC = Spec(
    source_id="sqlserver",
    title="Microsoft SQL Server",
    schema="cat_sqlserver",
    base_path="/sqlserver/api/v1",
    auth=Auth("basic"),
    paging=Paging(
        "offset", limit_param="top", offset_param="skip", items_key="value", next_key="nextSkip", total_key="count", max_size=100
    ),
    resources=(
        Resource("historian_tags", "/historian_tags", "TagName", filters=("EquipmentID", "EngUnit")),
        Resource("maintenance_log", "/maintenance_log", "LogID", filters=("EquipmentID", "WorkType")),
    ),
    seed=seed,
)
