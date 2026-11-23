"""Sources bound to org units (plan 8, MVP-1.4): `source_system.org_unit_id`, set by source.update's `org_unit_id`.

Null means the source is shared by every org, which every demo source is. The module creates flat-file sources (no
connection, no sync) and org units starting "t-src-"; it ends with the demo reset (tests/starting.py), which removes the
sources it made, and then removes its org units.
"""

from sqlalchemy import text

from di.core import golden
from di.core.db import engine
from tests import starting
from tests.helpers import call, client, h

DEMO_IDS = [s["id"] for s in golden.load("sources")["sources"]]


def setup_module():
    starting.reset()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO org_unit (id, parent_id, kind, name) VALUES ('t-src-co', 'workspace', 'company', 'Src Co') "
                 "ON CONFLICT DO NOTHING")
        )  # fmt: skip


def teardown_module():
    starting.reset()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM org_unit WHERE id LIKE 't-src-%'"))


def _new(org: str | None, name: str = "Org ERP", user: str = "developer") -> dict:
    d = {"type": "erp", "name": name, "vendor": "SAP S/4HANA", "ver": "", "env": "Test", "url": "", "method": "file",
         "cfg": {}, "interval": 0, "auth": "", "owner": ""}  # fmt: skip
    body = {"mode": "new", "id": "", "d": d, "maps": [["MATNR", "M-1", "asset.asset_id", "M-1", "Pass-through"]],
            "ops": {"read": [], "write": []}, "note": "", "org_unit_id": org}  # fmt: skip
    return call("source.update", body, user)


def _org_of(sid: str) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": sid}).scalar_one()


def _screen_row(sid: str) -> dict:
    rows = client.get("/api/screens/integration/sources", headers=h("developer")).json()["sources"]
    return next(r for r in rows if r["id"] == sid)


def test_demo_sources_unbound():
    with engine.connect() as conn:
        bound = conn.execute(
            text("SELECT id FROM source_system WHERE id = ANY(:i) AND org_unit_id IS NOT NULL"), {"i": DEMO_IDS}
        ).all()
    assert bound == []
    assert _screen_row("erp")["org_unit_id"] is None


def test_new_source_bound_to_company():
    r = _new("t-src-co")
    assert r["ok"], r
    sid = r["output"]["source_id"]
    assert _org_of(sid) == "t-src-co"
    assert _screen_row(sid)["org_unit_id"] == "t-src-co"


def test_second_instance_binds_to_another_org():
    first, second = _new("t-src-co", "ERP one"), _new("Customer B", "ERP two")
    assert first["ok"] and second["ok"], (first, second)
    a, b = first["output"]["source_id"], second["output"]["source_id"]
    assert a != b and a.startswith("erp_") and b.startswith("erp_")
    assert (_org_of(a), _org_of(b)) == ("t-src-co", "Customer B")


def test_unknown_org_refused():
    r = _new("t-src-missing")
    assert r["error"] == {"code": "validation_error", "message": "No org unit t-src-missing."}


def test_unbound_is_shared():
    r = _new(None, "Shared ERP")
    assert r["ok"], r
    assert _org_of(r["output"]["source_id"]) is None
