"""Plan 9, P9-3.4 (story TF-01): the tool fleet's returns open cases from the contract feed.

The fleet mock's `returns` (18 open) are read by the adapter with the tool class of their line, and handed to the
`fleet` source's published ingest workflow, whose Open case step (x_case) takes the reason from each record
(`reason_field` = the return `kind`) and copies fields into the case's facts (`facts`). Each case is decided through
`decide_case` (I-6) by `intake.open_case`; no second path. The same serial and reason open one case; a later swap for
the same serial opens a second.

Needs source-sim with the fleet mock (restart it after the change, R14); the module is skipped, with the reason, when it
lacks it. It starts and ends with the demo reset (which drops the sources, the org unit and the cases it made).
"""

import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from di import worker
from di.connectors import sync
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core import clock, state
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.actions.registry import ActionError
from di.services.cases import intake
from di.workflow import blocks
from di.workflow.steps import flow
from tests import starting
from tests.helpers import call, client

SID = "fleet"
ORG = "tool-fleet-a"
API = get_settings().source_sim_url + "/fleet/api/v1"
KEY = {"x-api-key": "fleet-demo-key"}
CFG = {"template": "tool_fleet", "reason": "contract_end", "asset_field": "serial", "org_unit_id": ORG,
       "reason_field": "kind", "facts": ["toolClass", "contractId", "lineId", "site"]}  # fmt: skip
FT = {"contract_end": "Fleet management", "swap": "Fleet management", "service_order": "Repair center",
      "pool_excess": "Tool pool"}  # fmt: skip


