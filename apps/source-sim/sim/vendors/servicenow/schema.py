"""ServiceNow tables in Postgres schema `servicenow`, described once as dictionary entries (sys_dictionary).

Each field has a ServiceNow type that decides how it is stored, compared in encoded queries and returned:
  string, integer, decimal (stored typed, returned as strings), boolean ("true"/"false"),
  glide_date_time ("YYYY-MM-DD HH:MM:SS" UTC), glide_date ("YYYY-MM-DD"),
  glide_duration (stored in seconds, returned as "1970-01-01 HH:MM:SS", displayed "2 Hours 30 Minutes"),
  reference (a sys_id, returned as {"link", "value"}), choice (integer value with a label).
Every table carries sys_id, sys_created_on/by, sys_updated_on/by and sys_mod_count, as on an instance.
"""

from dataclasses import dataclass, field

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, Numeric, String, Table, Text

SCHEMA = "servicenow"
metadata = MetaData(schema=SCHEMA)


@dataclass(frozen=True)
class Field:
    name: str
    type: str = "string"
    ref: str | None = None  # referenced table
    choices: dict[int, str] | None = None
    length: int = 255


@dataclass(frozen=True)
class TableSpec:
    name: str
    label: str
    display: str  # the display field (what a reference shows)
    prefix: str | None  # number prefix, e.g. WO
    fields: list[Field]
    writable: bool = False
    by_name: dict[str, Field] = field(default_factory=dict, compare=False)

    def __post_init__(self):
        self.by_name.update({f.name: f for f in SYS_FIELDS + self.fields})


SYS_FIELDS = [
    Field("sys_id", length=32),
    Field("sys_created_on", "glide_date_time"),
    Field("sys_created_by", length=40),
    Field("sys_updated_on", "glide_date_time"),
    Field("sys_updated_by", length=40),
    Field("sys_mod_count", "integer"),
]

INSTALL_STATUS = {1: "In use", 2: "On order", 3: "In maintenance", 6: "In stock", 7: "Retired", 8: "Missing", 9: "In transit"}
ORDER_STATE = {
    1: "Draft",
    10: "Ready",
    16: "Scheduled",
    18: "Awaiting Dispatch",
    2: "Work In Progress",
    3: "Closed Complete",
    4: "Closed Incomplete",
    7: "Cancelled",
}
TASK_STATE = {
    1: "Draft",
    10: "Pending Dispatch",
    16: "Assigned",
    18: "Accepted",
    2: "Work In Progress",
    3: "Closed Complete",
    4: "Closed Incomplete",
    7: "Cancelled",
}
PRIORITY = {1: "1 - Critical", 2: "2 - High", 3: "3 - Moderate", 4: "4 - Low"}
CLOSED_STATES = (3, 4, 7)

