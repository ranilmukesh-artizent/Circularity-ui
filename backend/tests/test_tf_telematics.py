"""Plan 9, P9-3.8 (story TF-05): the stale telematics guardrail GR-13. Re-issue and pool need a person when the tool's telematics
are a week old or missing.

`fleet_evidence.telematics_check` (pure) reads the telematics reading (the canonical `condition.telemetry_at` of the serial) at
the clock the case is decided at: a reading `max_age_days` (7) or more old, or none, fails the gate G-TOOL-TEL (the pack's
GR-13, locked) with "Telematics last seen <n> days ago" or "No telematics for this tool". The gate is a hold on the routes
`release` (re-issue) and `redeploy` (pool): they stay valued and shown, but are never the recommendation, and one exception
item `stale_telematics` is open for Quality. The other four routes are untouched. No model step: the check reads a date.

The pinned clock is 2026-10-07 09:00 UTC. It starts and ends with the demo reset.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core import golden
from di.core.db import SessionLocal, engine
from di.services.cases import intake
from di.services.cases.decide import decide_case
from di.services.modeler import gates
from di.services.modeler.compile import FlowVersion
from di.services.modeler.evidence import Evidence
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import fleet_evidence, tool_fleet
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
SERIALS = ("CMH-48213", "CMH-48777")
HELD = {"release", "redeploy"}


def _reading(seen: str) -> Evidence:
    return Evidence("telematics_reading", "tooltel", datetime.fromisoformat(seen), "pass", {"lastSeen": seen})


# ------------------------------------------------------------------ the pure check
def test_tf_05_check_stale_holds():
    r = fleet_evidence.telematics_check(_reading("2026-09-29T07:40:00+00:00"), NOW, 7)
    assert not r.passed and r.reason == "Telematics last seen 8 days ago"
    assert r.gate_id == "G-TOOL-TEL" and r.effect.kind == "require_approval"
    assert not fleet_evidence.telematics_check(_reading("2026-09-30T09:00:00+00:00"), NOW, 7).passed  # exactly 7 days: stale


def test_tf_05_check_fresh_passes():
    r = fleet_evidence.telematics_check(_reading("2026-10-04T08:15:00+00:00"), NOW, 7)
    assert r.passed and r.reason == "Telematics 3 days old"
    assert fleet_evidence.telematics_check(_reading("2026-10-01T09:00:00+00:00"), NOW, 7).passed  # 6 days
    assert fleet_evidence.telematics_check(_reading("2026-10-06T08:00:00+00:00"), NOW, 7).reason == "Telematics 1 day old"


def test_tf_05_check_no_telematics_holds():
    r = fleet_evidence.telematics_check(None, NOW, 7)
    assert not r.passed and r.reason == "No telematics for this tool"
    assert not fleet_evidence.telematics_check(_reading("2026-10-06T08:00:00+00:00"), NOW, 0).passed  # a limit of 0 days


def test_tf_05_the_pack_holds_only_reissue_and_pool():
    pack = load_pack("tool_fleet")
    g = next(g for g in gates.pack_gates(pack) if g.id == "G-TOOL-TEL")
    assert g.params == {"guardrail": "GR-13", "max_age_days": 7, "locked": True} and g.locked
    assert set(gates.gate_routes(g, pack)) == HELD
    kind = next(t for t in pack.runtime.exception_types if t.id == "stale_telematics")
    assert kind.owner_role == "Quality" and pack.roles["Quality"] == "Approver"


# ------------------------------------------------------------------ cases opened from data
def _clean() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition"):
            conn.execute(text("DELETE FROM provenance WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": [*SERIALS, "FC-TEST"]})
            conn.execute(text("DELETE FROM canonical WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": [*SERIALS, "FC-TEST"]})


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _open(serial: str, seen: str | None) -> dict:
    facts = tool_case_facts(serial, {"tool_class": serial.split("-")[0], "site": "Houston", "grade": "B", "rul": 62}, seen=seen)
    with SessionLocal() as s:
        c = intake.open_case(
            s,
            {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end", "facts": facts},
            "system",
        )
        s.commit()
    return c


def _gate(c: dict) -> dict:
    return next(g for g in c["gates"] if g["id"] == "G-TOOL-TEL")


def _items(case_id: str) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT owner_role, cause, action, status FROM work_item "
                "WHERE case_id = :c AND type = 'stale_telematics' ORDER BY id"
            ),
            {"c": case_id},
        )
        return [dict(r._mapping) for r in rows]


def test_tf_05_stale_telematics_holds_reissue_and_pool():
    c = _open("CMH-48777", "2026-09-29T07:40:00+00:00")
    g = _gate(c)
    assert not g["passed"] and g["reason"] == "Telematics last seen 8 days ago" and g["guardrail"] == "GR-13" and g["locked"]
    assert c["recommendation"] is not None and c["recommendation"]["id"] not in HELD and c.get("gateHold") is None
    items = [i for i in _items(c["id"]) if i["status"] == "open"]
    assert len(items) == 1 and items[0]["owner_role"] == "Approver" and "Telematics last seen 8 days ago" in items[0]["cause"]


def test_tf_05_no_telematics_holds_reissue_and_pool():
    c = _open("CMH-48777", None)
    g = _gate(c)
    assert not g["passed"] and g["reason"] == "No telematics for this tool"
    assert c["recommendation"] is None or c["recommendation"]["id"] not in HELD
    assert len([i for i in _items(c["id"]) if i["status"] == "open"]) == 1


def test_tf_05_fresh_telematics_passes():
    c = _open("CMH-48213", "2026-10-04T08:15:00+00:00")
    g = _gate(c)
    assert g["passed"] and g["reason"] == "Telematics 3 days old"
    assert [i for i in _items(c["id"]) if i["status"] == "open"] == []


def test_tf_05_screen_carries_the_age():
    stale = _open("CMH-48777", "2026-09-29T07:40:00+00:00")
    r = client.get(f"/api/screens/toolfleet/{stale['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    g = next(x for x in r.json()["gates"] if x["id"] == "G-TOOL-TEL")
    assert g["passed"] is False and g["reason"] == "Telematics last seen 8 days ago" and g["guardrail"] == "GR-13"
    assert g["age_days"] == 8 and g["max_age_days"] == 7 and g["owner"]
    assert next(x for x in r.json()["gates"] if x["id"] == "G-CON-2")["passed"]


def test_tf_05_stale_telematics_never_recommends_reissue_or_pool_even_at_the_highest_net():
    """The sample world has returns whose best path is re-issue or pool (the golden decisions): with a stale reading the same
    case is valued as before, but the recommendation is another route (or none), and both routes keep their net."""
    pack = load_pack("tool_fleet")
    queue = tool_fleet.sample_live_cases()
    want = [w for w in golden.load("po/equip_decisions")["decisions"] if w["best"]["k"] in HELD]
    assert want, "the sample world has no return whose best is re-issue or pool"
    by_id = {c["id"]: c for c in tool_fleet.sample_queue()}
    stale = {"type": "telematics_reading", "source": "tooltel", "at": "2026-09-29T07:40:00+00:00", "result": "pass",
             "value": {"lastSeen": "2026-09-29T07:40:00+00:00"}}  # fmt: skip
    for w in want:
        case = dict(by_id[w["id"]])
        base = decide_case(dict(case), pack, FlowVersion(None, 0, ()), NOW, queue=queue)
        assert base.recommendation["id"] == w["best"]["k"] and all(g.passed for g in base.gates)
        d = decide_case(dict(case) | {"evidenceRecords": [stale]}, pack, FlowVersion(None, 0, ()), NOW, queue=queue)
        tel = next(g for g in d.gates if g.gate_id == "G-TOOL-TEL")
        assert not tel.passed and tel.reason == "Telematics last seen 8 days ago", w["id"]
        assert d.recommendation is None or d.recommendation["id"] not in HELD, w["id"]
        net = lambda dec: {r["id"]: r["net"] for r in dec.routes if r["id"] in HELD}  # noqa: E731
        assert net(d) == net(base), w["id"]  # the held routes keep their net
        assert all(not r["excluded"] for r in d.routes if r["id"] == w["best"]["k"])  # still valued and shown
