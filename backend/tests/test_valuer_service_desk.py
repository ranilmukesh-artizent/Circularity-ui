"""Plan 9, P9-4.6 (story SD-04): the pure options valuer of a service-desk ticket (fix, covered swap, upgrade).

Every figure the valuer returns is worked again here from the inputs, with no code of the valuer: the checks are the spec's
formulas. There is no model step (R16): every number and every reason is computed, so there are no model tests.
"""

import math
from decimal import ROUND_HALF_UP, Decimal

from di.services.modeler.valuers import service_desk as sdv
from di.services.modeler.valuers.tool_fleet import CLS

D = Decimal
REFS = ["US labour rates v1", "US parts prices v2", "US terms v1", "US cover terms v1", "US credit rules v1"]


def _c(x: float | Decimal) -> Decimal:
    return D(str(x)).quantize(D("0.01"), ROUND_HALF_UP)


def _line(n: int = 1, cls: str = "CRH", life: int = 40, *, covered: bool = False, swap: bool = False, upgrade: bool = False,
          stock: int = 2, point: float = 430, auto: bool = True, pct: float = 0.1, cap: float = 150, days: int | None = 5,
          cited: list[str] | None = None) -> dict:  # fmt: skip
    return {
        "n": n, "serial": f"S-{n}", "model_class": cls, "family": CLS[cls]["name"], "life_used_pct": life,
        "estimate": {"point": point, "auto": auto, "n": 60, "reason": "", "currency": "USD", "confidence": 0.8,
                     "lines": [{"label": "Parts", "amount": 300, "basis": "x", "cites": REFS[1]},
                               {"label": "Labour", "amount": 100, "basis": "x", "cites": REFS[0]},
                               {"label": "Test fee", "amount": 30, "basis": "x", "cites": REFS[2]}]},
        "cover": {"repair_covered": covered, "swap_allowed": swap, "upgrade_allowed": upgrade, "reason": "No cover",
                  "ref": REFS[3]},
        "credit": {"credit_pct": pct, "credit_cap": cap, "ref": REFS[4]},
        "terms": {"logistics": 24, "markup": 0.35, "unit_cost_share": 0.62, f"list_price.{cls}": 620, "swap_days": 2,
                  "upgrade_days": 3, "ref": REFS[2]},
        "refurb_stock": stock, "fix_days": days, "cited": cited or REFS,
    }  # fmt: skip


def _inputs(*lines: dict, shift: float = 0.0) -> dict:
    return {"market": "US", "currency": "USD", "fx": 1.0, "take_up": {"a": -3.2, "b": 9.0, "shift": shift, "source": "prior"},
            "approved": REFS, "lines": list(lines)}  # fmt: skip


def _opt(d: dict, k: str, line: int = 0) -> dict:
    return next(o for o in d["lines"][line]["options"] if o["k"] == k)


def _p(pct: float, shift: float = 0.0) -> float:
    return 1 / (1 + math.exp(-(-3.2 + shift + 9.0 * pct)))


def test_sd_04_uncovered_fix_price_is_cost_plus_markup():
    d = sdv.decide_ticket(_inputs(_line()))
    fix = _opt(d, "fix")
    assert fix["eligible"] and fix["customer_price"] == float(_c(430 * 1.35))
    assert fix["margin"] == float(_c(430 * 1.35 - 430 - 24)) and fix["days"] == 5


def test_sd_04_covered_fix_is_free_and_costs_the_margin():
    d = sdv.decide_ticket(_inputs(_line(covered=True)))
    fix = _opt(d, "fix")
    assert fix["customer_price"] == 0 and fix["margin"] == -(430 + 24)


def test_sd_04_swap_needs_cover_and_stock_with_reasons():
    no_cover = _opt(sdv.decide_ticket(_inputs(_line())), "swap")
    assert not no_cover["eligible"] and no_cover["why"] == "Covered swap is not allowed: No cover"
    none = _opt(sdv.decide_ticket(_inputs(_line(swap=True, stock=0))), "swap")
    assert not none["eligible"] and none["why"] == "No refurbished Cordless rotary hammer, 22 V in stock"
    ok = _opt(sdv.decide_ticket(_inputs(_line(swap=True, covered=True))), "swap")
    refurb, back = CLS["CRH"]["refurb"], CLS["CRH"]["res"]["C"] * CLS["CRH"]["newP"]
    assert ok["eligible"] and ok["days"] == 2
    assert ok["margin"] == float(_c(-(refurb + 2 * 24) + back)) and ok["customer_price"] == 0


def test_sd_04_upgrade_credit_margin_and_expected_margin():
    d = sdv.decide_ticket(_inputs(_line(life=60, pct=0.2, cap=300)))
    up, fix = _opt(d, "upgrade"), _opt(d, "fix")
    credit = min(0.2 * 620, 300)
    back = CLS["CRH"]["res"]["C"] * CLS["CRH"]["newP"]
    m_up = (620 - credit) - 0.62 * 620 - 24 + back
    p = _p(0.2)
    assert up["eligible"] and up["customer_price"] == float(_c(620 - credit)) and up["days"] == 3
    assert up["margin"] == float(_c(m_up)) and abs(up["take_up"] - p) < 1e-6
    assert abs(up["expected_margin"] - float(_c(p * m_up + (1 - p) * fix["margin"]))) < 0.02


