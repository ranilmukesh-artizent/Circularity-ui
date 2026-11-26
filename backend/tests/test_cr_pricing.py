"""Plan 9, P9-5.4 (story CR-04): a refresh proposal priced with its fee and renewal odds.

Everything priced here is computed: the fees from the market's `terms` and `refresh_terms` rate cards in force on the decision
date, the credits from the market's `credit_rules` table, the renewal likelihood from the fleet's contract history (a
Laplace-smoothed rate by market and size, `renewal_odds`, nothing trained). Nothing is worded by a language model: every
sentence is a template over those numbers, so there is no `AgentLoop` step and no model tests belong to this task
(R16 has nothing to route; a model may never write a computed number). Sending the proposal is a person's (P9-5.5); `refresh_route` only says who
must approve, and an agent approves nothing (no new action, so `FORBIDDEN_ACTIONS` is unchanged).
"""

import copy
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import market_tables
from di.services.modeler import tables
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import contract_refresh, renewal_odds, tool_approval
from di.services.modeler.valuers.contract_refresh import ToolAction
from tests.helpers import client, h
from tests.test_cr_tool_action import refresh_case  # noqa: F401 - the fixture: FC-30140, one swap and one keep, US

PACK, FLOW = "tool_fleet", "service_desk"
SPEC = tables.market_spec(PACK)
assert SPEC is not None


def _card(name: str, version: int = 0, market: str = "US") -> tables.RateCard:
    v = SPEC.table(name).versions[version]
    vals = {k: Decimal(str(x)) for k, x in v.values[market].items()}
    return tables.RateCard(market, name, version + 1, SPEC.markets[market], v.valid_from, v.valid_to, vals)


TERMS, FEES = _card("terms"), _card("refresh_terms")
CREDITS = tables.JdmTable.model_validate(SPEC.table("credit_rules").body)


def _a(serial: str, action: str, cls: str, rul: int) -> ToolAction:
    return ToolAction(serial, cls, action, "", rul, "High", None, "TF-X2" if action == "upgrade" else None)  # type: ignore[arg-type]


def _line(serial: str, fee: float, months: int) -> dict:
    return {"serial": serial, "fee": fee, "months": months}


def _hist(n: int, renewed: int, proposal: bool, market: str = "US", lines: int = 4) -> list[dict]:
    return [
        {"contractId": f"H-{proposal}-{market}-{i}", "market": market, "lines": lines, "endedAt": "2026-03-01",
         "outcome": "renewed" if i < renewed else "lapsed", "hadProposal": proposal}
        for i in range(n)
    ]  # fmt: skip


ACTIONS = [_a("K1", "keep", "CMH", 60), _a("K2", "keep", "CMH", 60), _a("S1", "swap", "CMH", 21), _a("U1", "upgrade", "CRH", 20)]
LINES = [_line("K1", 55, 20), _line("K2", 55, 20), _line("S1", 55, 41), _line("U1", 25, 41)]
HISTORY = _hist(8, 7, True) + _hist(2, 0, False)  # 7 of 8 renewed with a proposal: 8/10; none of 2 without: 1/4


def _price(actions=ACTIONS, lines=LINES, history=HISTORY, credits=CREDITS, terms=TERMS):
    return contract_refresh.price(
        actions, [{"serial": "S1", "unit_id": "RU-7001"}], terms, credits, history, "US", fees=FEES, lines=lines, term_months=12
    )


# ------------------------------------------------------------------ the pure price
def test_cr_04_proposal_priced():
    p = _price()
    assert (p.current_fee_month, p.proposed_fee_month) == (Decimal("190.00"), Decimal("184.10"))
    assert p.saving_vs_new == Decimal("104.40")  # the swap: (58.00 - 49.30) a month for 12 months
    assert [(c.serial, c.amount, c.rule_version) for c in p.credits] == [
        ("U1", Decimal("155.00"), 1)
    ]  # 25% of the $620 list price
    assert p.credit_total == Decimal("155.00")
    assert p.renewal_likelihood == pytest.approx(0.8) and p.renewal_without == pytest.approx(0.25)
    assert "US contracts of small size, 8 ended in two years with a proposal, 7 renewed" in p.renewal_basis
    assert "modelled, observational (A section 3.4)" in p.renewal_basis
    assert p.lines and all(
        x.cite.startswith(("terms v1, refresh_terms v1", "credit_rules v1", "renewal history")) for x in p.lines
    )
    assert p.rate_card_version == 1 and p.currency == "USD"


def test_cr_04_routes_ranked_with_standard():
    p = _price()
    by = {r.id: r for r in p.routes}
    assert set(by) == {"proposal", "renew_as_is", "upgrade_all"}
    assert by["renew_as_is"].standard and not by["proposal"].standard and not by["upgrade_all"].standard
    assert by["renew_as_is"].net == Decimal("570.00")  # $190 x 12 x 0.25
    assert by["proposal"].net == Decimal("1276.16")  # (184.10 x 12 - 459 refurbishment and logistics - 155 credit) x 0.8
    assert by["upgrade_all"].net == Decimal("1320.48")  # (198.80 x 12 - 735 full credits) x 0.8
    assert [r.id for r in p.routes] == ["upgrade_all", "proposal", "renew_as_is"] and p.best == "upgrade_all"
    assert p.uplift == Decimal("750.48")  # best less renew_as_is


