"""P9-3.20 (story GR-03, I-4; R21): the fit-for-use threshold of harvested parts is pack data owned by Quality
(`customer_layer.params["valuer.rulMin"]`, 50, raise-only for a customer). A customer raises it through the overlay
(`set_param`), approved by a different person; lowering it is refused naming GR-03. With no overlay every decision is
unchanged. No new action: the overlay actions' approve and return are already forbidden to agents."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.services.agents.forbidden import forbidden
from di.services.cases import intake
from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.overlay import OverlayError, SetParam, apply_overlay
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_fleet
from tests.helpers import call, client, h

AS_OF = datetime(2026, 10, 2, tzinfo=UTC)
PATH = "valuer.rulMin"
MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."
REF = {"pack_key": "tool_fleet", "org_unit_id": "Customer A"}


def _op(value: float, seen: float = 50) -> dict:
    return {"id": "op-1", "op": "set_param", "path": PATH, "value": value, "seen": seen}


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked' OR type LIKE 'action.overlay.%'"))
        conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'overlay.%'"))


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    yield
    _reset()


def _raised(value: float):
    return apply_overlay(load_pack("tool_fleet"), [SetParam(id="op-1", op="set_param", path=PATH, value=value, seen=50)])


def _case() -> dict:
    """A combihammer whose first part is at 55% life and the others at 70%, each with an open repair order."""
    parts = [pn for pn, _ in tool_fleet.CLS["CMH"]["parts"]]
    wo = {pn: [{"id": f"WO-{i}", "who": "Houston depot", "backorder": False}] for i, pn in enumerate(parts)}
    c = intake.tool_fleet_case("RT-9120", {"cls": "CMH", "grade": "C", "rul": 60, "dem": {"wo": wo}})
    c["partRul"] = [55] + [70] * (len(parts) - 1)
    return c


def _harvest(pack) -> dict:
    d = decide_case(_case(), pack, FlowVersion(None, 1, ()), AS_OF, queue=[])
    return next(r for r in d.routes if r["id"] == "harvest")


FIRST = tool_fleet.CLS["CMH"]["parts"][0][0]  # the part at 55% life


def _parts(route: dict) -> str:
    """The parts the harvest route certifies, as its term labels name them."""
    return " | ".join(t["label"] for t in route["terms"])


def _basis(pack) -> str:
    """The valuer's own harvest lines for the case, with the pack's threshold: `basis` says why a part counts."""
    from di.services.modeler.valuers import tool_inputs

    v = tool_fleet.value(_case(), "harvest", tool_inputs.fleet_params(pack), queue=[])
    return " | ".join(x["basis"] for x in v["lines"])


def test_rulmin_default_keeps_numbers():
    from di.services.modeler.valuers import tool_inputs

    pack = load_pack("tool_fleet")
    assert pack.customer_layer.params[PATH].value == 50 == tool_fleet.BASEP["rulMin"]
    assert tool_inputs.fleet_params(pack) == tool_fleet.BASEP  # no overlay: the valuer's own parameters, unchanged
    assert "55% life ≥ 50%" in _basis(pack) and "70% life ≥ 50%" in _basis(pack)
    assert FIRST in _parts(_harvest(pack))


def test_rulmin_raise_changes_harvest():
    pack = _raised(60)
    assert FIRST not in _parts(_harvest(pack))  # the part at 55% no longer counts
    assert "55% life" not in _basis(pack) and "70% life ≥ 60%" in _basis(pack)


def test_rulmin_lower_refused():
    for value in (40, 49):
        with pytest.raises(OverlayError) as e:
            _raised(value)
        assert e.value.code == "weakens" and "GR-03" in e.value.message, e.value.message
    with pytest.raises(OverlayError) as e:
        _raised(95)
    assert e.value.code == "out_of_range"
    r = call("overlay.save", REF | {"ops": [_op(40)]}, "planner-a")  # the action refuses it too, nothing is saved
    assert r["ok"] is False and r["error"]["overlay_code"] == "weakens" and "GR-03" in r["error"]["message"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM customer_overlay")).scalar_one() == 0


def _to_review(maker: str = "admin") -> None:
    assert call("overlay.save", REF | {"ops": [_op(60)]}, maker)["ok"]
    assert call("overlay.submit", REF, maker)["ok"]


def test_rulmin_maker_cannot_approve():
    _to_review("admin")
    r = call("overlay.approve", REF, "admin")
    assert r == {"ok": False, "error": {"code": "conflict", "message": MAKER_CHECKER}}
    assert call("overlay.approve", REF, "planner-a")["ok"] is False  # a planner is no approver either
    assert call("overlay.approve", REF, "approver")["ok"]
    with SessionLocal() as s:
        assert live_pack(s, {"template": "tool_fleet", "owner": "Customer A"}).customer_layer.params[PATH].value == 60


def test_rulmin_agent_cannot_approve():
    assert forbidden("overlay.approve") and forbidden("overlay.reject")
    _to_review("planner-a")
    for action, body in (("overlay.approve", REF), ("overlay.reject", REF | {"reason": "Not for this quarter, sorry."})):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator", "X-Circularity-Confirmed": "true"}
        r = client.post(f"/api/actions/{action}", json=body, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", (action, r.json())
    with SessionLocal() as s:
        assert live_pack(s, {"template": "tool_fleet", "owner": "Customer A"}).customer_layer.params[PATH].value == 50


def test_rulmin_tenant_boundary():
    other = {"pack_key": "tool_fleet", "org_unit_id": "Customer B"}
    r = call("overlay.save", other | {"ops": [_op(60)]}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert call("overlay.save", other | {"ops": [_op(60)]}, "admin")["ok"]
    assert call("overlay.submit", other, "admin")["ok"]
    assert call("overlay.approve", other, "approver")["ok"]
    with SessionLocal() as s:
        mine = live_pack(s, {"template": "tool_fleet", "owner": "Customer A"})
        theirs = live_pack(s, {"template": "tool_fleet", "owner": "Customer B"})
    assert mine.customer_layer.params[PATH].value == 50 and theirs.customer_layer.params[PATH].value == 60
    assert FIRST in _parts(_harvest(mine))  # Customer A's decisions are unchanged
    assert FIRST not in _parts(_harvest(theirs))