def test_sd_04_upgrade_credit_is_capped_and_account_shift_moves_take_up():
    d = sdv.decide_ticket(_inputs(_line(life=90, pct=0.25, cap=100), shift=0.7))
    up = _opt(d, "upgrade")
    assert up["credit"] == 100.0 and abs(up["take_up"] - _p(0.25, 0.7)) < 1e-6


def test_sd_04_upgrade_not_offered_before_half_the_life_unless_cover_allows():
    early = _opt(sdv.decide_ticket(_inputs(_line(life=49))), "upgrade")
    assert not early["eligible"] and early["why"] == "Upgrade is offered from 50% of life used (BR-S1); this tool has used 49%"
    assert _opt(sdv.decide_ticket(_inputs(_line(life=49, upgrade=True))), "upgrade")["eligible"]
    assert _opt(sdv.decide_ticket(_inputs(_line(life=50))), "upgrade")["eligible"]


def test_sd_04_best_is_the_highest_expected_margin_and_each_value_line_cites():
    d = sdv.decide_ticket(_inputs(_line(swap=True, covered=True, life=60, pct=0.25, cap=300)))
    line = d["lines"][0]
    eligible = [o for o in line["options"] if o["eligible"]]
    assert line["best"] == max(eligible, key=lambda o: o["expected_margin"])["k"]
    for o in eligible:
        assert o["lines"] and all(v["cites"] for v in o["lines"])


def test_sd_04_holds_gr14_gr_c1_and_confidence_in_the_order_r20():
    big = sdv.decide_ticket(_inputs(_line(point=700, covered=True)))
    assert [h["id"] for h in sdv.approval_holds(big, "fix")] == ["GR-14"]
    assert sdv.approval_holds(big, "fix")[0]["owner"] == "Fleet manager"
    small = sdv.decide_ticket(_inputs(_line(point=600)))
    assert sdv.approval_holds(small, "fix") == []  # 600 is not above 600
    credit = sdv.decide_ticket(_inputs(_line(life=90, pct=0.25, cap=400)))
    assert [h["id"] for h in sdv.approval_holds(credit, "upgrade")] == []  # 155 of credit
    rich = _line(life=90, pct=0.9, cap=400)
    rich["terms"]["list_price.CRH"] = 1500
    big_credit = sdv.decide_ticket(_inputs(rich))
    holds = sdv.approval_holds(big_credit, "upgrade")
    assert [h["id"] for h in holds] == ["GR-C1"] and holds[0]["owner"] == "Sales"
    draft = sdv.decide_ticket(_inputs(_line(auto=False)))
    assert [h["id"] for h in sdv.approval_holds(draft, "fix")] == ["GR-S1"]


def test_sd_04_gr_s3_stale_table_holds_the_case():
    d = sdv.decide_ticket(_inputs(_line(cited=[*REFS[:1], "US parts prices v1", *REFS[2:]])))
    holds = sdv.approval_holds(d, "fix")
    assert [h["id"] for h in holds] == ["GR-S3"]
    assert holds[0]["reason"] == "Prices must come from the market's current approved table (GR-S3)"


def test_sd_04_currency_converts_to_usd_for_the_limits():
    ln = _line(point=500, covered=True)  # 500 EUR is 543 USD at 0.92: under 600; 560 EUR is 608.7
    inp = _inputs(ln) | {"currency": "EUR", "fx": 0.92}
    assert sdv.approval_holds(sdv.decide_ticket(inp), "fix") == []
    ln2 = _line(point=560, covered=True)
    holds = sdv.approval_holds(sdv.decide_ticket(_inputs(ln2) | {"currency": "EUR", "fx": 0.92}), "fix")
    assert [h["id"] for h in holds] == ["GR-14"]


def test_sd_04_case_best_sums_lines_and_needs_every_line_eligible():
    d = sdv.decide_ticket(_inputs(_line(1, swap=True, covered=True), _line(2)))
    case = {o["k"]: o for o in d["options"]}
    assert case["swap"]["eligible"] is False  # line 2 has no covered swap
    assert case["fix"]["eligible"] and case["fix"]["expected_margin"] == round(
        sum(_opt(d, "fix", i)["expected_margin"] for i in (0, 1)), 2
    )


def test_sd_04_no_estimate_means_no_priced_option():
    ln = _line()
    ln["estimate"] = None
    d = sdv.decide_ticket(_inputs(ln))
    assert not any(o["eligible"] for o in d["lines"][0]["options"]) and d["lines"][0]["best"] is None
    assert _opt(d, "fix")["why"] == "No estimate yet: a technician checks the tool first"
