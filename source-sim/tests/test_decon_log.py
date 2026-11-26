"""Plan 9 P9-11.3: call the synthetic decontamination log (mr_decon) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories: MR-03 (two timestamps, the gate uses the end of the cycle), MR-05 (records that arrive later), MR-12 (a record
that ended before the check-in).
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import scheduler
from sim.core.db import engine
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/decon-log/api"
KEY = {"x-api-key": "mr_decon-demo-key"}
FIELDS = {"cycleId", "tag", "method", "enhanced", "cycleStartedAt", "cycleEndedAt", "operatorRef", "result"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh(client):
    """The seed as loaded now, on a clock that starts again."""
    client.post("/_sim/clock/reset").raise_for_status()
    client.post("/_sim/reset", params={"system": "mr_decon"}).raise_for_status()
    scheduler.tick()
    return client


def cycles(client, **params) -> list[dict]:
    r = client.get(f"{API}/cycles", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def tag(n: int) -> str:
    return f"SYN-MR-IP-{n:04d}"


def events(kind: str = "decon.cycle.completed") -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT data FROM sim.outbox WHERE source = 'mr_decon' AND type = :t ORDER BY id"), {"t": kind})
        return [r[0] for r in rows]


def test_registered_beside_the_demo_systems(fresh):
    s = EXTRA_BY_ID["mr_decon"]
    assert (s.vendor, s.style, s.base_path) == ("Decontamination log (synthetic)", "vendor", "/decon-log")
    assert "mr_decon" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_decon" in MOCKS
    body = fresh.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_decon_log_needs_the_key(fresh):
    assert fresh.get(f"{API}/cycles").status_code == 401
    assert fresh.get(f"{API}/cycles", headers={"x-api-key": "wrong"}).status_code == 401
    assert fresh.post(f"{API}/cycles", json={"tag": tag(1)}).status_code == 401


def test_decon_log_seed(fresh):
    """No record for the batch SYN-MR-IP-0020 to 0025; the S4 record ended before the check-in; the others after it."""
    rows = cycles(fresh)
    assert rows and all(set(r) == FIELDS for r in rows)
    by_tag = {r["tag"]: r for r in rows}
    assert len(by_tag) == len(rows) == 39  # one per return, the batch of six left out
    assert not {tag(n) for n in range(20, 26)} & set(by_tag)
    assert [r["cycleEndedAt"] for r in rows] == sorted(r["cycleEndedAt"] for r in rows)
    returns = {r["tag"]: r for r in fresh.get("/rental-system/api/returns", headers={"x-api-key": "mr_rental-demo-key"}).json()}
    assert set(by_tag) | {tag(n) for n in range(20, 26)} == set(returns)
    for t, r in by_tag.items():
        check_in = datetime.fromisoformat(returns[t]["checkedInAt"])
        start, end = datetime.fromisoformat(r["cycleStartedAt"]), datetime.fromisoformat(r["cycleEndedAt"])
        assert start < end, t
        assert (end < check_in) == (t == tag(5)), t  # MR-S4 alone ended before its check-in
    assert by_tag[tag(5)]["cycleId"] == "DC-0005"
    assert {r["tag"] for r in rows if r["enhanced"]} == {tag(10), tag(11)}  # the isolation-ward returns
    assert {r["method"] for r in rows if r["enhanced"]} == {"enhanced"} and {r["result"] for r in rows} == {"pass"}
    assert len({r["cycleId"] for r in rows}) == 39 and all(r["operatorRef"].startswith("OP-") for r in rows)
    assert len(cycles(fresh, tag=tag(1))) == 1 and cycles(fresh, tag=tag(21)) == []


def test_decon_log_filters(fresh):
    assert fresh.get(f"{API}/cycles", params={"updatedSince": "last week"}, headers=KEY).status_code == 400
    assert len(cycles(fresh, updatedSince="2020-01-01")) == 39 and cycles(fresh, updatedSince="2035-01-01T00:00:00Z") == []


def test_decon_log_same_seed_same_json(fresh):
    before = cycles(fresh)
    fresh.post("/_sim/reset", params={"system": "mr_decon"}).raise_for_status()
    assert cycles(fresh) == before


def test_decon_records_arrive_later(fresh):
    """Six hours on, four records (0020 to 0023) and four events; 0024 and 0025 never get one."""
    scheduler.tick()
    assert len(cycles(fresh)) == 39 and events() == []
    fresh.post("/_sim/clock/advance", json={"hours": 5}).raise_for_status()
    scheduler.tick()
    assert len(cycles(fresh)) == 39 and events() == []
    advanced = fresh.post("/_sim/clock/advance", json={"hours": 1.1})  # the route ticks the scheduler itself
    assert advanced.status_code == 200 and advanced.json()["scheduled_ran"] == 4
    rows = cycles(fresh)
    assert len(rows) == 43
    arrived = [r for r in rows if r["tag"] in {tag(n) for n in range(20, 24)}]
    assert [r["tag"] for r in sorted(arrived, key=lambda r: r["tag"])] == [tag(n) for n in range(20, 24)]
    assert all(
        datetime.fromisoformat(r["cycleEndedAt"]) - datetime.fromisoformat(r["cycleStartedAt"]) == timedelta(hours=3)
        for r in arrived
    )
    assert sorted(e["tag"] for e in events()) == [tag(n) for n in range(20, 24)]
    assert {e["cycleId"] for e in events()} == {r["cycleId"] for r in arrived}
    assert cycles(fresh, tag=tag(24)) == [] and cycles(fresh, tag=tag(25)) == []
    assert scheduler.tick() == 0 and len(events()) == 4
    assert {r["tag"] for r in cycles(fresh, updatedSince="2026-10-07T10:00:00Z")} == {r["tag"] for r in arrived}


def test_decon_cycle_post_ends_three_hours_later(fresh):
    r = fresh.post(f"{API}/cycles", json={"tag": tag(30), "enhanced": True}, headers=KEY)
    assert r.status_code == 202, r.text
    body = r.json()
    assert (body["tag"], body["enhanced"], body["status"], body["cycleId"]) == (tag(30), True, "scheduled", "DC-1001")
    assert len(cycles(fresh, tag=tag(30))) == 1  # the seeded cycle only: the new one is not listed yet
    again = fresh.post(f"{API}/cycles", json={"tag": tag(30)}, headers=KEY)
    assert again.status_code == 200 and again.json() == body  # idempotent while it is scheduled
    fresh.post("/_sim/clock/advance", json={"hours": 2.9}).raise_for_status()
    scheduler.tick()
    assert len(cycles(fresh, tag=tag(30))) == 1
    fresh.post("/_sim/clock/advance", json={"hours": 0.2}).raise_for_status()
    scheduler.tick()
    new = [c for c in cycles(fresh, tag=tag(30)) if c["cycleId"] == "DC-1001"]
    assert len(new) == 1 and new[0]["enhanced"] is True and new[0]["method"] == "enhanced"
    assert datetime.fromisoformat(new[0]["cycleEndedAt"]) - datetime.fromisoformat(new[0]["cycleStartedAt"]) == timedelta(hours=3)
    assert new[0]["cycleEndedAt"] == body["scheduledEndAt"]
    assert [e["cycleId"] for e in events() if e["tag"] == tag(30)] == ["DC-1001"]


def test_decon_cycle_post_for_a_batch_tag_is_the_scheduled_one(fresh):
    r = fresh.post(f"{API}/cycles", json={"tag": tag(20)}, headers=KEY)
    assert r.status_code == 200 and r.json()["cycleId"] == "DC-0020"  # already scheduled by the seed


def test_decon_cycle_post_validates(fresh):
    for body in ({}, {"tag": "IP-1"}, {"tag": tag(1), "enhanced": "yes"}, []):
        assert fresh.post(f"{API}/cycles", json=body, headers=KEY).status_code == 422, body
    assert fresh.post(f"{API}/cycles", content=b"not json", headers=KEY).status_code == 400
    assert fresh.post(f"{API}/cycles", json={"tag": tag(1)}, headers=KEY).status_code == 202  # `enhanced` defaults to false
