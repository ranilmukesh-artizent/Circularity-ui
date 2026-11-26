"""Replay batches and items as stored in `replay_batch` and `replay_item` (migration 0049; plan 9 P9-7.1, registry I-16).

Owns the reads and the writes of an imported history batch. Never checks a row (di.services.replay.history does) and never
decides who may see a batch (the actions apply the tenant boundary).
"""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

HELD_SHOWN = 50


@dataclass
class Batch:
    """I-16: a batch's counts, its decision period and why rows were held."""

    id: int
    pack: str
    org_unit_id: str
    rows: int
    held: int
    period: tuple[date, date] | None
    held_reasons: dict[str, int] = field(default_factory=dict)

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pack": self.pack,
            "org_unit_id": self.org_unit_id,
            "rows": self.rows,
            "held": self.held,
            "period": [self.period[0].isoformat(), self.period[1].isoformat()] if self.period else None,
            "held_reasons": self.held_reasons,
        }


def get(s: Session, batch_id: int, for_update: bool = False) -> dict[str, Any] | None:
    sql = "SELECT id, pack, org_unit_id, rows, held, period_from, period_to FROM replay_batch WHERE id = :i"
    r = s.execute(text(sql + (" FOR UPDATE" if for_update else "")), {"i": batch_id}).mappings().first()
    return dict(r) if r else None


def item_ids(s: Session, batch_id: int) -> set[str]:
    return set(s.execute(text("SELECT item_id FROM replay_item WHERE batch_id = :b"), {"b": batch_id}).scalars())


def create(s: Session, pack: str, org: str, by: str) -> int:
    return int(
        s.execute(
            text("INSERT INTO replay_batch (pack, org_unit_id, rows, held, created_by) VALUES (:p, :o, 0, 0, :by) RETURNING id"),
            {"p": pack, "o": org, "by": by},
        ).scalar_one()
    )


def last_n(s: Session, batch_id: int) -> int:
    """The number of the batch's last item (0 for a new batch): an append numbers its rows after it."""
    return int(s.execute(text("SELECT COALESCE(MAX(n), 0) FROM replay_item WHERE batch_id = :b"), {"b": batch_id}).scalar_one())


def _facts(facts: dict[str, Any]) -> dict[str, Any]:
    return {k: {"value": f["value"], "at": f["at"].isoformat() if f["at"] else None} for k, f in facts.items()}


def add_items(s: Session, batch_id: int, items: list[dict[str, Any]], held: bool, start: int = 0) -> None:
    """Store items under `start` + their row number in the file, so a held row is found by the row it came from."""
    if not items:
        return
    rows = [
        {
            "b": batch_id, "n": start + it["n"], "i": it["item_id"], "d": it["decided_at"], "c": it["cls"], "m": it["market"],
            "r": it["actual_route"], "v": it["realised_value"], "co": json.dumps(it["costs"]),
            "f": json.dumps(_facts(it["facts"])),
            "s": "held" if held else "ok", "h": it.get("held_reason"),
        }
        for it in items
    ]  # fmt: skip
    s.execute(
        text(
            "INSERT INTO replay_item (batch_id, n, item_id, decided_at, cls, market, actual_route, realised_value, costs, "
            "facts, status, held_reason) VALUES (:b, :n, :i, :d, :c, :m, :r, :v, CAST(:co AS jsonb), CAST(:f AS jsonb), "
            ":s, :h)"
        ),
        rows,
    )


def refresh(s: Session, batch_id: int) -> Batch:
    """Recount the batch from its items and answer it."""
    s.execute(
        text(
            "UPDATE replay_batch b SET rows = c.n, held = c.h, period_from = c.lo, period_to = c.hi FROM ("
            "SELECT count(*) AS n, count(*) FILTER (WHERE status = 'held') AS h, "
            "CAST(min(decided_at) FILTER (WHERE status = 'ok') AS date) AS lo, "
            "CAST(max(decided_at) FILTER (WHERE status = 'ok') AS date) AS hi FROM replay_item WHERE batch_id = :b"
            ") c WHERE b.id = :b"
        ),
        {"b": batch_id},
    )
    return batches(s, [batch_id])[0]


def batches(s: Session, ids: list[int]) -> list[Batch]:
    rows = s.execute(
        text("SELECT id, pack, org_unit_id, rows, held, period_from, period_to FROM replay_batch WHERE id = ANY(:i) ORDER BY id"),
        {"i": ids},
    ).all()
    return [_batch(s, r) for r in rows]


def _batch(s: Session, r: Any) -> Batch:
    reasons = s.execute(
        text(
            "SELECT held_reason, count(*) FROM replay_item WHERE batch_id = :b AND status = 'held' "
            "GROUP BY held_reason ORDER BY count(*) DESC, held_reason"
        ),
        {"b": r.id},
    ).all()
    period = (r.period_from, r.period_to) if r.period_from and r.period_to else None
    return Batch(r.id, r.pack, r.org_unit_id, r.rows, r.held, period, {k: int(v) for k, v in reasons})


def for_org(s: Session, pack: str, org: str) -> list[Batch]:
    ids = s.execute(
        text("SELECT id FROM replay_batch WHERE pack = :p AND org_unit_id = :o ORDER BY id DESC"), {"p": pack, "o": org}
    ).scalars()
    return sorted(batches(s, list(ids)), key=lambda b: -b.id)  # newest first


def held_items(s: Session, batch_id: int) -> list[dict[str, Any]]:
    """The first HELD_SHOWN held rows of a batch."""
    rows = s.execute(
        text("SELECT n, item_id, held_reason FROM replay_item WHERE batch_id = :b AND status = 'held' ORDER BY n LIMIT :l"),
        {"b": batch_id, "l": HELD_SHOWN},
    ).mappings()
    return [dict(r) for r in rows]
