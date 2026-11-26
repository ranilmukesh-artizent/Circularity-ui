"""Seeded synthetic history per pack (plan 9, P9-7.1; story X-06): what the replay fixtures and a trial import.

Owns: a deterministic CSV of past decisions in the columns `history.py` reads, for any pack (its classes, routes and
markets). Never does: read real data or the clock; every value is invented. The same pack, rows and seed give the same text.

    python -m di.services.replay.sample <pack> <rows> [seed]
"""

import csv
import io
import random
import sys
from datetime import UTC, date, datetime, timedelta

from di.services.modeler.pack import load_pack
from di.services.modeler.tables import market_spec

START = date(2025, 10, 1)
DAYS = 360  # decisions fall between START and START + DAYS, all in the past
FACT = "condition"


def make_csv(pack_key: str, rows: int, seed: int = 26111) -> str:
    """The sample history as CSV text; its first line is a comment holding the command that made it."""
    pack = load_pack(pack_key)
    rng = random.Random(f"{pack_key}:{seed}")  # noqa: S311 - invented sample data, not a secret
    spec = market_spec(pack_key)
    markets = list(spec.markets) if spec else ["US"]
    route_ids = [r.id for r in pack.routes]
    weights = [3 if r.classes and r.classes[0] in ("reuse", "sale", "refurbish") else 1 for r in pack.routes]
    out = io.StringIO()
    out.write(f"# python -m di.services.replay.sample {pack_key} {rows}" + (f" {seed}" if seed != 26111 else "") + "\n")
    w = csv.writer(out, lineterminator="\n")
    head = ["item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "cost_logistics", "cost_refurb"]
    w.writerow([*head, "cost_test", "cost_fees", "market", f"fact.{FACT}", f"fact.{FACT}.at"])
    for k in range(rows):
        at = datetime.combine(START + timedelta(days=rng.randrange(DAYS)), datetime.min.time(), UTC) + timedelta(
            hours=rng.randrange(8, 18)
        )
        value = round(rng.uniform(40, 900), 2)
        w.writerow(
            [
                f"{pack.prefix}-H{k + 1:05d}",
                rng.choice(pack.classes).id,
                at.isoformat(),
                "sample decision",
                rng.choices(route_ids, weights)[0],
                value,
                round(rng.uniform(4, 40), 2),
                round(rng.uniform(0, 120), 2),
                round(rng.uniform(0, 25), 2),
                round(value * rng.uniform(0.01, 0.06), 2),
                rng.choice(markets),
                rng.choice(pack.grades.scale),
                (at - timedelta(days=rng.randrange(1, 6))).isoformat(),
            ]
        )
    return out.getvalue()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python -m di.services.replay.sample <pack> <rows> [seed]")
    sys.stdout.write(make_csv(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 26111))
