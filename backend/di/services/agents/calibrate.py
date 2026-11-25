"""Isotonic calibration of a stage's confidence (plan 9, P9-2.9; story X-05; registry entries I-7 and I-10).

Owns: `fit` (pool-adjacent-violators over (raw confidence, accepted unchanged 0/1) points) and `apply` (a step lookup with
linear interpolation). Steps are `[(raw, calibrated)]`, raw ascending, calibrated never falling.
Never does: read a table, call a model or decide a hold. The labels come from `di.repositories.stage_outcomes`, the stored
steps from `model_version` (template `<pack>.stage.<stage>`), and `di.services.agents.runtime.calibrated` applies them.
Calibrated confidence is computed, never the language model's own number (R16).
"""

from itertools import pairwise

MIN_POINTS = 20
Step = tuple[float, float]  # (raw confidence, calibrated share accepted unchanged)


def fit(points: list[tuple[float, int]], min_n: int = MIN_POINTS) -> list[Step] | None:
    """Isotonic steps of raw confidence to the share accepted unchanged; None with fewer than `min_n` points."""
    if len(points) < min_n:
        return None
    by_raw: dict[float, list[int]] = {}
    for raw, label in points:
        by_raw.setdefault(raw, []).append(label)
    # blocks: [sum of raw weighted by count, sum of labels, count]; pooled while a block's rate is below the one before it
    blocks: list[list[float]] = []
    for raw in sorted(by_raw):
        ys = by_raw[raw]
        blocks.append([raw * len(ys), float(sum(ys)), float(len(ys))])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            top = blocks.pop()
            blocks[-1] = [a + b for a, b in zip(blocks[-1], top, strict=True)]
    return [(round(b[0] / b[2], 6), round(b[1] / b[2], 6)) for b in blocks]


def apply(steps: list[Step], raw: float) -> float:
    """The calibrated confidence of `raw`: linear between neighbouring steps, the end step beyond them."""
    if not steps:
        return raw
    if raw <= steps[0][0]:
        return steps[0][1]
    for (x0, y0), (x1, y1) in pairwise(steps):
        if raw <= x1:
            return y0 + (y1 - y0) * (raw - x0) / (x1 - x0)
    return steps[-1][1]
