"""Writer 32: the case screen and /api/checks must not 404/500 when the case table is emptied under a running api
(a reset in another process, scripts/reset_starting.py): `store.ensure` used to trust its in-process flag, and
`store.reset` committed the DELETE before it reinserted, so a reader saw an empty table in between."""

import threading

from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import store
from tests import starting
from tests.helpers import client, h


def _count() -> int:
    with SessionLocal() as s:
        return s.execute(text("SELECT count(*) FROM case_record")).scalar() or 0


def test_case_screen_survives_a_table_emptied_by_another_process():
    starting.reset()
    assert store._ready  # this process believes the cases are open
    with SessionLocal() as s:  # another process wipes the table without touching our flag
        s.execute(text("DELETE FROM case_record"))
        s.commit()
    r = client.get("/api/screens/case/RT-1048", headers=h("planner.a"))
    assert r.status_code == 200, r.text
    assert _count() >= 128


def test_checks_survive_a_table_emptied_by_another_process():
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM case_record"))
        s.commit()
    r = client.get("/api/checks", headers=h("admin"))
    assert r.status_code == 200, r.text


def test_reset_never_exposes_an_empty_table_to_a_reader():
    starting.reset()
    seen: list[int] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            seen.append(_count())

    t = threading.Thread(target=reader)
    t.start()
    try:
        for _ in range(3):
            store.reset()
    finally:
        stop.set()
        t.join()
    assert seen and min(seen) >= 128, min(seen)
