"""P9-13.8: model quality, drift and cadence across packs (enabler for story 01 section 3; E section 11.5).

`di.services.engine.drift` is pure (PSI, error ratio, status). `model.fit` stamps the registry fields and queues the weekly
`model.drift` job; `model.checkDrift` measures a model against the outcomes closed since it was trained, stores the status
and opens one work item (I-20) on an alert. The explanation of a drift runs on the model first (R16) with the rule text as
its fallback; every number in it is computed.
"""

import importlib.util
import json
import random
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents import drift_explainer, runtime
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases import store
from di.services.engine import drift
from tests.helpers import call

PACK = "industrial"


# ---------------------------------------------------------------- pure
def test_drift_psi_values():
    rnd = random.Random(7)  # noqa: S311 - a test sample
    base = [rnd.gauss(100, 10) for _ in range(500)]
    assert drift.psi(base, list(base)) == 0.0
    shifted = [x + 20 for x in base]  # a mean shift of two standard deviations
    assert drift.psi(base, shifted) > 0.25


def test_drift_status_rules():
    assert drift.status(0.05, 1.0) == "ok"
    assert drift.status(0.15, 1.0) == "watch"
    assert drift.status(0.05, 1.6) == "alert"
    assert drift.status(0.25, 1.5) == "watch"  # the alert bounds are exclusive
    assert drift.error_drift(2.0, 3.0) == pytest.approx(1.5)


def test_next_due_monthly_or_fifty_outcomes():
    from datetime import UTC, datetime

    t = datetime(2026, 10, 7, tzinfo=UTC)
    assert drift.next_due(t, 3, t + timedelta(days=2)) == t + timedelta(days=30)
    assert drift.next_due(t, 50, t + timedelta(days=2)) == t + timedelta(days=2)


# ---------------------------------------------------------------- database
def _outcome(case_id: str, predicted: float, actual: float, at: str) -> None:
    doc = {
        "id": case_id, "template": PACK, "cls": "x", "rec_index": 0,
        "routes": [{"id": "redeploy", "net": predicted}], "outcome": {"net": actual, "at": at},
    }  # fmt: skip
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO case_record (id, owner, location, stage, data) "
                "VALUES (:i, 'Customer A', 'Site 1', 'closed', CAST(:d AS jsonb))"
            ),
            {"i": case_id, "d": json.dumps(doc)},
        )
        s.commit()


@pytest.fixture
def world():
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    with SessionLocal() as s:
        store.ensure(s)
        s.execute(text("DELETE FROM model_version"))
        s.commit()
    for k in range(5):
        _outcome(f"DRIFT-{k}", 100.0, 80.0, f"2026-10-0{k + 1}T09:00Z")
    yield
    runtime.set_loop(None)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM case_record WHERE id LIKE 'DRIFT-%'"))
        s.execute(text("DELETE FROM work_item WHERE type = 'model_drift'"))
        s.execute(text("DELETE FROM job WHERE kind = 'model.drift'"))
        s.execute(text("DELETE FROM agent_run WHERE playbook = 'drift_explain'"))
        s.execute(text("DELETE FROM model_version"))
        s.commit()


def _fit() -> dict[str, Any]:
    out = call("model.fit", {"template": PACK}, "planner-a")
    assert out["ok"], out
    return out["output"]


def _row(mid: str) -> Any:
    with SessionLocal() as s:
        return s.execute(
            text(
                "SELECT pack, trained_at, data_window, quality, cadence, next_due, drift_status, drift "
                "FROM model_version WHERE id = :i"
            ),
            {"i": mid},
        ).one()


def test_model_fit_stamps_the_registry_fields(world):
    m = _fit()
    pack, trained_at, window, quality, cadence, next_due, status, _ = _row(m["id"])
    assert pack == PACK and trained_at is not None and next_due - trained_at == timedelta(days=30)
    assert window["n"] == 5 and quality["mae"] == pytest.approx(0.0, abs=1e-6) and "50" in cadence and status is None


