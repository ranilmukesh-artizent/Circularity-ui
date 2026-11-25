"""P9-0.17 (review of P9-0.16): no new decision workflow is made, published or imported in Studio; the Modeler owns
decision rules. The demo's three decision workflows (WF-133..135) keep working (parity)."""

import copy

from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal, engine
from tests.helpers import call

DEV = "developer"
MSG = "Decision rules live in the Modeler"


def _reset() -> None:
    state.reset(["workflows", "workflow_runs"])


def _dec_draft() -> str:
    """A never-published, never-run decision draft, as an old install could still hold one."""
    with SessionLocal() as s:
        w = copy.deepcopy(state.get(s, "workflows", "WF-133"))
        w |= {"id": "WF-990", "status": "draft", "runsN": 0, "okN": 0, "pub": None, "last": None, "name": "Old dec draft"}
        state.add(s, "workflows", "WF-990", w)
        s.commit()
    return "WF-990"


def test_create_dec_kept_for_parity_p9_0_17():
    """workflow.create {type: dec} stays: the demo's golden scenario (fixtures/golden/workflow_writes.json) creates
    one, and publishes it, so create and publish stay as the demo has them. Studio's own Save refuses a new decision
    draft (P9-0.16) and an import refuses one (below)."""
    _reset()
    assert call("workflow.create", {"type": "dec"}, DEV)["ok"]
    _reset()


def test_demo_dec_workflows_still_publish_p9_0_17():
    _reset()
    for wid in ("WF-133", "WF-134", "WF-135"):
        r = call("workflow.publish", {"id": wid}, DEV)
        assert not (r["ok"] is False and r["error"]["message"] == MSG), (wid, r)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    _reset()


def test_import_dec_refused_p9_0_17():
    _reset()
    ex = call("workflow.export", {"workflow_id": "WF-133"}, DEV)
    assert ex["ok"], ex
    r = call("workflow.import", {"data": ex["output"]}, DEV)
    assert r["ok"] is False and r["error"]["code"] == "validation_error" and MSG in str(r["error"]), r
    _reset()
