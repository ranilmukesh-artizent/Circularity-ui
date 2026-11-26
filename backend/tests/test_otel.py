"""Plan 5, Task 1: OpenTelemetry setup, off by default (di/telemetry.py).

The exporter is the in-memory one; nothing here talks to a collector. The global tracer provider can be set once per
process, so the tests share it and clear the exporter between them.
"""

import logging
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from di.routes.screens import nav as nav_screen
from tests.helpers import h

SECRET = "tok-1234567890-must-not-leak"  # a fake value the test plants in a query string


def test_off_by_default_imports_no_sdk_and_exports_nothing():
    """No endpoint and no exporter: setup_telemetry returns at once, the SDK is not even imported."""
    code = (
        "import os, sys\n"
        "os.environ.pop('OTEL_EXPORTER_OTLP_ENDPOINT', None)\n"
        "os.environ.pop('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', None)\n"
        "from fastapi import FastAPI\n"
        "from di import telemetry\n"
        "app = FastAPI()\n"
        "telemetry.setup_telemetry('di-api', app)\n"
        "assert not telemetry.enabled()\n"
        "assert not any(m.startswith('opentelemetry.sdk') for m in sys.modules), 'sdk imported'\n"
        "import logging\n"
        "r = logging.getLogger('x').makeRecord('x', 20, 'f', 1, 'm', (), None)\n"
        "assert not hasattr(r, 'otelTraceID')\n"
        "print('OFF-OK')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False)  # noqa: S603
    assert "OFF-OK" in out.stdout, out.stdout + out.stderr


@pytest.fixture(scope="module")
def traced():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from di import telemetry

    exporter = InMemorySpanExporter()
    app = FastAPI()
    app.include_router(nav_screen.router)
    telemetry.setup_telemetry("di-api", app, exporter=exporter)
    assert telemetry.enabled()
    with TestClient(app) as c:
        yield c, exporter


def test_nav_request_yields_server_span_with_sql_children(traced):
    c, exporter = traced
    exporter.clear()
    r = c.get("/api/screens/nav", headers=h("planner-a"))
    assert r.status_code == 200
    spans = exporter.get_finished_spans()
    server = [s for s in spans if s.kind.name == "SERVER" and "/api/screens/nav" in s.name + str(dict(s.attributes))]
    assert server, [s.name for s in spans]
    root = server[0]
    assert root.resource.attributes["service.name"] == "di-api"
    sql = [s for s in spans if s.parent is not None and s.context.trace_id == root.context.trace_id and s is not root]
    assert any(s.kind.name == "CLIENT" for s in sql), [s.name for s in spans]


def test_log_records_carry_the_trace_id(traced):
    from di import telemetry

    with telemetry.tracer.start_as_current_span("t") as span:
        rec = logging.getLogger("di.test").makeRecord("di.test", 20, __file__, 1, "msg", (), None)
        expected = format(span.get_span_context().trace_id, "032x")
    assert rec.otelTraceID == expected  # type: ignore[attr-defined]


def test_no_secret_reaches_a_span_attribute(traced):
    c, exporter = traced
    exporter.clear()
    c.get(f"/api/screens/nav?access_token={SECRET}&ticket={SECRET}", headers=h("planner-a"))
    for s in exporter.get_finished_spans():
        for k, v in dict(s.attributes).items():
            assert SECRET not in str(v), (s.name, k)


# ---------------------------------------------------------------- plan 5 task 2: worker and job traces
@pytest.fixture(scope="module")
def traced_tasks():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from di import telemetry
    from di.routes import tasks as tasks_routes

    exporter = InMemorySpanExporter()
    app = FastAPI()
    app.include_router(tasks_routes.router)
    telemetry.setup_telemetry("di-api", app, exporter=exporter)
    with TestClient(app) as c:
        yield c, exporter


def _run_until(seen: list) -> None:
    from di import worker

    for _ in range(50):  # other queued jobs of the shared database may come first
        if seen or not worker.run_once():
            return


def test_a_job_queued_by_a_request_carries_its_traceparent_and_the_worker_span_links_to_it(traced_tasks):
    c, exporter = traced_tasks
    exporter.clear()
    from di import worker

    kind = "test.otel.job"
    seen: list = []
    worker.HANDLERS[kind] = seen.append  # a task may only name a kind a worker runs
    r = c.post("/api/v1/tasks", json={"kind": kind, "payload": {"n": 1}}, headers=h("developer"))
    assert r.status_code == 201, r.text
    carrier = r.json()["payload"]["_trace"]
    server = next(s for s in exporter.get_finished_spans() if s.kind.name == "SERVER")
    tid = format(server.context.trace_id, "032x")
    assert carrier["traceparent"].startswith(f"00-{tid}-")
    # the worker's handler sees the payload it always saw: the trace carrier is not part of it
    exporter.clear()
    _run_until(seen)
    assert seen == [{"n": 1}]
    job = [s for s in exporter.get_finished_spans() if s.name == f"job {kind}"]
    assert len(job) == 1
    span = job[0]
    assert span.kind.name == "CONSUMER"
    assert span.attributes["di.job.kind"] == kind
    links = [(format(k.context.trace_id, "032x"), format(k.context.span_id, "016x")) for k in span.links]
    assert links[0][0] == tid and len(links) == 1


def test_a_failing_job_span_has_error_status(traced_tasks):
    from di import worker

    c, exporter = traced_tasks
    kind = "test.otel.boom"

    def boom(_payload):
        raise RuntimeError("boom")

    worker.HANDLERS[kind] = boom
    r = c.post("/api/v1/tasks", json={"kind": kind}, headers=h("developer"))
    assert r.status_code == 201, r.text
    exporter.clear()
    for _ in range(50):
        if any(s.name == f"job {kind}" for s in exporter.get_finished_spans()) or not worker.run_once():
            break
    span = next(s for s in exporter.get_finished_spans() if s.name == f"job {kind}")
    assert span.status.status_code.name == "ERROR"


def test_nothing_is_added_to_a_job_payload_when_tracing_is_off(monkeypatch):
    from di import telemetry
    from di.core import jobs
    from di.core.db import SessionLocal

    monkeypatch.setattr(telemetry, "_provider", None)
    with SessionLocal() as s:
        job = jobs.enqueue(s, "ping", {"n": 1})
        assert job.payload == {"n": 1}
        s.rollback()


def test_a_job_queued_outside_any_span_has_no_trace_carrier(traced_tasks):
    from di.core import jobs
    from di.core.db import SessionLocal

    with SessionLocal() as s:
        job = jobs.enqueue(s, "ping", {"n": 2})
        assert job.payload == {"n": 2}
        s.rollback()
