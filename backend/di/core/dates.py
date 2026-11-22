"""JavaScript's date arithmetic in epoch milliseconds, and the demo's pinned as-of time (`AS_OF`, from the golden world).

The demo's `asOfNow()` and `new Date()` mean `AS_OF`. These helpers sit in core so the foundations (di.core.policy's
starting state) can use them; di.repositories.common re-exports them for the read actions.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from di.core import golden

DAY_MS = 86_400_000
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def ms(v: Any) -> int:
    """`new Date(v).getTime()` for an ISO string (date-only strings are UTC, as in JavaScript) or epoch ms."""
    if isinstance(v, int | float):
        return int(v)
    s = str(v)
    if len(s) == 10:
        s += "T00:00:00Z"
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return (d - EPOCH) // timedelta(milliseconds=1)


def dt(t: int) -> datetime:
    """The UTC datetime of epoch milliseconds."""
    return EPOCH + timedelta(milliseconds=t)


def iso(v: Any) -> str:
    """`new Date(v).toISOString()`."""
    t = ms(v)
    return dt(t).strftime("%Y-%m-%dT%H:%M:%S") + f".{t % 1000:03d}Z"


AS_OF = ms(golden.load("world")["as_of"])


def add_days(v: Any, n: float) -> int:
    return ms(v) + int(n * DAY_MS)
