"""The live cases, in the database (table case_record; docs/backend-steps.md, B11).

A case is one JSON document in the demo's shape. The recommendation is stored as the index of its route, so after a
load `case["recommendation"] is case["routes"][i]`, as in the demo.

**Intake.** The cases are opened from the engine's book (`di.services.engine.book`): each case's facts and route terms with
the engine's evaluation. That is the one place di takes data other than through a connector, because the demo's route
values are random draws that no source system holds (see B10). Opening happens once, when the table is empty;
`reset` reopens every case (and drops the cases opened from data). Cases opened from data (plan 8, Phase 8) come in
through `insert_new` (di.services.cases.intake).
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.engine import book

Case = dict[str, Any]
_ready = False


def _doc(c: Case) -> dict:
    d = {k: v for k, v in c.items() if k != "recommendation"}
    rec = c.get("recommendation")
    d["rec_index"] = next((i for i, r in enumerate(c["routes"]) if r is rec), None) if rec is not None else None
    return d


def _case(d: dict) -> Case:
    c = {k: v for k, v in d.items() if k != "rec_index"}
    i = d.get("rec_index")
    c["recommendation"] = c["routes"][i] if i is not None else None
    return c


def _insert(s: Session, c: Case, reason: str = "Case opened", actor: str = "system") -> None:
    p = {"i": c["id"], "o": c["owner"], "l": c["location"], "st": c["stage"], "d": json.dumps(_doc(c)), "r": reason, "a": actor}
    s.execute(text("INSERT INTO case_record (id, owner, location, stage, data) VALUES (:i, :o, :l, :st, CAST(:d AS jsonb))"), p)
    s.execute(text("INSERT INTO case_stage_log (case_id, to_stage, reason, actor) VALUES (:i, :st, :r, :a)"), p)


def insert_new(s: Session, c: Case, reason: str = "Case opened", actor: str = "system") -> None:
    """Add a case opened from data (di.services.cases.intake, plan 8 MVP-8.1) beside the book's, with its stage log
    row. In the caller's transaction; the book's cases are opened first, so a reset never mixes the two."""
    ensure(s)
    _insert(s, c, reason, actor)


def _open_all(own: Session) -> int:
    n = 0
    for cid in book.ids():
        case = book.get(cid)
        if case is None:  # not reached: book.ids() lists only the cases book.get() has
            raise LookupError(f"case {cid} is listed but has no record")
        _insert(own, case)
        n += 1
    return n


def ensure(_: Session | None = None) -> int:
    """Open every case if none is open yet; returns how many were opened. Runs in its own transaction, so a
    caller's transaction is never committed by it."""
    global _ready
    if _ready:
        return 0
    from di.core.db import SessionLocal

    n = 0
    with SessionLocal() as own:
        own.execute(text("SELECT pg_advisory_xact_lock(1048)"))  # api and worker may start together
        if not own.execute(text("SELECT EXISTS (SELECT 1 FROM case_record)")).scalar():
            n = _open_all(own)
        own.commit()
    _ready = True
    return n


def _heal() -> bool:
    """Called when a read finds nothing: the table may have been emptied by another process (a reset or a restore),
    which this process's `_ready` flag cannot know. Re-checks the database and reopens the book if it is empty;
    True when it did. Costs one lock and one EXISTS, only on a miss."""
    global _ready
    _ready = False
    return ensure() > 0


def reset() -> int:
    """Reopen every case from the book: what a demo reset does. Delete and reopen are ONE transaction under the
    intake lock, so a reader in another process (the api, while a script resets) never sees an empty table."""
    global _ready
    from di.core.db import SessionLocal

    with SessionLocal() as own:
        own.execute(text("SELECT pg_advisory_xact_lock(1048)"))
        own.execute(text("DELETE FROM case_record"))
        n = _open_all(own)
        own.commit()
    _ready = True
    return n


def get(s: Session, case_id: str, for_update: bool = False) -> Case | None:
    ensure(s)
    row = s.execute(
        text("SELECT data FROM case_record WHERE id = :i" + (" FOR UPDATE" if for_update else "")),  # noqa: S608 - only the fixed FOR UPDATE suffix is appended; values are bound
        {"i": case_id},
    ).scalar()
    if row is None and _heal():  # the table was emptied behind this process's back: reopened, read again
        row = s.execute(
            text("SELECT data FROM case_record WHERE id = :i" + (" FOR UPDATE" if for_update else "")),  # noqa: S608 - fixed suffix
            {"i": case_id},
        ).scalar()
    return _case(row) if row is not None else None


def all_cases(s: Session) -> list[Case]:
    ensure(s)
    rows = list(s.execute(text("SELECT data FROM case_record ORDER BY id")).scalars())
    if not rows and _heal():
        rows = list(s.execute(text("SELECT data FROM case_record ORDER BY id")).scalars())
    return [_case(d) for d in rows]


def save(s: Session, c: Case) -> None:
    """Write a changed case back (the caller holds it FOR UPDATE and commits)."""
    s.execute(
        text(
            "UPDATE case_record SET owner = :o, location = :l, stage = :st, data = CAST(:d AS jsonb), "
            "version = version + 1, updated_at = now() WHERE id = :i"
        ),
        {"i": c["id"], "o": c["owner"], "l": c["location"], "st": c["stage"], "d": json.dumps(_doc(c))},
    )


def scope(s: Session, case_id: str) -> tuple[str, str] | None:
    """(owner tenant, location) for the tenant boundary and warehouse lock."""
    ensure(s)
    row = s.execute(text("SELECT owner, location FROM case_record WHERE id = :i"), {"i": case_id}).first()
    if row is None and _heal():
        row = s.execute(text("SELECT owner, location FROM case_record WHERE id = :i"), {"i": case_id}).first()
    return (row[0], row[1]) if row else None
