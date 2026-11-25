"""Plan 8 MVP-9.3: the Windchill (plm_wc) adapter against source-sim's Windchill mock (MVP-9.2).

plm_wc is no demo source: it starts unregistered (no source_system row), so every demo screen and count is unchanged.
Registered (di.connectors.extra) and connected with source.reconnect, a sync maps the parts to `part.*` and the part
structures to `bom.*` lines, keyed per org unit of the source (schema.part_key, bom_key), so two Windchill instances
bound to two org units never collide.

Needs source-sim running. The module starts and ends with the demo reset (tests/starting.py), which removes the
sources it registered, and removes the part and BOM facts it wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.registry import ADAPTERS, adapter_for
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import bom_key, part_key
from tests import starting
from tests.helpers import call, client, h

SIM = get_settings().source_sim_url
SID = "plm_wc"
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
WC = SIM + "/Windchill/servlet/odata/ProdMgmt"
AUTH = ("di_connector", "Circularity-demo-wc-1")


def _forget_plm() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('part', 'bom')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('part', 'bom')"))


def setup_module():
    starting.reset()
    _forget_plm()


def teardown_module():
    starting.reset()
    _forget_plm()


def mock_parts() -> dict[str, dict]:
    """Number -> the mock's part, read straight from source-sim (every page)."""
    out, url = {}, f"{WC}/Parts"
    with httpx.Client(timeout=30, auth=AUTH) as c:
        while url:
            body = c.get(url).json()
            out |= {p["Number"]: p for p in body["value"]}
            url = body.get("@odata.nextLink")
    return out


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def connect(sid: str) -> dict:
    r = call("source.reconnect", {"source_id": sid}, "developer")
    assert r["ok"], r
    out = run_sync(sid, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    return out


def registered(org: str) -> str:
    with SessionLocal() as s:
        sid = extra.register(s, SID, org)
        s.commit()
    return sid


def test_demo_counts_unchanged_while_disconnected():
    """A connector is there, but no source row: the source map, the sources API and the syncs are the demo's."""
    assert SID in ADAPTERS and ADAPTERS[SID].vendor == "PTC Windchill" and ADAPTERS[SID].source_type == "plm"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21
    rows = client.get("/api/screens/integration/sources", headers=h("developer")).json()["sources"]
    assert {r["id"] for r in rows} == DEMO_IDS
    assert SID not in {r["id"] for r in client.get("/api/sources", headers=h("developer")).json()}
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_reconnect_registers_it_disconnected_first():
    """source.reconnect on the unregistered plm_wc registers it (disconnected, shared) and connects it."""
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    with engine.connect() as conn:
        row = conn.execute(text("SELECT vendor, type, status, org_unit_id FROM source_system WHERE id = :i"), {"i": SID}).one()
    assert tuple(row) == ("PTC Windchill", "plm", "live", None)
    starting.reset()  # gone again: no demo source
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": SID}).first() is None


def test_sync_maps_parts_and_bom():
    assert registered("Customer A") == SID
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == "disconnected"
    out = connect(SID)
    parts = mock_parts()
    assert out["records_read"] == len(parts) + 14  # every part, and the structure of the 8 + 6 tool assemblies
    seal = parts["VLT-SK-250M"]
    p = canonical("part", part_key("Customer A", "VLT-SK-250M"))
    assert p["data"] == {
        "number": "VLT-SK-250M", "name": seal["Name"], "revision": seal["Version"],
        "state": {"RELEASED": "released", "INWORK": "in_work", "OBSOLETE": "obsolete"}[seal["State"]["Value"]],
        "unit_cost": seal["UnitCost"], "org_unit_id": "Customer A",
    }  # fmt: skip
    prov = p["provenance"]["revision"][0]
    assert (prov["source_id"], prov["source_field"], prov["source_value"]) == (
        SID,
        "Version",
        f"{seal['Version']}.{seal['Iteration']}",
    )
    top = parts["0000100001"]
    line = canonical("bom", bom_key("Customer A", "0000100001", top["Version"], "VLT-SK-250M"))
    assert line["data"] == {
        "parent": "0000100001", "child": "VLT-SK-250M", "qty": 1.0, "parent_revision": top["Version"],
        "harvestable": seal["State"]["Value"] != "INWORK",
    }  # fmt: skip
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'bom' AND key LIKE :k"), {"k": "Customer A:%"}
        ).scalar_one()
    assert n == 8 * 6 + 21  # 6 lines per industrial assembly, and the 21 wear parts of the 6 tool assemblies


def test_two_orgs_two_windchill_instances_do_not_collide():
    with engine.connect() as conn:
        if conn.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": SID}).first() is None:
            pytest.fail("test_sync_maps_parts_and_bom registers plm_wc first")
    second = registered("Customer B")
    assert second == "plm_wc_2"
    with SessionLocal() as s:
        a = adapter_for(s, second)
    assert a is not None and a.source_id == second
    connect(second)
    a_part = canonical("part", part_key("Customer A", "VLT-SK-250M"))
    b_part = canonical("part", part_key("Customer B", "VLT-SK-250M"))
    assert (a_part["data"]["org_unit_id"], b_part["data"]["org_unit_id"]) == ("Customer A", "Customer B")
    assert {x["source_id"] for x in a_part["provenance"]["number"]} == {SID}
    assert {x["source_id"] for x in b_part["provenance"]["number"]} == {second}
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT split_part(key, ':', 1) AS org, count(*) AS n FROM canonical WHERE model = 'part' GROUP BY 1")
        ).all()
    orgs = {r.org: r.n for r in rows}
    assert orgs["Customer A"] == orgs["Customer B"] == len(mock_parts())


def test_sync_maps_tool_ratings():
    """P9-3.3: the soft attributes of a tool class's assembly and wear parts reach the canonical part."""
    wear = canonical("part", part_key("Customer A", "TF-CMH-01"))["data"]
    assert (wear["tool_class"], wear["rated_life_hours"], wear["criticality_weight"], wear["critical"]) == (
        "CMH", 1200, 0.4, True,
    )  # fmt: skip
    assert wear["name"] == "Motor armature" and "end_of_parts" not in wear
    asm = canonical("part", part_key("Customer A", "TF-CMH"))["data"]
    assert (asm["end_of_parts"], asm["successor"], asm["tool_class"]) == ("2028-06-30", "TF-CMH2", "CMH")
    assert "rated_life_hours" not in asm
    assert "rated_life_hours" not in canonical("part", part_key("Customer A", "VLT-SK-250M"))["data"]  # industrial
