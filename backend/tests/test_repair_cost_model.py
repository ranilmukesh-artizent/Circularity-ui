"""Plan 9, P9-4.4 (story SD-02): the repair cost model is computed, never a language model. Pure: hand-built rows and cards,
exact statistics asserted to the cent, the widened key, the range width and the rows that cannot be priced."""

import statistics
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from di.repositories.repair_history import RepairRow
from di.services.modeler.tables import RateCard
from di.services.models.cost import GrS1Params, PriceCards, RepairCostModel, RepairKey

D = Decimal
GR = GrS1Params(min_matches=50, max_width_share=D("0.30"), window_years=3)
PARTS = {"CRH.Brushless motor": D(160), "CRH.Electronics module": D(95), "CRH.Chuck assembly": D(45)}


def _card(name: str, version: int, values: dict[str, Decimal]) -> RateCard:
    return RateCard("US", name, version, "USD", date(2026, 1, 1), None, values)


CARDS = PriceCards(
    _card("labour", 1, {"per_hour": D(58)}), _card("parts", 2, PARTS), _card("terms", 1, {"test_fee": D(14)})
)  # fmt: skip


def _row(i: int, parts: list[dict], hours: float, age: int = 18, fault: str = "MOT", cls: str = "CRH") -> RepairRow:
    return RepairRow(f"RH-{i}", None, cls, age, fault, "US", parts, hours, None, 5, None, "USD", date(2026, 5, 1))


def _hand_rows() -> list[RepairRow]:
    shapes = [
        [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}],
        [{"PART_NUMBER": "CRH-1", "QUANTITY": 1}, {"PART_NUMBER": "CRH-2", "QUANTITY": 2}],
        [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}, {"PART_NUMBER": "CRH-2", "QUANTITY": 1}],
    ]
    return [_row(i, shapes[i % 3], 0.25 * (4 + i % 9)) for i in range(60)]


def _cents(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), ROUND_HALF_UP)


def _expected(rows: list[RepairRow]) -> tuple[Decimal, Decimal, Decimal]:
    """The rule of the module docstring, worked again here from the rows and the card prices."""
    price = {0: D(160), 1: D(95), 2: D(45)}
    parts = [sum(D(p["QUANTITY"]) * price[int(p["PART_NUMBER"][-1])] for p in r.parts) for r in rows]
    hours = [D(str(r.labour_hours)) for r in rows]
    totals = sorted(p + h * 58 + 14 for p, h in zip(parts, hours, strict=True))
    q = statistics.quantiles(totals, n=10, method="inclusive")
    point = _cents(statistics.median(parts)) + _cents(statistics.median(hours) * 58) + D(14)
    return point, _cents(q[0]), _cents(q[8])


def test_repair_cost_model_exact_statistics():
    rows = _hand_rows()
    e = RepairCostModel().estimate(rows, RepairKey("CRH", "MOT", "13-24"), CARDS, GR, None)
    point, p10, p90 = _expected(rows)
    assert (e.point, e.p10, e.p90, e.n) == (point, p10, p90, 60)
    assert (e.point, e.p10, e.p90) == (D("315.00"), D("232.00"), D("361.95"))  # worked by hand from the 60 rows
    assert e.key_used == "class_fault_age" and e.currency == "USD" and e.confidence == 0.80
    assert [ln.label for ln in e.lines] == ["Parts", "Labour", "Test fee"]
    assert sum(ln.amount for ln in e.lines) == e.point
    assert e.lines[1].basis == "2 h × $58/h" and e.lines[1].cites == "US labour rates v1"
    assert e.lines[0].cites == "US parts prices v2" and e.lines[2].cites == "US terms v1"


def test_repair_cost_model_uses_held_out_coverage_as_confidence():
    e = RepairCostModel().estimate(_hand_rows(), RepairKey("CRH", "MOT", "13-24"), CARDS, GR, 0.92)
    assert e.confidence == 0.92


def test_sd_02_widened_key():
    rows = [_row(i, [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}], 1.0, age=18) for i in range(20)]
    rows += [_row(100 + i, [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}], 1.0, age=30) for i in range(50)]
    e = RepairCostModel().estimate(rows, RepairKey("CRH", "MOT", "13-24"), CARDS, GR, None)
    assert e.key_used == "class_fault" and e.n == 70 and e.auto


def test_sd_02_wide_range_not_auto():
    # 30 repairs with 104 of a 1.00 part, 30 with 197: the range is 93 on a point of 222.50, 42% of it
    cheap = [_row(i, [{"PART_NUMBER": "CRH-0", "QUANTITY": 104}], 1.0) for i in range(30)]
    dear = [_row(50 + i, [{"PART_NUMBER": "CRH-0", "QUANTITY": 197}], 1.0) for i in range(30)]
    cards = PriceCards(CARDS.labour, _card("parts", 2, {"CRH.Brushless motor": D(1)}), CARDS.terms)
    e = RepairCostModel().estimate(cheap + dear, RepairKey("CRH", "MOT", "13-24"), cards, GR, None)
    assert e.n == 60 and not e.auto and e.point == D("222.50")
    assert (e.p90 - e.p10) / e.point > D("0.41") and "range is 42% of the estimate (over 30%)" in e.reason


def test_sd_02_under_min_matches_is_a_draft():
    rows = [_row(i, [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}], 1.0) for i in range(37)]
    e = RepairCostModel().estimate(rows, RepairKey("CRH", "MOT", "13-24"), CARDS, GR, None)
    assert not e.auto and e.reason == "37 similar repairs (under 50): draft, a technician checks"


def test_sd_02_no_match_and_no_fault_code():
    e = RepairCostModel().estimate([], RepairKey("CRH", "MOT", "13-24"), CARDS, GR, None)
    assert (e.point, e.n, e.auto, e.reason) == (D(0), 0, False, "No similar repair in 3 years")
    e = RepairCostModel().estimate(_hand_rows(), RepairKey("CRH", None, "13-24"), CARDS, GR, None)
    assert not e.auto and e.reason.startswith("No fault code") and e.n == 0


def test_sd_02_a_repair_that_cannot_be_priced_is_not_counted():
    rows = [*_hand_rows(), _row(900, [{"PART_NUMBER": "CRH-9", "QUANTITY": 1}], 1.0), _row(901, [], None)]  # type: ignore[arg-type]
    e = RepairCostModel().estimate(rows, RepairKey("CRH", "MOT", "13-24"), CARDS, GR, None)
    assert e.n == 60
