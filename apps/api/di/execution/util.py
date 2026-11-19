"""JavaScript conversions the execution texts depend on, and the date arithmetic of the move (epoch milliseconds)."""

import re
from datetime import UTC, datetime, timedelta

from di.reads.common import DAY_MS

HOUR_MS = 3_600_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NUM = re.compile(r"^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def js_str(x: float | int) -> str:
    """`String(n)` for a number: integers without a decimal point (24, not 24.0), others in their shortest form, which
    is what Python's repr gives as well (24.9, 0.30000000000000004)."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return repr(x) if isinstance(x, float) else str(x)


def parse_float(s: object) -> float:
    """`parseFloat(s)`: the leading number of a string ("55 kW" -> 55), NaN when there is none."""
    m = _NUM.match(str(s)) if s is not None else None
    return float(m[0]) if m else float("nan")


def num_or(x: float, default: float) -> float:
    """`x || default` for a number: NaN and 0 fall back."""
    return default if x != x or x == 0 else x


def dt(t: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=t)


def midnight(t: int) -> int:
    """The demo's exDD: the UTC midnight of a time."""
    return t - t % DAY_MS


def js_day(t: int) -> int:
    """`getUTCDay()`: 0 is Sunday."""
    return (dt(t).weekday() + 1) % 7


def hours(t: int) -> float:
    """`getUTCHours() + getUTCMinutes() / 60` (seconds ignored, as in the demo)."""
    d = dt(t)
    return d.hour + d.minute / 60
