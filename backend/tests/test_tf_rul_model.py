"""Plan 9, P9-3.10 (stories TF-06 model path, TF-15): the remaining-life model fitted on teardown verdicts.

    model.fit {template: "tool_fleet", kind: "rated_life"}   a candidate: per component a Weibull (shape, scale, median hours)
                                                             fitted on the depot's teardown verdicts, with MAE and concordance
    model.propose, model.promote                             unchanged: a different person promotes; an agent never does

A statistical model (lifelines Weibull), not a language model: no AgentLoop and no model tests belong to it. The verdicts are
written to the canonical store as the repair log's sync would (`repair_event`, kind `teardown`); the pinned clock is 2026-10-07.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.actions.models import MAKER_CHECKER
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import intake
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
COMP = "Motor armature"  # a component of the pack's CMH table
FIT = {"template": "tool_fleet", "kind": "rated_life"}
FIRST_DAY = date(2026, 4, 1)


def _verdict(i: int) -> tuple[int, str]:
    """Run hours and verdict of the i-th teardown: tools worn out above about 1,100 hours, the border blurred by a few tens."""
    hours = 400 + i * 30
    return hours, "worn_out" if hours > 1100 + ((i * 37) % 7 - 3) * 40 else "serviceable"


def _seed(tag: str, n: int, org: str | None = None, comp: str = COMP, cls: str = "CMH") -> None:
    """`n` teardown verdicts of one component, a few days apart; with `org` their serials sit on a contract of that org."""
    facts = []
    for i in range(n):
        key, serial = f"TDX-{tag}-{i}", f"{cls}-X{tag}{i}"
        hours, verdict = _verdict(i)
        when = (FIRST_DAY + timedelta(days=i * 3)).isoformat()
        for f, v in (("kind", "teardown"), ("serial", serial), ("tool_class", cls), ("component", comp), ("run_hours", hours),
                     ("verdict", verdict), ("observed_at", when)):  # fmt: skip
            facts.append(canonical.Fact("repair_event", key, f, v, resource="teardowns"))
        if org:
            facts.append(canonical.Fact("contract_line", serial, "contract_id", f"FC-X-{tag}", resource="lines"))
    if org:
        facts.append(canonical.Fact("contract", f"FC-X-{tag}", "owner_org", org, resource="contracts"))
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", facts)
        s.commit()


def _clean() -> None:
    with engine.begin() as conn:
        for m, pat in (("repair_event", "TDX-%"), ("contract_line", "%-X%"), ("contract", "FC-X-%"), ("condition", "CMH-4821%")):
            conn.execute(text("DELETE FROM provenance WHERE model = :m AND key LIKE :p"), {"m": m, "p": pat})
            conn.execute(text("DELETE FROM canonical WHERE model = :m AND key LIKE :p"), {"m": m, "p": pat})
        conn.execute(text("DELETE FROM model_version"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _fit(user: str = "planner-a") -> dict:
    out = call("model.fit", FIT, user)
    assert out["ok"], out
    return out["output"]


def _promote(mid: str) -> None:
    assert call("model.propose", {"id": mid}, "planner-a")["ok"]
    out = call("model.promote", {"id": mid}, "approver")
    assert out["ok"], out


def _open_cmh() -> dict:
    serial, seen = "CMH-48213", "2026-10-04T08:15:00+00:00"
    facts = [
        canonical.Fact("condition", serial, "run_hours", 820, resource="tools"),
        canonical.Fact("condition", serial, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", serial, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", serial, "telemetry_coverage_pct", 95, resource="tools"),
    ]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()
    f = tool_case_facts(serial, {"tool_class": "CMH", "site": "Houston", "grade": "B", "rul": 62}, seen=seen)
    with SessionLocal() as s:
        c = intake.open_case(
            s,
            {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end", "facts": f},
            "system",
        )
        s.commit()
    return c


# ------------------------------------------------------------------ the fit
def test_tf_15_fit_proposes_candidate_with_metrics():
    _seed("a", 60)
    m = _fit()
    assert m["status"] == "candidate" and m["kind"] == "rated_life" and m["template"] == "tool_fleet"
    (f,) = [x for x in m["factors"] if x["cls"] == "CMH" and x["name"] == COMP]
    assert (
        f["shape"] > 0 and f["scale"] > 0 and 1100 < f["median_hours"] < 2200
    )  # every worn-out tool in the seed ran over 1,100 h
    met = m["metrics"]
    assert met["n"] == 60 and met["mae"] is not None and met["mae"] >= 0
    assert 0 <= met["concordance"] <= 1
    assert call("model.propose", {"id": m["id"]}, "planner-a")["ok"]


def test_tf_15_component_with_few_verdicts_keeps_its_rating():
    _seed("a", 25)
    m = _fit()
    assert m["factors"] == []
    why = m["metrics"]["by_class"]["CMH"]["skipped"]
    assert why == [{"name": COMP, "n": 25, "reason": "Needs at least 30 verdicts; it keeps its current rating."}]


def test_tf_15_another_person_promotes():
    _seed("a", 60)
    m = _fit()
    median = next(x["median_hours"] for x in m["factors"] if x["name"] == COMP)
    _promote(m["id"])
    c = _open_cmh()
    motor = c["life"]["inputs"]["components"][0]
    assert motor["name"] == COMP and motor["source"] == "model" and motor["rated_hours"] == pytest.approx(median, abs=0.06)
    assert c["life"]["table_version"] == m["id"] and c["life"]["range"] is not None
    r = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin"))
    assert r.json()["life"]["table_version"] == m["id"]
    r = client.get("/api/screens/agents/models", headers=h("admin"))
    assert r.json()["activeRatedLife"] == m["id"]


def test_tf_06_model_fallback_without_active_model():
    _seed("a", 60)
    _fit()  # a candidate is not active
    life = _open_cmh()["life"]
    assert life["table_version"] == "tf-life-table-1" and life["rule_version"] == "tf-life-1"
    assert {x["source"] for x in life["per_component"]} == {"pack"}


def test_rated_life_maker_cannot_promote():
    _seed("a", 60)
    mid = _fit("admin")["id"]
    out = call("model.promote", {"id": mid}, "admin")
    assert not out["ok"] and out["error"]["message"] == MAKER_CHECKER
    assert not call("model.promote", {"id": mid}, "planner-a")["ok"]  # no approve.flows


def test_rated_life_agent_cannot_promote():
    assert "model.promote" in FORBIDDEN_ACTIONS and forbidden("model.promote") and forbidden("model.propose")


def test_rated_life_tenant_boundary():
    _seed("a", 40)  # depot-wide history: no contract names an org
    _seed("b", 40, org=ORG)  # on a contract of an org planner-a has no access to
    assert _fit("admin")["metrics"]["n"] == 80
    assert _fit("planner-a")["metrics"]["n"] == 40


def test_rated_life_kind_needs_the_tool_fleet_template():
    out = call("model.fit", {"template": "industrial", "kind": "rated_life"}, "planner-a")
    assert not out["ok"] and out["error"]["code"] == "validation_error"
    out = call("model.fit", {"template": "tool_fleet", "kind": "nonsense"}, "planner-a")
    assert not out["ok"] and out["error"]["code"] == "validation_error"


# ------------------------------------------------------------------ the pure model
def test_rul_model_predict_is_pure():
    import math

    from di.services.models.rul import RulModel

    shape, scale = 2.0, 1000.0
    m = RulModel({"components": [{"name": COMP, "shape": shape, "scale": scale}]})
    want = scale * math.log(2) ** (1 / shape)
    assert m.median(COMP) == pytest.approx(want)
    assert m.predict(COMP, 0).rul_pct == 100
    e = m.predict(COMP, want / 2)
    assert e.rul_pct == 50 and e.p10 <= e.rul_pct <= e.p90 and 0 < e.p_survive_term < 1
    assert m.predict(COMP, 10 * scale).rul_pct == 0
    assert m.has("Nope") is False
    src = (Path(__file__).parents[1] / "di" / "services" / "models" / "rul.py").read_text()
    assert "import lifelines" not in src and "from lifelines" not in src  # the api never loads it on a request
