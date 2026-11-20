"""JavaScript's arithmetic where it differs from Python's, so the engine matches the demo to the dollar.

- Rounding: Python's round() rounds halves to even (round(2.5) == 2); JavaScript's Math.round rounds them up
  (Math.round(2.5) == 3, Math.round(-2.5) == -2).
- Summing: Python 3.12's sum() of floats is compensated (more exact); the demo adds left to right
  (`a.reduce((s, x) => s + x, 0)`), and a scenario net that lands near .5 can round the other way.
"""

import math
from collections.abc import Iterable


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def js_sum(xs: Iterable[float]) -> float:
    total: float = 0
    for x in xs:
        total = total + x
    return total