SPECS: dict[str, TableSpec] = {
    s.name: s
    for s in [
        TableSpec(
            "core_company",
            "Company",
            "name",
            None,
            [
                Field("name"),
                Field("customer", "boolean"),
                Field("vendor", "boolean"),
                Field("manufacturer", "boolean"),
                Field("city"),
                Field("country"),
            ],
        ),
        TableSpec(
            "cmn_location",
            "Location",
            "name",
            None,
            [
                Field("name"),
                Field("full_name"),
                Field("street"),
                Field("city"),
                Field("state"),
                Field("country"),
                Field("company", "reference", "core_company"),
                Field("u_site_code", length=40),
            ],
        ),
        TableSpec(
            "sys_user",
            "User",
            "name",
            None,
            [
                Field("user_name", length=40),
                Field("name"),
                Field("first_name"),
                Field("last_name"),
                Field("email"),
                Field("title"),
                Field("location", "reference", "cmn_location"),
                Field("company", "reference", "core_company"),
                Field("active", "boolean"),
            ],
        ),
        TableSpec(
            "cmdb_model",
            "Product Model",
            "display_name",
            None,
            [
                Field("display_name"),
                Field("name"),
                Field("manufacturer", "reference", "core_company"),
                Field("model_number", length=80),
                Field("short_description"),
            ],
        ),
        TableSpec(
            "alm_asset",
            "Asset",
            "display_name",
            None,
            [
                Field("display_name"),
                Field("asset_tag", length=40),
                Field("serial_number", length=40),
                Field("model", "reference", "cmdb_model"),
                Field("model_category", length=80),
                Field("install_status", "choice", choices=INSTALL_STATUS),
                Field("substatus", length=40),
                Field("location", "reference", "cmn_location"),
                Field("company", "reference", "core_company"),
                Field("owned_by", "reference", "sys_user"),
                Field("install_date", "glide_date_time"),
                Field("warranty_expiration", "glide_date"),
                Field("quantity", "integer"),
                Field("comments", "string", length=4000),
            ],
        ),
        TableSpec(
            "wm_order",
            "Work Order",
            "number",
            "WO",
            [
                Field("number", length=40),
                Field("short_description"),
                Field("description", length=4000),
                Field("state", "choice", choices=ORDER_STATE),
                Field("priority", "choice", choices=PRIORITY),
                Field("company", "reference", "core_company"),
                Field("location", "reference", "cmn_location"),
                Field("asset", "reference", "alm_asset"),
                Field("caller", "reference", "sys_user"),
                Field("opened_at", "glide_date_time"),
                Field("expected_start", "glide_date_time"),
                Field("closed_at", "glide_date_time"),
                Field("close_notes", length=4000),
                Field("correlation_id", length=100),
                Field("u_work_type", length=40),
                Field("u_model_required", "reference", "cmdb_model"),
                Field("u_quantity", "integer"),
            ],
            writable=True,
        ),
        TableSpec(
            "wm_task",
            "Work Order Task",
            "number",
            "WOT",
            [
                Field("number", length=40),
                Field("parent", "reference", "wm_order"),
                Field("short_description"),
                Field("state", "choice", choices=TASK_STATE),
                Field("priority", "choice", choices=PRIORITY),
                Field("assigned_to", "reference", "sys_user"),
                Field("company", "reference", "core_company"),
                Field("location", "reference", "cmn_location"),
                Field("asset", "reference", "alm_asset"),
                Field("expected_start", "glide_date_time"),
                Field("actual_work_start", "glide_date_time"),
                Field("actual_work_end", "glide_date_time"),
                Field("work_duration", "glide_duration"),
                Field("closed_at", "glide_date_time"),
                Field("close_code", length=40),
                Field("close_notes", length=4000),
                Field("u_labour_rate", "decimal"),
            ],
            writable=True,
        ),
        TableSpec(
            "sm_part_requirement",
            "Part Requirement",
            "number",
            "PRQ",
            [
                Field("number", length=40),
                Field("task", "reference", "wm_task"),
                Field("part_number", length=80),
                Field("short_description"),
                Field("required_quantity", "integer"),
                Field("consumed_quantity", "integer"),
                Field("unit_cost", "decimal"),
                Field("state", length=40),
            ],
            writable=True,
        ),
    ]
}


def _column(f: Field) -> Column:
    if f.name == "sys_id":
        return Column("sys_id", String(32), primary_key=True)
    kind = {
        "integer": Integer,
        "choice": Integer,
        "glide_duration": Integer,
        "decimal": Numeric(15, 2),
        "boolean": Boolean,
        "glide_date_time": DateTime(timezone=True),
        "glide_date": DateTime(timezone=True),
        "reference": String(32),
    }.get(f.type)
    if kind is None:
        kind = Text if f.length > 255 else String(f.length)
    return Column(f.name, kind, index=f.type == "reference" or f.name in ("number", "sys_updated_on", "asset_tag"))


TABLES: dict[str, Table] = {
    name: Table(name, metadata, *[_column(f) for f in SYS_FIELDS + s.fields]) for name, s in SPECS.items()
}
