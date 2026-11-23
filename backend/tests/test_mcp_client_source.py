"""Plan 8 MVP-11.7: a source read through an MCP server (Circularity as an MCP client; edge case 27).

A source set up by hand is pointed at source-sim's MCP demo server (/mcp-demo) with source.update mode "mcp"; a sync
calls its read tool `list_returns` with the SDK's streamable HTTP client, and the items become records for the
source's field mapping and the canonical store, as the configured adapter's records do. A server that does not answer
fails the sync: the source is failing and retries later. The module removes every source it made.
"""

import pytest
from sqlalchemy import text

from di.connectors import connection
from di.connectors.mcp_client import call_tool, rows_of
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from tests.helpers import call

SIM = get_settings().source_sim_url.rstrip("/")
MAPS = [["asset_id", "MCP-AST-101", "asset.asset_id", "MCP-AST-101", "Pass-through"]]
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping")
_made: list[str] = []


def teardown_module():
    with engine.begin() as c:
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": _made})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM failed_record WHERE source_id = ANY(:i)"), {"i": _made})
        c.execute(text("DELETE FROM provenance WHERE source_id = ANY(:i)"), {"i": _made})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = ANY(:i)"), {"i": _made})
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": _made})
        c.execute(text("DELETE FROM state_item WHERE collection = 'source_config' AND id = ANY(:i)"), {"i": _made})


def _new_source(name: str) -> str:
    d = {"type": "erp", "name": name, "vendor": "Sandbox", "ver": "", "env": "Test", "url": SIM + "/sandbox/demo",
         "method": "api", "cfg": {"spec": "REST"}, "interval": 15, "auth": "No authentication", "owner": ""}  # fmt: skip
    body = {"mode": "new", "id": "", "d": d, "maps": MAPS, "ops": {"read": ["GET /records"], "write": []}, "note": ""}
    r = call("source.update", body, "developer")
    assert r["ok"], r
    sid = str(r["output"]["source_id"])
    _made.append(sid)
    return sid


def _to_mcp(sid: str, url: str) -> dict:
    d = {"url": url, "tool": "list_returns", "arguments": {"limit": 10}, "resource_key": "returns", "id_field": "return_id"}
    return call("source.update", {"mode": "mcp", "id": sid, "d": d, "maps": [], "ops": {}}, "developer")


def test_the_demo_server_answers_the_sdk_client():
    rows = rows_of(call_tool(SIM + "/mcp-demo", "list_returns", {"limit": 3}))
    assert [r["return_id"] for r in rows] == ["RMA-7001", "RMA-7002", "RMA-7003"]


def test_mcp_source_sync_maps_records():
    sid = _new_source("Returns over MCP")
    r = _to_mcp(sid, SIM + "/mcp-demo")
    assert r["ok"], r
    with SessionLocal() as s:
        conn = connection.connection_for(s, sid)
        assert conn is not None and conn.protocol == "mcp" and conn.base_url == SIM + "/mcp-demo"
        assert conn.resources == [
            {"name": "returns", "path": "mcp:list_returns", "tool": "list_returns", "arguments": {"limit": 10},
             "id_field": "return_id"},
        ]  # fmt: skip
    out = run_sync(sid, "manual", full=True)
    assert out["status"] == "ok" and out["records_read"] == 10 and out["records_failed"] == 0, out
    assert out["facts_written"] >= 10, out
    with engine.connect() as c:
        ids = c.execute(text("SELECT ext_id FROM raw_record WHERE source_id = :s ORDER BY ext_id"), {"s": sid}).scalars()
        assert list(ids) == [f"RMA-{7001 + k}" for k in range(10)]
        n = c.execute(text("SELECT count(*) FROM provenance WHERE source_id = :s"), {"s": sid}).scalar_one()
        assert n >= 10
        st = c.execute(text("SELECT status FROM source_system WHERE id = :s"), {"s": sid}).scalar_one()
        assert st == "live"


def test_mcp_source_down_marks_failing():
    sid = _new_source("Returns over a dead MCP server")
    assert _to_mcp(sid, SIM + "/mcp-nowhere")["ok"]
    out = run_sync(sid, "manual", full=True)
    assert out["status"] == "failed" and "did not answer list_returns" in (out["error"] or ""), out
    with engine.connect() as c:
        row = c.execute(text("SELECT status, fail_streak, next_retry_at FROM source_system WHERE id = :s"), {"s": sid}).one()
    assert row.status == "failing" and row.fail_streak == 1 and row.next_retry_at is not None


@pytest.mark.parametrize(
    ("d", "message"),
    [
        ({"url": "not a url", "tool": "list_returns", "resource_key": "returns"}, "Enter the MCP server's http(s) URL."),
        ({"url": SIM + "/mcp-demo", "tool": "", "resource_key": "returns"}, "Name the tool to call and the resource key."),
        ({"url": SIM + "/mcp-demo", "tool": "list_returns", "resource_key": "r", "arguments": []},
         '"arguments" must be an object.'),
    ],
)  # fmt: skip
def test_mcp_mode_validates(d, message):
    sid = _made[0] if _made else _new_source("Returns over MCP (validation)")
    r = call("source.update", {"mode": "mcp", "id": sid, "d": d, "maps": [], "ops": {}}, "developer")
    assert r["error"] == {"code": "validation_error", "message": message}
