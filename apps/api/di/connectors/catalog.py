"""Connection templates for the Connection Fabric's catalogue (plan 6, task A3).

    template("workday")   → {"base_path", "auth_kind", "auth_params", "paging", "resources", "demo_secret"}

Connecting a catalogue system (source.update, mode "catalog") writes a `source_connection` row from its template: the
URL (settings.source_sim_url + base_path in dev, where source-sim mocks the system), how to sign in, how lists are paged
and which resources to read. The configured adapter (di.connectors.configured) then reads it like any spec-shaped API.

Every system here is synthetic: source-sim's generic mock (apps/source-sim/sim/generic/specs/catalog_<id>.py) is the
only thing behind it, never the vendor. The shapes below must match those specs (tests/test_configured_adapter.py
syncs every one). `demo_secret` is the synthetic credential that mock accepts (sim.generic.spec.credentials): what is
stored when the person connecting enters none.

**Default mappings** (`maps`, the rows Suggest mappings offers and connecting saves as the first mapping version):
only systems whose mock holds asset, condition, demand, market or vendor data have rows, naming the mock's real field
names and only canonical fields of MODEL_FIELDS whose type fits (di/canonical/schema.py). Workday, Jira, Confluence,
Teams, Google Drive, S3, Azure Blob and NetSuite have none: their records are kept in raw_record (Sync & History,
Source Tables) and feed no fact. Every catalogue fact lands on a key of its own, `<system>:<record key>` (rule
prefix:<system> on the model's key row): the mocks are seeded from the demo's assets, and a fact on a demo key would
change a demo asset's canonical value or open a conflict with the source that has authority over it.
"""

from typing import Any


def _offset(items: str, nxt: str, limit: str = "limit", offset: str = "offset", total: str | None = None, size: int = 100):
    return {"style": "offset", "limit_param": limit, "offset_param": offset, "items_key": items, "next_key": nxt,
            "total_key": total, "max_size": size}  # fmt: skip


def _page(items: str, nxt: str, page: str, size_param: str, total: str | None = None, size: int = 100):
    return {"style": "page", "page_param": page, "size_param": size_param, "items_key": items, "next_key": nxt,
            "total_key": total, "max_size": size}  # fmt: skip


def _cursor(items: str, nxt: str, limit: str, cursor: str, size: int = 100):
    return {"style": "cursor", "limit_param": limit, "cursor_param": cursor, "items_key": items, "next_key": nxt,
            "max_size": size}  # fmt: skip


