"""Isotonic regression for calibrated confidence (plan 9, P9-8.2; used by `mapping_suggest`, registry entry I-19).

    fit(xs, ys)       -> [(x, y), ...]   pool-adjacent-violators on raw scores `xs` and 0/1 outcomes `ys`
    lookup(points, x) -> float           linear between the points, clipped to [0, 1]

Owns: the pure fit and lookup, so scikit-learn stays out of the image (D section 3.2).
Never does: read a file, a database or a model; it knows nothing about mappings.
"""

from collections.abc import Sequence
from itertools import pairwise

Point = tuple[float, float]


def fit(xs: Sequence[float], ys: Sequence[int]) -> list[Point]:
    """Non-decreasing calibration points, one per pooled block: (mean score, mean outcome), sorted by score. Equal scores
    are pooled first; a block whose mean outcome is lower than the one before it is merged into that one."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys differ in length")
    blocks: list[list[float]] = []  # [sum of scores, sum of outcomes, count]
    for x, y in sorted(zip(xs, ys, strict=True)):
        if blocks and blocks[-1][3] == x:
            blocks[-1][0] += x
            blocks[-1][1] += y
            blocks[-1][2] += 1
        else:
            blocks.append([x, float(y), 1.0, x])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            top = blocks.pop()
            for i in range(3):
                blocks[-1][i] += top[i]
            blocks[-1][3] = float("nan")  # a merged block is never extended by an equal score (nan equals nothing)
    return [(round(b[0] / b[2], 4), round(b[1] / b[2], 4)) for b in blocks]


def lookup(points: Sequence[Point], x: float) -> float:
    """The calibrated probability at score `x`: linear between neighbouring points, flat outside them, in [0, 1]."""
    if not points:
        return 0.0
    if x <= points[0][0]:
        return min(1.0, max(0.0, points[0][1]))
    for (x0, y0), (x1, y1) in pairwise(points):
        if x <= x1:
            y = y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            return min(1.0, max(0.0, y))
    return min(1.0, max(0.0, points[-1][1]))