def served() -> bool:
    try:
        return httpx.get(API + "/returns", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the fleet mock: restart it (R14)")


def _cases() -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT data FROM case_record WHERE owner = :o ORDER BY id"), {"o": ORG})
        return list(rows.scalars())


def _graph(wid: str) -> dict:
    with SessionLocal() as s:
        g = state.get(s, "workflows", wid)["graph"]
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    conn["cfg"] = {**(conn.get("cfg") or {}), "resources": ["returns"]}
    case = {"id": "case", "k": "xf", "ref": "x_case", "x": conn["x"] + 120, "y": conn["y"], "cfg": CFG}
    return g | {"nodes": [conn, case], "edges": [{"id": f"{conn['id']}>case", "a": conn["id"], "b": "case", "locked": False}]}


@pytest.fixture(scope="module")
def fleet():
    """Admin makes the org unit, the Developer connects `fleet` bound to it and publishes the ingest workflow with the
    Open case step; a full sync then opens the cases."""
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "segment", "name": "Tool fleet A"}, "admin")["ok"]
    assert call("source.reconnect", {"source_id": SID}, "developer")["ok"]
    with engine.begin() as c:  # bound to the org unit (the step names it too)
        c.execute(text("UPDATE source_system SET org_unit_id = :o WHERE id = :s"), {"o": ORG, "s": SID})
    r = call("workflow.create", {"type": "ingest", "src": SID}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
    body = {"id": wid, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": _graph(wid)}
    assert call("workflow.save", body, "developer")["ok"]
    pub = call("workflow.publish", {"id": wid}, "developer")
    assert pub["ok"], pub
    out = sync.run_sync(SID, "manual", True)
    assert out["status"] in ("ok", "partial"), out
    # the cases opened before the sync wrote their contract lines (GR-07, P9-3.6) were held: the lines queued a recheck of each
    with engine.connect() as c:
        rechecks = list(
            c.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars()
        )
    for payload in rechecks:
        worker.HANDLERS["case.gateRecheck"](payload)
    yield wid
    starting.reset()


# ------------------------------------------------------------------ the step and the block (no source-sim)
def test_x_case_without_new_settings_unchanged():
    """An Open case step configured as before (fixed reason, no reason_field, no facts) reads its settings as ever."""
    assert blocks.default_cfg("x_case") == {"template": "industrial", "reason": "rma", "asset_field": "", "org_unit_id": "",
                                            "only_if": "", "reason_field": "", "facts": []}  # fmt: skip
    assert flow.reason_of({"kind": "swap"}, "rma", "") == "rma"
    assert flow.facts_of_record({"toolClass": "CMH"}, []) == {}
    assert set(intake.REASONS) >= {"swap", "service_order", "pool_excess"}
    assert set(blocks.CASE_REASONS) == set(intake.REASONS) - {"contract_refresh", "service_ticket"}
    # only the daily scan opens a refresh (P9-5.1); only the sdesk hook opens a ticket's case (P9-4.3)


def test_tf_01_reason_comes_from_the_record():
    """The reason of each record: its `kind` through the map (a value left out of the map is used as it is)."""
    rec = {"kind": "service_order", "toolClass": "CMH", "contractId": "FC-1"}
    assert flow.reason_of(rec, "contract_end", "kind") == "service_order"
    assert flow.reason_of(rec, "contract_end", "kind: service_order=swap, x=y") == "swap"
    assert flow.reason_of({}, "contract_end", "kind") == "contract_end"  # no value: the fixed reason
    assert flow.facts_of_record(rec, ["toolClass", "contractId", "site"]) == {"tool_class": "CMH", "contract_id": "FC-1"}


def test_tf_01_return_adapter_adds_the_tool_class():
    rec = Record("returns", "FR-1", {"returnId": "FR-1", "serial": "CMH-1"})
    out = ADAPTERS[SID].with_class(rec, {"CMH-1": "CMH"})
    assert out.payload == {"returnId": "FR-1", "serial": "CMH-1", "toolClass": "CMH"} and out.ext_id == "FR-1"
    assert ADAPTERS[SID].map(out) == []  # still no fact


def test_tf_01_tool_return_facts_are_normalised():
    f = intake.tool_return_facts(
        {"tool_class": "CMH", "contract_id": "FC-30117", "line_id": "FL-30117-03", "site": "Houston"}, "CMH-48213", "swap"
    )
    assert (f["cls"], f["ft"], f["serial"], f["flow"], f["contract_id"]) == (
        "CMH",
        "Fleet management",
        "CMH-48213",
        "returns",
        "FC-30117",
    )
    assert intake.tool_return_facts({"cls": "BRK"}, "X", "manual") == {"cls": "BRK"}  # not a return: left as given
    assert intake.tool_return_facts({"cls": "BRK", "ft": "Tool pool"}, "X", "swap")["ft"] == "Tool pool"  # given wins


# ------------------------------------------------------------------ a sync of the seeded returns
@needs_mock
def test_tf_01_one_case_per_return(fleet):
    cases = _cases()
    assert len(cases) == 18, len(cases)
    assert {c["template"] for c in cases} == {"tool_fleet"}
    for c in cases:
        reason = c["intake"]["reason"]
        assert reason in FT and c["intake"]["key"] == intake.intake_key(c["assetId"], reason)
        assert c["cls"] and c["contract_id"] and c["line_id"] and c["flow"] == "returns" and c["serial"] == c["assetId"]
        assert c["ft"] == FT[reason], c
    cmh = next(c for c in cases if c["assetId"] == "CMH-48213")
    assert (cmh["intake"]["reason"], cmh["ft"], cmh["cls"], cmh["site"], cmh["contract_id"]) == (
        "contract_end", "Fleet management", "CMH", "Houston", "FC-30117",
    )  # fmt: skip
    assert cmh["routes"] and cmh["rec_index"] is not None  # decided through decide_case


@needs_mock
def test_tf_01_duplicate_refused(fleet):
    """The webhook for the return replayed answers `duplicate`; the intake names the open case; the count stays 18."""
    ev = {"specversion": "1.0", "id": f"t-{uuid.uuid4()}", "source": f"/vendor/{SID}", "type": "fleet.return.created",
          "time": clock.now().isoformat().replace("+00:00", "Z"), "data": {"serial": "CMH-48213"}}  # fmt: skip
    secret = get_settings().webhook_secret.get_secret_value()
    body = json.dumps(ev).encode()
    head = {"x-signature": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            "content-type": "application/json"}  # fmt: skip
    assert client.post(f"/api/webhooks/{SID}", content=body, headers=head).status_code == 202
    again = client.post(f"/api/webhooks/{SID}", content=body, headers=head)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    open_id = next(c["id"] for c in _cases() if c["assetId"] == "CMH-48213")
    r = call("case.open", {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "CMH-48213",
                           "reason": "contract_end", "facts": {"cls": "CMH"}}, "admin")  # fmt: skip
    assert r["ok"] is False and r["error"]["code"] == "duplicate" and open_id in r["error"]["message"], r
    again_sync = sync.run_sync(SID, "manual", True)
    assert again_sync["status"] in ("ok", "partial")
    assert len(_cases()) == 18
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))
        c.execute(text("DELETE FROM webhook_event WHERE event_id LIKE 't-%'"))


@needs_mock
def test_tf_01_same_serial_new_reason_opens(fleet):
    with SessionLocal() as s:
        c = intake.open_case(
            s,
            {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "CMH-48213", "reason": "swap",
             "facts": {"tool_class": "CMH", "contract_id": "FC-30117", "line_id": "FL-30117-03", "site": "Houston"}},
            "system",
        )  # fmt: skip
        s.commit()
        with pytest.raises(ActionError) as e:
            intake.open_case(s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "CMH-48213", "reason": "swap",
                                 "facts": {"cls": "CMH"}}, "system")  # fmt: skip
        assert e.value.code == "duplicate"
        s.rollback()
    assert c["ft"] == "Fleet management" and c["intake"]["reason"] == "swap"
    assert len([x for x in _cases() if x["assetId"] == "CMH-48213"]) == 2
