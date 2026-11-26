"""Plan 9, P9-10.12 (stories TN-15, TN-16 and TN-17): the telecom pack's customer diversions and the blocked wipe skip.

The pack ships three sample diversions (`customer_layer.sample_diversions`, P9-10.1); a customer publishes them as overlay
operations (P9-1.3) and `decide_case` applies them (`add_step` lists a required step, `shortcut` is refused when it would
skip a locked compliance guardrail). The pack file never changes. The writers of the two steps (`security_inspection`: a
person's checklist step, no system write; `firmware_upgrade`: the test bench's refurb order) are tested on a stubbed client.
Pure but for the audited refusal, which goes through the action `overlay.save`. Legal note: the wipe standard is pack data;
Kinective's Legal team reviews it before it is relied on.
"""

import json
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors.http import SourceError
from di.core.db import engine
from di.services.agents.forbidden import forbidden
from di.services.instructions import writers
from di.services.modeler.gates import pack_gates
from di.services.modeler.overlay import OverlayError, apply_overlay, parse_ops
from di.services.modeler.pack import Diversion, Pack, load_pack
from tests.helpers import call
from tests.test_tn_routing import PACK, decide, route, sample

ORG = "Customer A"
PACK_FILE = json.dumps(json.loads(PACK.model_dump_json()), sort_keys=True)
SAMPLES = {d.op["id"]: d for d in PACK.customer_layer.sample_diversions}
BLOCKED_TEXT = (
    "Blocked: this skips the compliance guardrail Configuration wiped, certificate on file, before any route at Condition."
)


def _op(sample_id: str, n: int) -> dict[str, Any]:
    """The sample diversion as the customer layer's editor saves it: its operation under an `op-<n>` id."""
    return {k: v for k, v in SAMPLES[sample_id].op.items() if k != "id"} | {"id": f"op-{n}"}


def _with(*ids: str) -> Pack:
    return apply_overlay(PACK, parse_ops([_op(i, n) for n, i in enumerate(ids, 1)]))


@pytest.fixture
def clean_audit():
    def wipe() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM customer_overlay"))
            conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked' OR type LIKE 'action.overlay.%'"))
            conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'overlay.%'"))

    wipe()
    yield
    wipe()


def _steps(d: Any, gate: str) -> list[tuple[str, str, str]]:
    return [(x["step"], x["owner"], x["stage"]) for x in d.required_steps if x["gate"] == gate]


def test_tn_15_core_site_security_inspection():
    pack = _with("DV-TN-CORE")
    core = decide(sample("TN-S1") | {"asset.site_kind": "core"}, pack=pack)
    edge = decide(sample("TN-S1"), pack=pack)  # the sample sits at an edge site
    plain = decide(sample("TN-S1") | {"asset.site_kind": "core"})
    assert _steps(core, "op-1") == [("Security inspection", "test_bench_lead", "condition")] and core.diversions == ["op-1"]
    assert _steps(edge, "op-1") == [] and edge.diversions == []
    assert (core.route, core.net) == (plain.route, plain.net)  # a step adds work; it never changes the numbers
    assert json.dumps(json.loads(load_pack("telecom_network").model_dump_json()), sort_keys=True) == PACK_FILE
    assert PACK.diversions == [] and pack.diversions[0].kind == "step"  # the template and the pack file stay as they are


def test_tn_16_firmware_behind_upgrade_step():
    pack = _with("DV-TN-FW")
    s8 = decide(sample("TN-S8") | {"demand.id": "SD-207", "demand.model": "RTR-880"}, pack=pack)
    s1 = decide(sample("TN-S1"), pack=pack)  # firmware current: no step
    assert _steps(s8, "op-1") == [("Firmware upgrade", "test_bench_lead", "condition")]
    assert _steps(s1, "op-1") == [] and s8.route == "redeploy"
    assert [d.stage for d in pack.diversions] == ["condition"]  # stage 3 of 7


