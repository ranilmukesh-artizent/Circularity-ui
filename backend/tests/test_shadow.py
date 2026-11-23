"""MVP-3.5: while a case's flow is in shadow, each re-evaluation also decides with the draft's rules and records both;
the live decision is unchanged."""

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal, engine
from di.repositories import flows
from di.services.cases import store
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call

ONLY_MATERIAL_A_C = ("IR-01", "require", "material", {"grade": ["C"], "owner": ["Customer A"]})


@pytest.fixture(autouse=True)
def fresh():
    def reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM domain_event"))
            conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
            conn.execute(text("DELETE FROM action_journal"))
        store.reset()
        state.reset()
        flowkit.reset_flows()

    reset()
    yield
    reset()


def _shadow_flow() -> int:
    """Customer A's own flow, published as the default, with a draft that sends grade-C returns to material recovery
    approved into shadow."""
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(default_flow(load_template("industrial")), *ONLY_MATERIAL_A_C)
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    return int(fid)


def _reevaluate(case_id: str) -> dict:
    ok(call("decision.decline", {"case_id": case_id, "reason": "Re-check with the new policy."}, "admin"))
    ok(call("case.reevaluate", {"case_id": case_id}, "admin"))
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return c


def _rows(fid: int) -> list:
    with engine.begin() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT flow_id, dver, case_id, live_route, shadow_route, live_net, shadow_net FROM shadow_decision "
                    "WHERE flow_id = :f ORDER BY id"
                ),
                {"f": fid},
            )
        )


def test_shadow_row_written_live_unchanged():
    fid = _shadow_flow()
    c = _reevaluate("RT-1065")
    rec = c["recommendation"]
    material = next(r for r in c["routes"] if r["id"] == "material")
    assert rec["id"] != "material" and not material["excluded"]
    assert "rulesApplied" not in c and c["flowVer"] == 1  # the live decision used the published graph only
    (row,) = _rows(fid)
    assert (row.flow_id, row.dver, row.case_id, row.live_route, row.shadow_route) == (fid, 2, "RT-1065", rec["id"], "material")
    assert (float(row.live_net), float(row.shadow_net)) == (rec["net"], material["net"])


def test_shadow_stats():
    fid = _shadow_flow()
    cases = [_reevaluate(cid) for cid in ("RT-1065", "RT-1079", "RT-1062")]  # grade C, grade C, grade B (out of scope)
    mat = [next(r for r in c["routes"] if r["id"] == "material")["net"] for c in cases[:2]]
    dv = sum(m - c["recommendation"]["net"] for m, c in zip(mat, cases[:2], strict=True))
    with SessionLocal() as s:
        st = flows.shadow_stats(s, fid)
    assert {k: st[k] for k in ("n", "agree", "disagree")} == {"n": 3, "agree": 1, "disagree": 2}
    assert st["dv"] == pytest.approx(dv)
    ok(call("flow.publish", {"flow_id": fid}, "approver"))
    _reevaluate("RT-1106")  # published: no shadow any more
    with SessionLocal() as s:
        assert flows.shadow_stats(s, fid)["n"] == 3
