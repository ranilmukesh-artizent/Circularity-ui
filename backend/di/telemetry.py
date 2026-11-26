"""OpenTelemetry setup for di-api and di-worker (plan 5, Task 1).

Off unless `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) is set: then `setup_telemetry` returns
at once, imports nothing of the SDK, patches nothing and exports nothing. When on, it sets one tracer provider (resource
`service.name`), a batching OTLP/HTTP exporter (it drops spans when the collector is down; it never blocks a request) and
instruments FastAPI (when an app is given), SQLAlchemy, psycopg, httpx and logging (`otelTraceID` / `otelSpanID` on every
log record; the log format itself is unchanged). Logs go out over OTLP only with `DI_OTEL_LOGS=true`.

No secret reaches a span: `_scrubbed` (an exporter wrapper) masks `access_token=`, `ticket=`, bearer tokens and `gsk_`
keys in every string attribute before export (urls and targets carry query strings). Bodies, headers and arguments are
not captured.
Tests pass `exporter=` (an in-memory one) to switch it on without an endpoint.
"""

import logging
import os
import re
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

if TYPE_CHECKING:
    from fastapi import FastAPI

tracer = trace.get_tracer("di")

log = logging.getLogger("di.telemetry")
_ENDPOINT_ENVS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
_SECRET = re.compile(
    r"(\b(?:access_token|ticket|token|api_key|signature)=)[^&\s\"']+|(\bBearer\s+)[\w.~+/=-]+|\bgsk_[A-Za-z0-9]{8,}",
    re.IGNORECASE,
)
_provider: Any = None


def enabled() -> bool:
    """True once setup_telemetry switched tracing on in this process."""
    return _provider is not None


def _mask(match: re.Match[str]) -> str:
    return (match.group(1) or match.group(2) or "") + "[redacted]"


def scrub(value: str) -> str:
    return _SECRET.sub(_mask, value)


def _scrubbed(exporter: Any) -> Any:
    """Wraps a span exporter: every string attribute is masked on a copy of the span before the exporter sees it (the url
    and target attributes are set during the request, and an ended span's attributes are immutable)."""
    import copy

    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class _ScrubExporter(SpanExporter):
        def export(self, spans: Any) -> Any:
            clean = []
            for span in spans:
                attrs = dict(span.attributes or {})
                if any(isinstance(v, str) and _SECRET.search(v) for v in attrs.values()):
                    span = copy.copy(span)
                    span._attributes = {k: scrub(v) if isinstance(v, str) else v for k, v in attrs.items()}
                clean.append(span)
            result: SpanExportResult = exporter.export(clean)
            return result

        def shutdown(self) -> None:
            exporter.shutdown()

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return bool(exporter.force_flush(timeout_millis))

    return _ScrubExporter()


def setup_telemetry(service_name: str, app: "FastAPI | None" = None, *, exporter: Any = None) -> None:
    """Switch tracing on for this process (once), or do nothing. `exporter` is for tests."""
    global _provider
    if exporter is None and not any(os.environ.get(k) for k in _ENDPOINT_ENVS):
        return
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        trace.set_tracer_provider(_provider)
        _instrument_libraries()
        _start_log_export(service_name)
    if exporter is not None:
        _provider.add_span_processor(SimpleSpanProcessor(_scrubbed(exporter)))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        _provider.add_span_processor(BatchSpanProcessor(_scrubbed(OTLPSpanExporter())))
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, tracer_provider=_provider)


def _instrument_libraries() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from di.core.db import engine

    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=_provider)
    PsycopgInstrumentor().instrument(tracer_provider=_provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=_provider)
    # otelTraceID/otelSpanID/otelServiceName on every record; no format change, and no OTLP log handler of its own
    LoggingInstrumentor().instrument(set_logging_format=False, inject_trace_context=True, enable_log_auto_instrumentation=False)


def _start_log_export(service_name: str) -> None:
    """OTLP log export, only behind DI_OTEL_LOGS=true and a real endpoint (the Python Logs SDK is Development status)."""
    from di.core.config import get_settings

    if not get_settings().otel_logs or not any(os.environ.get(k) for k in _ENDPOINT_ENVS):
        return
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    from di.core.logs import RedactSecrets

    provider = LoggerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    handler.addFilter(RedactSecrets())
    logging.getLogger().addHandler(handler)
