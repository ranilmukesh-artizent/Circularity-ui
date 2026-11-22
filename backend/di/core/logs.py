"""One logging setup for di-api and di-worker.

`configure_logging()` is called by di/main.py (the api, after uvicorn has set up its own loggers) and by
di/worker.py. Level: the DI_LOG_LEVEL environment variable (default INFO). One format for every line; uvicorn's
loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) lose their own handlers and go through the same one.

Credentials never reach a log line: `RedactSecrets` replaces the value of `access_token=` and `ticket=` in any message,
which is where a query string carries them (the live stream's sign-in, uvicorn's access log of that URL).
"""

import logging
import os
import re
import sys

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")
_SECRET = re.compile(r"\b(access_token|ticket)=[^&\s\"']+", re.IGNORECASE)


class RedactSecrets(logging.Filter):
    """Masks `access_token=…` and `ticket=…` values. Never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = _SECRET.sub(r"\1=[redacted]", msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True


class _Handler(logging.StreamHandler):
    """di's handler on the root logger; marked so that a second configure_logging() replaces it. Writes to the
    current sys.stderr (as logging's last-resort handler does), so a test runner swapping stderr does not break it."""

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


def configure_logging(level: str | None = None) -> None:
    """Idempotent. Leaves other handlers on the root logger alone (pytest's capture, for one)."""
    value = logging.getLevelName((level or os.environ.get("DI_LOG_LEVEL") or "INFO").upper())
    root = logging.getLogger()
    for h in [h for h in root.handlers if isinstance(h, _Handler)]:
        root.removeHandler(h)
    handler = _Handler()
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(RedactSecrets())
    root.addHandler(handler)
    root.setLevel(value if isinstance(value, int) else logging.INFO)
    for logger_name in UVICORN:
        lg = logging.getLogger(logger_name)
        lg.handlers.clear()
        lg.propagate = True
        lg.disabled = False  # a fileConfig() elsewhere (alembic's env.py) disables loggers that existed before it
        lg.setLevel(logging.NOTSET)
        # on the logger too, so the record itself is masked before any handler (another one included) sees it
        if not any(isinstance(f, RedactSecrets) for f in lg.filters):
            lg.addFilter(RedactSecrets())
