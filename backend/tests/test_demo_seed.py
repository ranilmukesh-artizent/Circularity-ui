"""Demo seed per pack and for agents (UI audit 26 Nov, gaps 5 and 6).

After the starting state plus `demo_seed.seed()` (what `scripts/reset_starting.py` runs), each non-industrial pack has real
cases opened through `case.open` (one held, one waiting for a person, one closed), two agent runs have real steps, and
proposals wait for a person with their reasons (value, confidence, taint). The industrial demo is untouched.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from tests import demo_seed, starting

PACKS = ("tool_fleet", "device", "used_cars", "telecom_network", "medical_rental")


@pytest.fixture(scope="module")
def seeded():
    starting.reset()
    out = demo_seed.seed()
    yield out
    starting.reset()


def _cases(pack: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, data->>'stage' AS stage, data->'gateHold' AS gate FROM case_record WHERE data->>'template' = :t"),
            {"t": pack},
        ).mappings()
        return [dict(r) for r in rows]


@pytest.mark.parametrize("pack", PACKS)
def test_seed_three_cases_per_pack(seeded, pack):
    cases = _cases(pack)
    assert {c["id"] for c in cases} >= set(seeded["cases"][pack].values())
    by = {kind: next(c for c in cases if c["id"] == cid) for kind, cid in seeded["cases"][pack].items()}
    assert set(by) == {"held", "waiting", "closed"}
    assert by["held"]["stage"] == "none"
    assert by["waiting"]["stage"] == "awaiting_approval"
    assert by["closed"]["stage"] == "closed"


def test_seed_leaves_the_industrial_demo_alone(seeded):
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM case_record WHERE data->>'template' IS NULL")).scalar_one()
        stage = conn.execute(text("SELECT data->>'stage' FROM case_record WHERE id = 'RT-1048'")).scalar_one()
    assert n == 128 and stage == "awaiting_approval"


def test_seed_agent_runs_have_steps(seeded):
    with SessionLocal() as s:
        runs = s.execute(text("SELECT id, status, step FROM agent_run")).mappings().all()
        assert len(runs) >= 2
        for r in runs:
            n = s.execute(text("SELECT count(*) FROM agent_run_step WHERE run_id = :i"), {"i": r["id"]}).scalar_one()
            assert n >= 2, r


def test_seed_proposals_wait_with_reasons(seeded):
    with SessionLocal() as s:
        rows = s.execute(text("SELECT id, status, reasons, case_id FROM agent_proposal")).mappings().all()
    assert 2 <= len(rows) <= 4 and all(r["status"] == "pending" for r in rows)
    kinds = {x["reason"] for r in rows for x in r["reasons"]}
    assert {"value", "confidence", "taint"} <= kinds, kinds
    assert len({r["case_id"] for r in rows}) == len(rows)


def test_seed_agents_never_approved(seeded):
    with SessionLocal() as s:
        n = s.execute(
            text("SELECT count(*) FROM action_journal WHERE preparer IS NOT NULL AND action LIKE 'decision.approve%'")
        ).scalar_one()
    assert n == 0
