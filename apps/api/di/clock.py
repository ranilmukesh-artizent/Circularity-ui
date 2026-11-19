"""The workspace clock: what "now" is for every action (the journal's time, instruction times, simulated acknowledgements).

Two modes, chosen by the setting DI_CLOCK:

- `pinned` (the default, and the test suite's): now is the demo's as-of time (7 Oct 2026, 09:00 UTC). The demo's answers
  (approval times, "who acted when", escalation clocks) depend on it, so the parity tests keep this mode.
- `sim` (the running api and worker, docker-compose.yml): now follows source-sim's simulated clock, so di and the mocks
  agree on time while the clock is advanced (B13b, "the real loop"). `GET /_sim/clock` gives the simulated time and its
  speed; that anchor is reused for `clock_cache_seconds` (now = anchor + wall time elapsed x speed) so a busy api does
  not read the clock on every call. When source-sim cannot be reached, the last anchor keeps running; with none yet,
  now is the as-of time.

The action handlers still stamp the demo's pinned as-of time on what they write into a case (approval, steps), so the
case documents stay at parity with the demo; the journal, the instructions and their due times use this clock.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from di import golden
from di.config import get_settings

log = logging.getLogger("di.clock")
_anchor: tuple[datetime, float, float] | None = None  # (simulated time, monotonic time when read, speed)


def as_of() -> datetime:
    return datetime.fromisoformat(golden.load("world")["as_of"].replace("Z", "+00:00")).astimezone(UTC)


def mode() -> str:
    return "sim" if get_settings().clock == "sim" else "pinned"


def invalidate() -> None:
    """Forget the cached anchor (after advancing the simulated clock, the next now() reads it again)."""
    global _anchor
    _anchor = None


def _read_sim() -> tuple[datetime, float, float]:
    s = get_settings()
    body = httpx.get(s.source_sim_url.rstrip("/") + "/_sim/clock", timeout=5).json()
    return datetime.fromisoformat(body["now"]).astimezone(UTC), time.monotonic(), float(body.get("speed") or 0)


def _sim_now() -> datetime:
    global _anchor
    if _anchor is None or time.monotonic() - _anchor[1] > get_settings().clock_cache_seconds:
        try:
            _anchor = _read_sim()
        except (httpx.HTTPError, ValueError, KeyError):
            log.warning("source-sim clock unavailable; using the last known time")
            if _anchor is None:
                return as_of()
    sim, at, speed = _anchor
    return sim + timedelta(seconds=(time.monotonic() - at) * speed)


def now() -> datetime:
    return _sim_now() if mode() == "sim" else as_of()
