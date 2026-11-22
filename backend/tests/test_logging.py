"""D6: one logging setup for api and worker (di/core/logs.py), secrets masked in log lines, and token calls whose response
bodies never reach the fetch log (di/connectors/http.py)."""

import logging

import httpx

from di.connectors.http import SourceClient
from di.core.logs import FORMAT, UVICORN, RedactSecrets, configure_logging


def _access_record(path: str) -> logging.LogRecord:
    """A record as uvicorn's access logger makes it (message template plus args)."""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', ("10.0.0.1:5000", "GET", path, "1.1", 200), None
    )


def test_access_lines_mask_tokens_and_tickets():
    f = RedactSecrets()
    for path, want in [
        ("/api/stream?access_token=eyJhbGciOi.abc.def", "/api/stream?access_token=[redacted]"),
        ("/api/stream?ticket=tk_123&since=4", "/api/stream?ticket=[redacted]&since=4"),
        ("/api/stream?since=4&ticket=tk_123", "/api/stream?since=4&ticket=[redacted]"),
        ("/api/stream?ACCESS_TOKEN=x&ticket=y", "/api/stream?ACCESS_TOKEN=[redacted]&ticket=[redacted]"),
    ]:
        rec = _access_record(path)
        assert f.filter(rec) is True
        assert rec.getMessage() == f'10.0.0.1:5000 - "GET {want} HTTP/1.1" 200'


def test_other_lines_are_left_alone():
    rec = _access_record("/api/screens/home?tenant=All")
    RedactSecrets().filter(rec)
    assert rec.args and rec.getMessage().endswith('"GET /api/screens/home?tenant=All HTTP/1.1" 200')


def test_configure_logging_is_one_setup_for_di_and_uvicorn(monkeypatch, capsys):
    monkeypatch.setenv("DI_LOG_LEVEL", "warning")
    root = logging.getLogger()
    level = root.level
    try:
        configure_logging()
        configure_logging()  # idempotent: still one di handler
        mine = [h for h in root.handlers if type(h).__name__ == "_Handler"]
        assert len(mine) == 1 and mine[0].formatter._fmt == FORMAT
        assert root.level == logging.WARNING
        for name in UVICORN:
            lg = logging.getLogger(name)
            assert lg.propagate and not lg.handlers and any(isinstance(f, RedactSecrets) for f in lg.filters)
        logging.getLogger("uvicorn.access").warning('%s - "%s %s"', "c", "GET", "/api/stream?ticket=secret-1")
        err = capsys.readouterr().err
        assert "ticket=[redacted]" in err and "secret-1" not in err and " WARNING uvicorn.access " in err
    finally:
        monkeypatch.delenv("DI_LOG_LEVEL")
        configure_logging()
        root.setLevel(level)


class _Log:
    """Stands in for the session: keeps the fetch-log rows `SourceClient` writes."""

    def __init__(self):
        self.rows: list[dict] = []

    def execute(self, _sql, params):
        self.rows.append(params)


def _client(status: int, body: str) -> tuple[SourceClient, _Log]:
    log = _Log()
    c = SourceClient("test", "http://source.invalid", auth=None, session=log)
    c.http = httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(status, text=body)))
    return c, log


def test_token_call_bodies_are_not_logged():
    c, log = _client(401, '{"error":"invalid_client","access_token":"leaked-secret"}')
    c.raw("POST", "/oauth/token", data={"client_secret": "client-secret-xyz"}, log_records=False)
    assert len(log.rows) == 1 and log.rows[0]["st"] == 401 and log.rows[0]["e"] == "HTTP 401"
    assert "leaked-secret" not in repr(log.rows) and "client-secret-xyz" not in repr(log.rows)


def test_other_failed_calls_keep_the_start_of_the_body():
    c, log = _client(500, "upstream exploded")
    c.raw("GET", "/odata/things")
    assert log.rows[0]["e"] == "upstream exploded" and log.rows[0]["u"] == "http://source.invalid/odata/things"