def test_model_drift_job_scheduled_weekly(world):
    m = _fit()
    with SessionLocal() as s:
        run_after, payload = s.execute(text("SELECT run_after, payload FROM job WHERE kind = 'model.drift'")).one()
        now = s.execute(text("SELECT now()")).scalar_one()
    assert payload == {"model_id": m["id"]}
    assert abs((run_after - now) - timedelta(days=7)) < timedelta(minutes=5)


def test_model_fields_backfilled(world):
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0059_model_registry_fields.py"
    spec = importlib.util.spec_from_file_location("m0059", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO model_version (id, template, factors, status, created_by, metrics) "
                "VALUES ('MV-900', 'device', '[]', 'candidate', 'x', '{}')"
            )
        )
        s.execute(text("UPDATE model_version SET pack = NULL"))
        s.execute(text(mod.BACKFILL))
        assert s.execute(text("SELECT pack FROM model_version WHERE id = 'MV-900'")).scalar_one() == "device"
        s.commit()


def _promote(mid: str) -> None:
    assert call("model.propose", {"id": mid}, "planner-a")["ok"]
    assert call("model.promote", {"id": mid}, "approver")["ok"]


def _shift() -> None:
    with SessionLocal() as s:
        s.execute(text("UPDATE model_version SET trained_at = '2026-10-06T00:00Z'"))
        s.commit()
    for k in range(6):  # outcomes closed after the training, far from what the model predicts
        _outcome(f"DRIFT-new-{k}", 100.0, 40.0, f"2026-10-1{k}T09:00Z")


def test_drift_alert_opens_work_item(world):
    m = _fit()
    _promote(m["id"])
    _shift()
    out = call("model.checkDrift", {"id": m["id"]}, "planner-a")
    assert out["ok"], out
    got = out["output"]["checked"][0]
    assert got["status"] == "alert" and got["ratio"] > 1.5 and got["by_model"] is False
    assert _row(m["id"])[6] == "alert"
    again = call("model.checkDrift", {"id": m["id"]}, "planner-a")  # a second check adds no second item
    assert again["ok"]
    with SessionLocal() as s:
        titles = s.execute(text("SELECT title FROM work_item WHERE type = 'model_drift' AND status = 'open'")).scalars().all()
    assert len(titles) == 1 and titles[0].startswith(f"Model {m['id']} drifted: ")


def test_drift_check_is_for_a_person_who_manages_flows(world):
    m = _fit()
    assert not call("model.checkDrift", {"id": m["id"]}, "exec")["ok"]
    assert not call("model.checkDrift", {"id": "MV-404"}, "planner-a")["ok"]


# ---------------------------------------------------------------- model first (R16)
FACTS = {"id": "MV-001", "psi": 0.31, "ratio": 1.8, "status": "alert", "rule": "PSI 0.31 is over 0.25"}


def _scripted(*notes: str, seen: list[int] | None = None) -> PydanticAILoop:
    todo = list(notes)

    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(1)
        t = todo.pop(0) if len(todo) > 1 else todo[0]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"text": t})])

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _ctx() -> CallContext:
    with SessionLocal() as s:
        return CallContext(actor=SYSTEM, session=s)


def test_drift_explain_model_text_accepted(world):
    runtime.set_loop(_scripted("Inputs moved: PSI 0.31 and the error ratio 1.8 both crossed their limits."))
    assert drift_explainer.explain(_ctx(), FACTS) == "Inputs moved: PSI 0.31 and the error ratio 1.8 both crossed their limits."


def test_drift_explain_invented_number_refused_then_fallback(world):
    seen: list[int] = []
    runtime.set_loop(_scripted("The error is up 77 percent.", seen=seen))
    assert drift_explainer.explain(_ctx(), FACTS) is None and len(seen) == 2  # one repair round, then the rule text stands


def test_drift_explain_no_model(world):
    assert drift_explainer.explain(_ctx(), FACTS) is None