def _res(delta: str | None, *rs: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [{"name": n, "path": p, "id_field": i, **({"delta_param": delta} if delta else {})} for n, p, i in rs]


def _maps(resource: str, key: str, *rows: tuple[str, str, str]) -> list[dict[str, Any]]:
    """One resource's rows: (source field, canonical model.field, rule). The key rows (the record's `key` source field
    → model.key, rule prefix:<system>) are added by template(), one per model the rows feed."""
    out = []
    for src, target, rule in rows:
        model, _, field = target.partition(".")
        out.append({"src": src, "model": model, "field": field, "rule": rule, "resource": resource, "key_src": key})
    return out


OAUTH = "oauth_cc"
_T: dict[str, dict[str, Any]] = {
    "workday": {
        "base_path": "/workday/ccx/api/v1/northfield", "auth_kind": OAUTH, "auth_params": {"token_path": "/oauth2/token"},
        "paging": _offset("data", "nextOffset", total="total"),
        "resources": _res("updatedFrom", ("workers", "/workers", "id"),
                          ("supervisoryOrganizations", "/supervisoryOrganizations", "id"), ("costCenters", "/costCenters", "id")),
    },
    "jira": {
        "base_path": "/jira/rest/api/3", "auth_kind": "basic", "auth_params": {},
        "paging": _offset("values", "nextStartAt", "maxResults", "startAt", "total"),
        "resources": _res("updatedSince", ("projects", "/project", "id"), ("issues", "/issue", "id")),
    },
    "confluence": {
        "base_path": "/confluence/wiki/api/v2", "auth_kind": "basic", "auth_params": {},
        "paging": _cursor("results", "nextCursor", "limit", "cursor"),
        "resources": _res("updated_since", ("spaces", "/spaces", "id"), ("pages", "/pages", "id")),
    },
    "postgres": {
        "base_path": "/postgres/rest/v1", "auth_kind": "bearer", "auth_params": {},
        "paging": _offset("rows", "next_offset", total="count", size=200),
        "resources": _res("updated_since", ("asset_register", "/asset_register", "asset_id"),
                          ("work_orders", "/work_orders", "wo_id")),
        "maps": _maps("asset_register", "asset_id", ("asset_id", "asset.asset_id", "copy"),
                      ("asset_class", "asset.asset_type", "copy"), ("description", "asset.description", "copy"),
                      ("manufacturer", "asset.manufacturer", "copy"), ("site", "asset.site", "copy"),
                      ("owner_tenant", "asset.owner_tenant", "copy"), ("quantity", "asset.qty", "number"))
        + _maps("work_orders", "asset_id", ("wo_id", "asset.work_order_ref", "copy"),
                ("state", "asset.work_order_state", "copy")),
    },
    "mysql": {
        "base_path": "/mysql/api/v1", "auth_kind": "api_key", "auth_params": {"header": "X-Api-Key"},
        "paging": _page("rows", "next_page", "page", "per_page", "total_rows"),
        "resources": _res("updated_since", ("site_assets", "/site_assets", "asset_tag"),
                          ("meter_readings", "/meter_readings", "reading_id")),
        # meter_readings mixes run hours, starts and kWh in one `value` column: no canonical field fits every row
        "maps": _maps("site_assets", "asset_tag", ("equipment", "asset.description", "copy"),
                      ("mfr", "asset.manufacturer", "copy"), ("site_code", "asset.site", "copy")),
    },
    "sqlserver": {
        "base_path": "/sqlserver/api/v1", "auth_kind": "basic", "auth_params": {},
        "paging": _offset("value", "nextSkip", "top", "skip", "count"),
        "resources": _res("updated_since", ("historian_tags", "/historian_tags", "TagName"),
                          ("maintenance_log", "/maintenance_log", "LogID")),
        # historian_tags mixes temperature and vibration tags in one `LastValue` column: not mapped
        "maps": _maps("maintenance_log", "EquipmentID", ("Technician", "condition.inspector", "copy"),
                      ("LoggedAt", "condition.service_date", "date"), ("Notes", "condition.inspection_result", "copy")),
    },
    "s3": {
        "base_path": "/s3/northfield-partner-drop", "auth_kind": "bearer", "auth_params": {},
        "paging": _cursor("Contents", "NextContinuationToken", "max-keys", "continuation-token", 200),
        "resources": _res("updated_since", ("objects", "/objects", "Key"), ("manifests", "/manifests", "ManifestId")),
    },
    "azureblob": {
        "base_path": "/azureblob/partner-files", "auth_kind": "api_key", "auth_params": {"header": "x-ms-access-key"},
        "paging": _cursor("Blobs", "NextMarker", "maxresults", "marker"),
        "resources": _res("updated_since", ("blobs", "/blobs", "Name")),
    },
    "excel": {
        "base_path": "/excel/v1.0/sites/northfield/drive", "auth_kind": OAUTH,
        "auth_params": {"token_path": "/oauth2/v2.0/token"},
        "paging": _cursor("value", "skipToken", "$top", "$skiptoken"),
        "resources": _res("updated_since", ("items", "/items", "id"), ("worksheet_rows", "/worksheet_rows", "rowId")),
        # a worksheet row's cells: asset id, product, site, age (no canonical field), grade
        "maps": _maps("worksheet_rows", "values.0.0", ("values.0.0", "asset.asset_id", "copy"),
                      ("values.0.1", "asset.description", "copy"), ("values.0.2", "asset.site", "copy"),
                      ("values.0.4", "condition.grade", "code:grade")),
    },
    "dynamics": {
        "base_path": "/dynamics/api/data/v9.2", "auth_kind": OAUTH, "auth_params": {"token_path": "/oauth2/token"},
        "paging": _offset("value", "nextSkip", "$top", "$skip", "@odata.count"),
        "resources": _res("updated_since", ("opportunities", "/opportunities", "opportunityid"),
                          ("accounts", "/accounts", "accountid")),
        # estimatedvalue is in each opportunity's own currency (EUR or USD) and statecode is a number: not mapped
        "maps": _maps("opportunities", "opportunityid", ("opportunityid", "demand.demand_id", "copy"),
                      ("name", "demand.item_desc", "copy")),
    },
    "ebs": {
        "base_path": "/ebs/webservices/rest/ap", "auth_kind": "basic", "auth_params": {},
        "paging": _offset("items", "next_offset", total="totalResults"),
        "resources": _res("updated_since", ("invoices", "/invoices", "invoice_id"), ("suppliers", "/suppliers", "vendor_id")),
        # invoices are payables, not the S/4HANA actual-cost lines of the outcome model: not mapped
        "maps": _maps("suppliers", "vendor_id", ("vendor_name", "vendor.name", "copy")),
    },
    "netsuite": {
        "base_path": "/netsuite/services/rest/record/v1", "auth_kind": OAUTH, "auth_params": {"token_path": "/oauth2/token"},
        "paging": _offset("items", "nextOffset", total="totalResults"),
        "resources": _res("updated_since", ("vendorBill", "/vendorBill", "id"), ("subsidiary", "/subsidiary", "id")),
    },
    "teams": {
        "base_path": "/teams/v1.0", "auth_kind": OAUTH, "auth_params": {"token_path": "/oauth2/v2.0/token"},
        "paging": _cursor("value", "nextSkipToken", "$top", "$skiptoken", 50),
        "resources": _res("updated_since", ("channels", "/channels", "id"), ("messages", "/messages", "id")),
    },
    "gdrive": {
        "base_path": "/gdrive/drive/v3", "auth_kind": "bearer", "auth_params": {},
        "paging": _cursor("files", "nextPageToken", "pageSize", "pageToken"),
        "resources": _res("updated_since", ("files", "/files", "id")),
    },
    "snowflake": {
        "base_path": "/snowflake/api/v2/databases/CIRCULARITY/schemas/HISTORY", "auth_kind": OAUTH,
        "auth_params": {"token_path": "/oauth/token"}, "paging": _page("data", "nextPage", "page", "pageSize", "total"),
        "resources": _res("updated_since", ("asset_history", "/asset_history", "ROW_ID"),
                          ("price_history", "/price_history", "ROW_ID")),
        "maps": _maps("asset_history", "ASSET_ID", ("ASSET_ID", "asset.asset_id", "copy"),
                      ("ASSET_CLASS", "asset.asset_type", "lower"), ("SITE", "asset.site", "copy"),
                      ("RECEIVED_AT", "asset.received_at", "date"), ("GRADE", "condition.grade", "code:grade"))
        + _maps("price_history", "ROW_ID", ("INDEX_VALUE", "market.price_index", "number"),
                ("MONTH", "market.price_index_period", "copy")),
    },
}  # fmt: skip


def _demo_secret(sid: str, kind: str) -> str:
    """sim.generic.spec.credentials: the synthetic credential source-sim's mock of `sid` accepts."""
    return {"api_key": f"{sid}-demo-key", "bearer": f"{sid}-demo-key", "basic": f"{sid}-demo"}.get(kind, f"{sid}-demo-secret")


def template(sid: str) -> dict[str, Any] | None:
    t = _T.get(sid)
    if t is None:
        return None
    params = dict(t["auth_params"])
    if t["auth_kind"] == "basic":
        params.setdefault("user", "di-connector")
    if t["auth_kind"] == OAUTH:
        params.setdefault("client_id", "di-connector")
    return {**t, "auth_params": params, "demo_secret": _demo_secret(sid, t["auth_kind"]), "maps": maps(sid)}


def maps(sid: str) -> list[dict[str, Any]]:
    """The rows a person is offered when connecting `sid` ({src, model, field, rule, resource}), [] for a system whose
    records feed no canonical model."""
    return [{k: v for k, v in r.items() if k != "key_src"} for r in _T.get(sid, {}).get("maps", [])]


def key_rows(sid: str, chosen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The key rows the chosen rows need: per (resource, model) the record's key field → model.key with rule
    prefix:<sid>, so the facts land on keys of their own ("postgres:MTR-2041") and never on a demo source's."""
    need = {(r["resource"], r["model"]) for r in chosen}
    out, seen = [], set()
    for r in _T.get(sid, {}).get("maps", []):
        k = (r["resource"], r["model"])
        if k in need and k not in seen:
            seen.add(k)
            out.append({"src": r["key_src"], "model": r["model"], "field": "key", "rule": f"prefix:{sid}",
                        "resource": r["resource"]})  # fmt: skip
    return out


IDS = tuple(_T)
