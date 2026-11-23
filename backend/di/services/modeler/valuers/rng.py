"""The PO prototype's seeded random numbers (docs/reference/po-modeler/recover-app-prototype.html, line 791).

`rng(seed)` there is mulberry32 on 32-bit integers (`|0`, `>>>`, `Math.imul`). This port keeps every value as an
unsigned 32-bit integer, which gives the same bits: XOR, OR and logical shifts act on the bits alone, and `Math.imul`
and `t + x` keep only the low 32 bits of the result.
"""

from collections.abc import Callable

_MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & _MASK


def mulberry32(seed: int) -> Callable[[], float]:
    """A generator of floats in [0, 1), draw for draw the prototype's `rng(seed)`."""
    state = seed & _MASK

    def draw() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _MASK
        t = _imul(state ^ (state >> 15), 1 | state)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK) ^ t
        return (t ^ (t >> 14)) / 4294967296

    return draw
