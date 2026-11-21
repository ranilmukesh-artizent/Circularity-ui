"""Connection templates for the Connection Fabric's catalogue (plan 6, task A3).

    template("workday")   → {"base_path", "auth_kind", "auth_params", "paging", "resources", "demo_secret"}

Connecting a catalogue system (source.update, mode "catalog") writes a `source_connection` row from its template: the
URL (settings.source_sim_url + base_path in dev, where source-sim mocks the system), how to sign in, how lists are paged
and which resources to read. The configured adapter (di.connectors.configured) then reads it like any spec-shaped API.

Every system here is synthetic: source-sim's generic mock (apps/source-sim/sim/generic/specs/catalog_<id>.py) is the
only thing behind it, never the vendor. The shapes below must match those specs (tests/test_configured_adapter.py
syncs every one). `demo_secret` is the synthetic credential that mock accepts (sim.generic.spec.credentials): what is
stored when the person connecting enters none.
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
    },
    "mysql": {
        "base_path": "/mysql/api/v1", "auth_kind": "api_key", "auth_params": {"header": "X-Api-Key"},
        "paging": _page("rows", "next_page", "page", "per_page", "total_rows"),
        "resources": _res("updated_since", ("site_assets", "/site_assets", "asset_tag"),
                          ("meter_readings", "/meter_readings", "reading_id")),
    },
    "sqlserver": {
        "base_path": "/sqlserver/api/v1", "auth_kind": "basic", "auth_params": {},
        "paging": _offset("value", "nextSkip", "top", "skip", "count"),
        "resources": _res("updated_since", ("historian_tags", "/historian_tags", "TagName"),
                          ("maintenance_log", "/maintenance_log", "LogID")),
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
    },
    "dynamics": {
        "base_path": "/dynamics/api/data/v9.2", "auth_kind": OAUTH, "auth_params": {"token_path": "/oauth2/token"},
        "paging": _offset("value", "nextSkip", "$top", "$skip", "@odata.count"),
        "resources": _res("updated_since", ("opportunities", "/opportunities", "opportunityid"),
                          ("accounts", "/accounts", "accountid")),
    },
    "ebs": {
        "base_path": "/ebs/webservices/rest/ap", "auth_kind": "basic", "auth_params": {},
        "paging": _offset("items", "next_offset", total="totalResults"),
        "resources": _res("updated_since", ("invoices", "/invoices", "invoice_id"), ("suppliers", "/suppliers", "vendor_id")),
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
    return {**t, "auth_params": params, "demo_secret": _demo_secret(sid, t["auth_kind"])}


IDS = tuple(_T)
