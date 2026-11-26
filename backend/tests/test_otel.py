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