def test_tn_17_wipe_skip_blocked_with_suggestion(clean_audit):
    sample_skip = SAMPLES["DV-TN-SKIP"]
    assert sample_skip.blocked and "G-NET-CFG" in sample_skip.reason
    assert "send an already wiped spare from the nearest pool" in sample_skip.reason
    assert next(g for g in pack_gates(PACK) if g.id == "G-NET-CFG").type == "Compliance"
    assert next(g for g in PACK.guardrails if g.id == "G-NET-CFG").locked
    with pytest.raises(OverlayError) as e:
        apply_overlay(PACK, parse_ops([_op("DV-TN-SKIP", 1)]))
    assert (e.value.code, e.value.guardrail, e.value.message) == ("skips_compliance", "G-NET-CFG", BLOCKED_TEXT)
    r = call("overlay.save", {"pack_key": "telecom_network", "org_unit_id": ORG, "ops": [_op("DV-TN-SKIP", 1)]}, "planner-a")
    assert r["ok"] is False and r["error"]["overlay_code"] == "skips_compliance" and r["error"]["message"] == BLOCKED_TEXT
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT payload FROM domain_event WHERE type = 'overlay.blocked'")).all()
        saved = conn.execute(text("SELECT count(*) FROM customer_overlay")).scalar()
    assert len(rows) == 1 and saved == 0  # one audit row, nothing saved: the wipe stays a person's to decide
    p = rows[0].payload
    assert (p["guardrail"], p["by"], p["pack_key"], p["op"]["id"]) == ("G-NET-CFG", "planner-a", "telecom_network", "op-1")


def test_tn_17_an_agent_never_approves_a_customer_overlay():
    assert forbidden("overlay.approve") and forbidden("overlay.reject")  # which diversions take effect is a person's call


def test_order_invariant_telecom_network_with_both_diversions():
    both = _with("DV-TN-CORE", "DV-TN-FW")
    swapped = _with("DV-TN-FW", "DV-TN-CORE")
    c = sample("TN-S5") | {"asset.firmware_major_gap": 2, "asset.site_kind": "core"}  # wipe failed twice
    a, b = decide(c, pack=both), decide(c, pack=swapped)
    assert a.trace == b.trace and (a.route, a.net) == (b.route, b.net) and a.hold == b.hold
    assert "G-NET-CFG" in [g.gate_id for g in a.gates if not g.passed] and a.hold is not None
    assert route(a, "resell")["excluded"]  # no diversion revives resale
    assert sorted(x["step"] for x in a.required_steps) == sorted(x["step"] for x in b.required_steps)
    assert {"destroy_storage", "Security inspection", "Firmware upgrade"} <= {x["step"] for x in a.required_steps}
    assert [d.kind for d in both.diversions] == ["step", "step"] and isinstance(both.diversions[0], Diversion)


class _Reply:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc

    def json(self) -> dict[str, Any]:
        return self.doc


class _Bench:
    def __init__(self, fail: SourceError | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail = fail

    def request(self, method: str, path: str, **kw: Any) -> _Reply:
        self.calls.append((method, path, kw["json"]))
        if self.fail:
            raise self.fail
        return _Reply({"orderId": "RF-0001", "serial": kw["json"]["serial"], "status": "created"})

    def close(self) -> None:
        pass


def test_tn_15_security_inspection_writes_to_no_system(monkeypatch):
    monkeypatch.setattr(writers, "client", lambda s, sid: pytest.fail("no system is written to"))
    with pytest.raises(writers.NotApplicable, match="checklist"):
        writers.WRITERS["security_inspection"](None, {}, {"serial": "SN-TN-0001"}, {})  # type: ignore[arg-type]


def test_tn_16_firmware_upgrade_orders_a_refurb_of_kind_firmware(monkeypatch):
    bench = _Bench()
    monkeypatch.setattr(writers, "client", lambda s, sid: bench if sid == "tn_bench" else pytest.fail(sid))
    out = writers.WRITERS["firmware_upgrade"](None, {}, {"serial": "SN-TN-0008"}, {})  # type: ignore[arg-type]
    assert bench.calls == [("POST", "/refurb-orders", {"serial": "SN-TN-0008", "kind": "firmware"})]
    assert out.doc_ref == "RF-0001" and out.detail["serial"] == "SN-TN-0008" and out.request[0]["call"] == "POST refurb-orders"
    with pytest.raises(writers.NotApplicable):
        writers.WRITERS["firmware_upgrade"](None, {}, {}, {})  # type: ignore[arg-type]
    bad = _Bench(SourceError("client", "No bench result for SN-TN-0008.", 404))
    monkeypatch.setattr(writers, "client", lambda s, sid: bad)
    with pytest.raises(writers.Refused):
        writers.WRITERS["firmware_upgrade"](None, {}, {"serial": "SN-TN-0008"}, {})  # type: ignore[arg-type]
