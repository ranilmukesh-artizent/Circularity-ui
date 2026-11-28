"""Lead decision (28 Nov, smoke p9-6 step 4): a case re-check caused by new evidence runs before bulk jobs and sweeps.

A device's wipe certificate (`condition.wipe_certificate`, as the dvlab webhook's sync lands it) queues `case.gateRecheck` at
`jobs.EVIDENCE_PRIORITY`, so the worker claims it ahead of hundreds of jobs queued earlier at the default 100; a re-check that
was already queued at 100 is raised by the dedupe hit, not left behind.
"""

from sqlalchemy import text

from di.core import jobs
from di.core.db import SessionLocal, engine
from tests.device_registry import seed_wipe

IMEI = "359990000000272"
KEY = f"IMEI:{IMEI}"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model = 'condition' AND key = :k"), {"k": KEY})
        conn.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key = :k"), {"k": KEY})


def test_a_certificate_recheck_runs_before_bulk_jobs():
    _clean()
    try:
        with SessionLocal() as s:
            for n in range(5):  # bulk work queued before the certificate arrives (SLA timers, case work, syncs)
                jobs.enqueue(s, "ping", {"n": n})
            stale = jobs.enqueue(s, "case.gateRecheck", {"asset_key": KEY}, dedupe_key=f"case.gateRecheck:{KEY}")
            s.commit()
            stale_id = stale.id
        seed_wipe(IMEI, certificate_id="WC-00272")
        with SessionLocal() as s:
            rows = s.execute(text("SELECT id, priority FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).all()
            assert [tuple(r) for r in rows] == [(stale_id, jobs.EVIDENCE_PRIORITY)]  # deduped, and raised from 100
            first = jobs.claim(s)
            s.commit()
        assert jobs.EVIDENCE_PRIORITY < 100 and first is not None
        assert (first.kind, first.payload["asset_key"]) == ("case.gateRecheck", KEY)
    finally:
        _clean()
