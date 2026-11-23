"""MVP-10.2: an org's configuration pack. org.exportPack reads what an org unit runs on (its sources' connection
settings without secrets, their mappings, the published workflows that use them, its published decision flows);
org.importPack sets the same up for another org unit as drafts only: sources disconnected and without credentials
(a person enters them), workflows as drafts, flows as the org's own fork with a draft.

The module connects the catalogue's Postgres system for Customer A (with its sandbox key), publishes an ingest workflow
for it and a Customer A flow with a rule. It starts and ends with the demo reset and the seeded flows.
"""

import copy
import json

import pytest
from sqlalchemy import text

from di.connectors import catalog
from di.core import state
from di.core.db import SessionLocal, engine
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit, starting
from tests.flowkit import ok
from tests.helpers import call

CAT = "postgres"
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "failed_record", "webhook_event", "field_mapping",
          "source_connection", "source_secret")  # fmt: skip
RULE = ("IR-07", "exclude", "material", {"grade": ["D"]})


def _clean() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind IN ('sync.source', 'workflow.run')"))
        made = list(c.execute(text("SELECT id FROM source_system WHERE id LIKE :p"), {"p": CAT + "%"}).scalars())
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
    starting.reset()
    flowkit.reset_flows()


def setup_module():
    _clean()


def teardown_module():
    _clean()


@pytest.fixture(scope="module")
def org_a() -> dict:
    """Customer A's configuration: the Postgres source with a stored secret, its published workflow, its own flow."""
    maps = ok(call("mapping.catalogSuggest", {"catalog_id": CAT}, "developer"))["rows"]
    secret = catalog.template(CAT)["demo_secret"]
    body = {"mode": "catalog", "id": "", "d": {"catalog": CAT, "auth": "key", "scopes": ["read"]}, "maps": maps,
            "ops": {}, "secret": secret, "org_unit_id": "Customer A"}  # fmt: skip
    ok(call("source.update", body, "developer"))
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))  # nothing reads it here
    wid = ok(call("workflow.create", {"type": "ingest", "src": CAT}, "developer"))["id"]
    ok(call("workflow.publish", {"id": wid}, "developer"))
    fid = flowkit.fork_and_publish("Customer A", [RULE])
    return {"secret": secret, "wid": wid, "fid": fid}


def _export(org: str = "Customer A", user: str = "admin") -> dict:
    return call("org.exportPack", {"org_unit_id": org}, user)


def _source(sid: str) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT * FROM source_system WHERE id = :i"), {"i": sid}).mappings().one())


def test_export_has_no_secrets(org_a):
    pack = ok(_export())
    blob = json.dumps(pack)
    assert org_a["secret"][-4:] not in blob and org_a["secret"] not in blob
    assert pack["version"] == 1 and pack["org"]["id"] == "Customer A"
    (src,) = pack["sources"]
    assert src["id"] == CAT and src["connection"]["base_url"].endswith(catalog.template(CAT)["base_path"])
    assert not any(k in src for k in ("secret", "credential")) and "audit" not in src["config"]
    assert pack["mappings"][CAT] and all(isinstance(m, list) for m in pack["mappings"][CAT])
    (wf,) = pack["workflows"]
    assert wf["source_id"] == CAT and any(s["ref"] == CAT for s in wf["steps"])
    rules = [n for n in pack["flows"]["industrial"]["nodes"] if n["t"] == "rule"]
    assert [n["rid"] for n in rules] == ["IR-07"]
    assert set(pack["flows"]) == {"industrial", "tool_fleet", "device"}
    assert _export(user="planner-a")["error"]["code"] in ("forbidden", "out_of_scope")


def test_import_creates_drafts_only(org_a):
    pack = ok(_export())
    out = ok(call("org.importPack", {"pack": pack, "target_org_unit_id": "Customer B"}, "admin"))
    created = out["created"]
    (sid,) = created["sources"]
    assert sid != CAT and sid.startswith(CAT)
    row = _source(sid)
    assert (row["status"], row["org_unit_id"]) == ("disconnected", "Customer B")
    with engine.connect() as c:
        n_secret = c.execute(text("SELECT count(*) FROM source_secret WHERE source_id = :i"), {"i": sid}).scalar_one()
        base = c.execute(text("SELECT base_url FROM source_connection WHERE source_id = :i"), {"i": sid}).scalar_one()
        jobs = c.execute(text("SELECT count(*) FROM job WHERE payload->>'source_id' = :i"), {"i": sid}).scalar_one()
    assert n_secret == 0 and jobs == 0 and base == pack["sources"][0]["connection"]["base_url"]
    assert out["needs"] == [f"credentials for {pack['sources'][0]['name']}"]
    assert created["mappings"] == [sid]
    with SessionLocal() as s:
        wfs = [state.get(s, "workflows", w) for w in created["workflows"]]
    assert len(wfs) == 1 and wfs[0]["status"] == "draft" and "pub" not in wfs[0] and wfs[0]["src"] == sid
    assert {n["ref"] for n in wfs[0]["graph"]["nodes"] if n["k"] in ("conn", "wconn", "map")} == {sid}
    assert len(created["flows"]) == 3
    for fid in created["flows"]:
        f, _ = flowkit.get(fid)
        assert (f.org_unit_id, f.status) == ("Customer B", "draft")
        assert f.published == default_flow(load_template(f.template_key))  # nothing of A's is live for B
    ind = next(flowkit.get(f)[0] for f in created["flows"] if flowkit.get(f)[0].template_key == "industrial")
    assert ind.draft == pack["flows"]["industrial"]


def test_import_into_other_org_scoped(org_a):
    pack = ok(_export())
    before_a = flowkit.get(org_a["fid"])[0]
    out = ok(call("org.importPack", {"pack": copy.deepcopy(pack), "target_org_unit_id": "Customer C"}, "admin"))
    (sid,) = out["created"]["sources"]
    assert _source(sid)["org_unit_id"] == "Customer C" and _source(CAT)["org_unit_id"] == "Customer A"
    after_a = flowkit.get(org_a["fid"])[0]
    assert (after_a.status, after_a.ver, after_a.published) == (before_a.status, before_a.ver, before_a.published)
    with SessionLocal() as s:
        assert state.get(s, "workflows", org_a["wid"])["status"] == "published"
    # the target is the one the pack lands in; a missing unit or a person without manageOrgs is refused
    bad = call("org.importPack", {"pack": pack, "target_org_unit_id": "Nowhere"}, "admin")
    assert bad["error"]["code"] == "not_found"
    assert call("org.importPack", {"pack": pack, "target_org_unit_id": "Customer A"}, "planner-a")["error"]["code"] in (
        "forbidden", "out_of_scope")  # fmt: skip
    assert call("org.importPack", {"pack": {"version": 2}, "target_org_unit_id": "Customer C"}, "admin")["error"][
        "code"] == "validation_error"  # fmt: skip