def test_cr_04_renewal_odds_are_a_smoothed_segment_rate():
    assert renewal_odds.likelihood([], {"market": "US", "size": "small"}, True)[0] == 0.5
    rows = _hist(4, 3, True) + _hist(9, 0, True, market="DE")
    p, basis = renewal_odds.likelihood(rows, {"market": "US", "size": "small"}, True)
    assert p == pytest.approx(4 / 6) and "4 ended in two years with a proposal, 3 renewed" in basis
    assert (
        renewal_odds.size_band(5) == "small" and renewal_odds.size_band(6) == "medium" and renewal_odds.size_band(12) == "large"
    )
    old = [{"contractId": "H-old", "endedAt": "2023-01-01"}, {"contractId": "H-new", "endedAt": "2026-05-01"}]
    assert [r["contractId"] for r in renewal_odds.within(old, date(2026, 10, 7))] == ["H-new"]


def _drop_v99() -> None:
    with engine.begin() as c:
        c.execute(
            text("DELETE FROM market_table WHERE pack = :p AND market = 'US' AND name = 'terms' AND version = 99"), {"p": PACK}
        )


def test_cr_04_rate_card_as_of():
    with SessionLocal() as s:
        market_tables.ensure_seeded(s, PACK)
        s.commit()
    body = {"values": {k: float(v) for k, v in TERMS.values.items()} | {"logistics": 99}}
    _drop_v99()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO market_table (org_unit_id, pack, flow, market, name, kind, version, status, valid_from, currency, "
                "body, created_by, approved_by) VALUES (NULL, :p, :f, 'US', 'terms', 'rate_card', 99, 'approved', '2026-11-01', "
                "'USD', CAST(:b AS jsonb), 'test', 'test2')"
            ),
            {"p": PACK, "f": FLOW, "b": json.dumps(body)},
        )
    try:
        with SessionLocal() as s:
            before = market_tables.effective(s, None, PACK, FLOW, "US", "terms", date(2026, 10, 7))
            after = market_tables.effective(s, None, PACK, FLOW, "US", "terms", date(2026, 11, 2))
        assert before is not None and before.version == 1  # a card valid from 2026-11-01 is not used on 2026-10-07
        assert after is not None and after.version == 99
        p = _price(terms=tables.rate_card(before))
        assert p.rate_card_version == 1 and p.lines[0].cite.startswith("terms v1")
    finally:
        _drop_v99()


# ------------------------------------------------------------------ who approves (GR-C1 per proposal, GR-C2)
def _capped(cap: str) -> tables.JdmTable:
    body = copy.deepcopy(SPEC.table("credit_rules").body)
    node = next(n for n in body["nodes"] if n["type"] == "decisionTableNode")
    for r in node["content"]["rules"]:
        r["out_credit_cap"] = cap
    return tables.JdmTable.model_validate(body)


def test_cr_04_credits_over_300_wait_for_sales():
    two = [_a("U1", "upgrade", "CMH", 20), _a("U2", "upgrade", "CMH", 20)]
    p = _price(two, [_line("U1", 55, 41), _line("U2", 55, 41)], credits=_capped("210"))
    assert [c.amount for c in p.credits] == [Decimal("210.00")] * 2 and p.credit_total == Decimal("420.00")  # each under $300
    r = tool_approval.refresh_route(float(p.credit_total), load_pack(PACK))
    assert (r.kind, r.role) == ("person", "Sales")  # per proposal, not per tool
    assert r.reasons == ["credits $420 are over $300"] and r.holds[0]["id"] == "GR-C1" and r.holds[0]["owner"] == "Sales"


def test_cr_04_credits_under_300_still_need_a_person():
    pack = load_pack(PACK)
    for usd in (150.0, 300.0, 0.0):  # the limit itself is not over it
        r = tool_approval.refresh_route(usd, pack)
        assert (r.kind, r.role) == ("person", "Fleet desk") and r.kind != "policy"
        assert r.holds[0]["id"] == "GR-C2"
    g = next(x for x in pack.guardrails if x.id == "GR-C1")
    assert g.type == "Approval" and g.param is not None and g.param.value == 300 and g.owner == "Sales"


# ------------------------------------------------------------------ the case panel
def test_cr_04_panel_prices_the_case_and_cites_its_cards(refresh_case):  # noqa: F811
    v = client.get(f"/api/screens/refresh/{refresh_case}", headers=h("admin")).json()
    p, a = v["pricing"], v["approval"]
    assert p["currency"] == "USD" and p["rate_card_version"] == 1 and p["fees_version"] == 1 and p["credit_rules_version"] == 1
    assert p["current_fee_month"] == 110.0 and p["term_months"] == 36
    assert p["proposed_fee_month"] == 104.3  # S00 swapped to a refurbished CMH ($58.00 less 15% is 49.30), S01 kept at 55
    assert p["saving_vs_new"] == 313.2 and p["credits"] == [] and p["credit_total"] == 0.0  # (58.00 - 49.30) x 36
    assert {r["id"] for r in p["routes"]} == {"proposal", "renew_as_is", "upgrade_all"} and p["best"] in {
        r["id"] for r in p["routes"]
    }
    assert 0 < p["renewal_likelihood"] < 1 and "modelled, observational" in p["renewal_basis"]
    assert (a["kind"], a["role"], a["text"]) == ("person", "Fleet desk", "Waits for the Fleet desk")
