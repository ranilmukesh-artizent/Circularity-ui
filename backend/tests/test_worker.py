"""Plan 2 task 3: the worker wakes on NOTIFY di_jobs (polling stays the fallback), heartbeats long jobs, and its
periodic step reaps stale ones."""

import threading
import time
from datetime import timedelta

from sqlalchemy import text

from di import worker
from di.core import jobs
from di.core.db import SessionLocal


def _serve_in_thread(poll: float) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    t = threading.Thread(target=worker.serve, args=(stop.is_set, poll), kwargs={"housekeeping": False}, daemon=True)
    t.start()
    return stop, t


def _stop(stop: threading.Event, t: threading.Thread) -> None:
    stop.set()
    with SessionLocal() as s:
        s.execute(text("NOTIFY di_jobs, 'stop'"))  # wakes the waiting loop, which then sees `stop`
        s.commit()
    t.join(10)
    assert not t.is_alive()


def test_a_job_enqueued_while_the_worker_waits_is_picked_up_at_once():
    seen: list[float] = []
    worker.HANDLERS["test.wake"] = lambda payload: seen.append(time.monotonic())
    stop, t = _serve_in_thread(poll=30)
    try:
        time.sleep(1.0)  # the queue is empty: the loop is now waiting on di_jobs (up to 30 s)
        with SessionLocal() as s:
            jobs.enqueue(s, "test.wake")
            s.commit()
            queued = time.monotonic()
        deadline = queued + 5
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)
        assert seen, "the job was not picked up"
        assert seen[0] - queued < 1.0
    finally:
        _stop(stop, t)
        worker.HANDLERS.pop("test.wake", None)


def test_a_long_job_heartbeats(monkeypatch):
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.2)
    beats: list[object] = []

    def slow(payload):
        time.sleep(0.4)
        with SessionLocal() as s:  # the first beat came during the run, before the job completes
            first = s.execute(text("SELECT heartbeat_at FROM job WHERE kind = 'test.slow'")).scalar()
        time.sleep(0.5)
        with SessionLocal() as s:
            beats.extend([first, s.execute(text("SELECT heartbeat_at FROM job WHERE kind = 'test.slow'")).scalar()])

    worker.HANDLERS["test.slow"] = slow
    try:
        with SessionLocal() as s:
            jobs.enqueue(s, "test.slow")
            s.commit()
        assert worker.run_once() is True
        assert beats[0] is not None and beats[1] > beats[0]
    finally:
        worker.HANDLERS.pop("test.slow", None)


def test_periodic_reaps_stale_jobs(monkeypatch):
    for name in ("ensure_subscription", "enqueue_due"):  # the rest of periodic() is not under test here
        monkeypatch.setattr(f"di.connectors.{'webhook' if name == 'ensure_subscription' else 'sync'}.{name}", lambda *a: [])
    monkeypatch.setattr(worker, "tick_triggers", lambda: None)
    with SessionLocal() as s:
        job = jobs.enqueue(s, "ping")
        s.commit()
        jobs.claim(s)
        s.execute(text("UPDATE job SET heartbeat_at = now() - :a WHERE id = :i"), {"a": timedelta(minutes=10), "i": job.id})
        s.commit()
    worker.periodic()
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM job WHERE id = :i"), {"i": job.id}).scalar() == "queued"
