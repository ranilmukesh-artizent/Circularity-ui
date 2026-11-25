"""Plan 9, P9-5.2 (story CR-02): keep, like-life swap or upgrade for each tool of a contract refresh.

The choice is computed: the remaining life of the tool (P9-3.9), the end of its parts in PLM (P9-3.3) and the per-market
decision table `refresh_tool_action` (I-15, P9-4.2) give one action and its reason. Nothing here reads or writes free text, so
there is no model step: no `AgentLoop` and no model tests belong to this task (R16 has nothing to route). The thresholds are
business rules held in the table, so a market overlay changes them through the table's maker-checker.
"""

import copy
import dataclasses
from datetime import date

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import refresh_intake
from di.services.modeler import tables
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import contract_refresh, tool_life
from tests import starting
from tests.helpers import call, client, h

PARAMS = load_pack("tool_fleet").valuer.params["life"]
NEXT_END = date(2028, 1, 5)
EOP = {"CRH": (date(2027, 3, 31), "TF-CRH2"), "CMH": (date(2028, 6, 30), "TF-CMH2")}


def _table(body: dict | None = None) -> tables.JdmTable:
    spec = tables.market_spec("tool_fleet")
    assert spec is not None
    return tables.JdmTable.model_validate(body or spec.table("refresh_tool_action").body)


def _life(rul: int, conf: str = "High") -> tool_life.LifeResult:
    comps = tool_life.components("CMH", PARAMS, replacements={"Piston and seal kit": 500.0})
    base = tool_life.evaluate(
        tool_life.LifeInputs("CMH", 820.0, 0.30, {}, None, 95.0, 3.0, True, comps), PARAMS
    )  # the worked example: RUL 21
    assert base.rul_tool == 21
    return dataclasses.replace(base, rul_tool=rul, confidence=conf)  # type: ignore[arg-type]


def _run(cls: str, rul: int, market: str = "US", conf: str = "High", table: tables.JdmTable | None = None):
    lines = [{"serial": f"{cls}-1", "cls": cls}]
    (a,) = contract_refresh.tool_actions(
        lines, {f"{cls}-1": _life(rul, conf)}, EOP, NEXT_END, tables.ZenEvaluator(), market, table or _table()
    )
    return a


# ------------------------------------------------------------------ the pure choice
def test_cr_02_upgrade_when_parts_end_before_term():
    a = _run("CRH", 60)
    assert (a.action, a.successor, a.end_of_parts) == ("upgrade", "TF-CRH2", date(2027, 3, 31))
    assert a.reason == "Parts for CRH end 2027-03-31, before the next term ends 2028-01-05: upgrade to TF-CRH2"


def test_cr_02_swap_below_25():
    a = _run("CMH", 21)  # the worked-example CMH; its parts end 2028-06-30, after the term
    assert a.action == "swap" and a.rul_pct == 21
    assert a.reason == "Life left 21% is under 25%: like-life swap"


def test_cr_02_keep_otherwise():
    a = _run("CMH", 60)
    assert a.action == "keep" and a.reason == "Life left 60%: keep"
    assert _run("CMH", 25).action == "keep"  # the limit itself is a keep


def test_cr_02_table_per_market():
    body = copy.deepcopy(_table().dump())
    rules = next(n for n in body["nodes"] if n["type"] == "decisionTableNode")["content"]["rules"]
    row = {k: "" for k in rules[0]}
    row |= {"_id": "de30", "in_market": '"DE"', "in_rul_pct": "< 30", "out_action": '"swap"',
            "out_reason": '"Life left {rul}% is under 30%: like-life swap"'}  # fmt: skip
    rules.insert(0, row)
    t = _table(body)
    assert _run("CMH", 28, "DE", table=t).action == "swap"
    assert _run("CMH", 28, "DE", table=t).reason == "Life left 28% is under 30%: like-life swap"
    assert _run("CMH", 28, "US", table=t).action == "keep"


def test_cr_02_low_confidence_keeps_action_and_waits_for_a_person():
    a = _run("CMH", 60, conf="Low")
    assert a.action == "keep" and a.confidence == "Low"
    assert contract_refresh.flag(a) == "life estimate low confidence"
    assert contract_refresh.hold_reason([a]) == "confidence"
    assert contract_refresh.flag(_run("CMH", 60)) is None
    assert contract_refresh.hold_reason([_run("CMH", 60)]) is None


def test_cr_02_a_tool_without_life_is_low_confidence():
    (a,) = contract_refresh.tool_actions(
        [{"serial": "X-1", "cls": "CMH"}], {}, EOP, NEXT_END, tables.ZenEvaluator(), "US", _table()
    )
    assert a.confidence == "Low" and contract_refresh.hold_reason([a]) == "confidence"


def test_cr_02_totals():
    acts = [_run("CRH", 60), _run("CMH", 21), _run("CMH", 60), _run("CMH", 70)]
    assert contract_refresh.totals(acts) == {"keep": 2, "swap": 1, "upgrade": 1}


def test_cr_02_pack_table_is_a_decision_table_without_code():
    spec = tables.market_spec("tool_fleet")
    assert spec is not None
    t = spec.table("refresh_tool_action")
    assert t.kind == "decision_table" and t.body is not None
    assert tables.validate_table(t.body, declared=t.inputs) == []
    assert t.inputs == ["market", "rul_pct", "parts_end_before_term", "cover_type"]


# ------------------------------------------------------------------ the case panel
ORG = "tool-fleet-a"


def _facts() -> list[canonical.Fact]:
    c = {"contract_id": "FC-30140", "customer": "Brightline Mechanical", "market": "US", "start_date": "2024-01-05",
         "end_date": "2027-01-05", "term_months": 36, "status": "active"}  # fmt: skip
    out = [canonical.Fact("contract", "FC-30140", k, v, resource="contracts") for k, v in c.items()]
    for serial, months in (("FC-30140-S00", 41), ("FC-30140-S01", 5)):
        f = {"contract_id": "FC-30140", "serial": serial, "tool_class": "CMH", "model": "CMH-12 Pro", "fee_month": 55.0,
             "months_on_contract": months, "status": "on_contract", "line_id": "FL-" + serial}  # fmt: skip
        out += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    return out


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM job WHERE kind IN ('refresh.scan', 'work.sla', 'case.replan')"))
        conn.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM work_item WHERE org_unit_id = :o"), {"o": ORG})


@pytest.fixture
def refresh_case():
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    _forget()
    with SessionLocal() as s:
        canonical.apply(s, "fleet", _facts())
        s.commit()
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, ORG, date(2026, 10, 7))
        s.commit()
    assert len(ids) == 1
    yield ids[0]
    _forget()
    starting.reset()


def test_cr_02_panel_lists_each_tool_with_action_and_totals(refresh_case):
    v = client.get(f"/api/screens/refresh/{refresh_case}", headers=h("admin")).json()
    by = {t["serial"]: t for t in v["tools"]}
    assert by["FC-30140-S00"]["action"] == "swap" and by["FC-30140-S00"]["rul_pct"] == 21
    assert by["FC-30140-S00"]["reason"] == "Life left 21% is under 25%: like-life swap"
    assert by["FC-30140-S01"]["action"] == "keep"
    assert by["FC-30140-S00"]["flag"] == "life estimate low confidence"  # months on contract only: GR-13
    assert v["tools_totals"] == {"keep": 1, "swap": 1, "upgrade": 0}
    assert v["tools_hold"] == "confidence"
