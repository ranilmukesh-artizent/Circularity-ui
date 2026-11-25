"""The repair cost model (plan 9, P9-4.4, story SD-02; registry entry I-14 `RepairCostModel`). Pure: rows and rate cards in, an
`Estimate` out. It reads no database, clock or language, and it never writes.

    RepairCostModel().estimate(history, key, cards, gr_s1, coverage) -> Estimate

Method (the same for every call, so the same facts give the same estimate, R19):
  1. The rows of the key's class and fault whose age band is the key's; fewer than `gr_s1.min_matches` widens to every age
     (`key_used` "class_fault").
  2. Each match is priced again at today's cards: its parts (quantity x today's price of the part), its labour hours x today's
     rate, and the market's test fee. A match whose part has no price today, or that has no labour hours, is left out: it cannot
     be priced, so it is not counted.
  3. `point` is the median parts cost + the median hours x the rate + the test fee, line by line, each line rounded half up to
     the cent, so the lines add up to the point. The test fee is the market's `terms` fee: a repair is always tested.
  4. `p10` and `p90` are the 10th and 90th percentile of the matches' totals (`statistics.quantiles(n=10, method="inclusive")`).
  5. `auto` (priced without a technician): enough matches, a range no wider than `max_width_share` of the point, and a known
     fault code. Else `reason` says which one failed and the estimate is a draft for a technician to check.
  6. `confidence` is the family's held-out coverage when given (P9-4.5), else 0.80, the nominal share the P10 to P90 holds.

Money is `Decimal`. Never does: read a table or the history (di.services.service_desk.estimate does), book the technician check,
or call a language model: the estimate and every number in its reason are computed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median, quantiles
from typing import Literal

from di.repositories.repair_history import BANDS, RepairRow
from di.services.modeler.tables import RateCard, TableRef, rate
from di.services.modeler.valuers.tool_fleet import CLS

PACK, FLOW = "tool_fleet", "service_desk"
NOMINAL = 0.80  # the share of repairs a P10 to P90 range holds
CENT = Decimal("0.01")
SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$"}


@dataclass(frozen=True)
class RepairKey:
    model_class: str
    fault_code: str | None
    age_band: str


@dataclass(frozen=True)
class GrS1Params:
    """GR-S1, the estimate guardrail's parameters (the pack's `valuer.params.service_desk.gr_s1`)."""

    min_matches: int
    max_width_share: Decimal
    window_years: int


@dataclass(frozen=True)
class PriceCards:
    """The three cards in force on the ticket's date for its market: labour rates, parts prices and terms."""

    labour: RateCard
    parts: RateCard
    terms: RateCard

    @property
    def currency(self) -> str:
        return self.labour.currency


@dataclass(frozen=True)
class PriceLine:
    label: str
    amount: Decimal
    basis: str
    cites: str


@dataclass(frozen=True)
class Estimate:
    point: Decimal
    p10: Decimal
    p90: Decimal
    n: int
    key_used: Literal["class_fault_age", "class_fault"]
    lines: list[PriceLine]
    auto: bool
    reason: str
    confidence: float
    currency: str


def age_band(months: int | None) -> str | None:
    """The band of an age in months (`repair_history.BANDS`), None when the age is not known."""
    if months is None:
        return None
    return next((b for b, (lo, hi) in BANDS.items() if months >= lo and (hi is None or months <= hi)), None)


def cite(card: RateCard) -> str:
    """What a priced line cites: "US labour rates v1"."""
    return str(TableRef(PACK, FLOW, card.market, card.name, card.version))


def money(amount: Decimal, currency: str) -> str:
    """ "$430" or "$430.50": whole amounts without cents."""
    sym = SYMBOL.get(currency, currency + " ")
    return f"{sym}{amount:,.0f}" if amount == amount.to_integral_value() else f"{sym}{amount:,.2f}"


def _cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, ROUND_HALF_UP)


def _hours(x: Decimal) -> str:
    return f"{x.normalize():f}"


def _parts_cost(row: RepairRow, cards: PriceCards) -> Decimal | None:
    """Today's price of the parts of one repair, None when a part has no price today."""
    names = CLS.get(row.model_class, {}).get("parts") or []
    total = Decimal(0)
    for p in row.parts:
        try:
            idx = int(str(p["PART_NUMBER"]).rsplit("-", 1)[1])
            total += Decimal(str(p.get("QUANTITY", 1))) * rate(cards.parts, f"{row.model_class}.{names[idx][0]}")
        except (KeyError, IndexError, ValueError):
            return None
    return total


def unpriced(
    reason: str, key_used: Literal["class_fault_age", "class_fault"], n: int, currency: str, confidence: float
) -> Estimate:
    """A draft with nothing priced: point 0 and the reason a technician reads."""
    zero = Decimal("0.00")
    return Estimate(zero, zero, zero, n, key_used, [], False, reason, confidence, currency)


class RepairCostModel:
    def estimate(
        self, history: Sequence[RepairRow], key: RepairKey, cards: PriceCards, gr_s1: GrS1Params, coverage: float | None
    ) -> Estimate:
        conf = NOMINAL if coverage is None else coverage
        cur = cards.currency
        none = f"No similar repair in {gr_s1.window_years} years"
        if key.fault_code is None:
            return unpriced("No fault code on the ticket: draft, a technician checks", "class_fault_age", 0, cur, conf)
        same = [r for r in history if r.model_class == key.model_class and r.fault_code == key.fault_code]
        used: Literal["class_fault_age", "class_fault"] = "class_fault_age"
        matches = self._priced([r for r in same if age_band(r.age_months) == key.age_band], cards)
        if len(matches) < gr_s1.min_matches:
            used, matches = "class_fault", self._priced(same, cards)
        if not matches:
            return unpriced(none, used, 0, cur, conf)
        n = len(matches)
        fee = rate(cards.terms, "test_fee")
        per_hour = rate(cards.labour, "per_hour")
        med_parts = Decimal(median(p for p, _ in matches))
        med_hours = Decimal(median(h for _, h in matches))
        labour = f"{_hours(med_hours)} h × {money(per_hour, cur)}/h"
        lines = [
            PriceLine("Parts", _cents(med_parts), f"median of {n} similar repairs at today's prices", cite(cards.parts)),
            PriceLine("Labour", _cents(med_hours * per_hour), labour, cite(cards.labour)),
            PriceLine("Test fee", _cents(fee), "test of the tool", cite(cards.terms)),
        ]
        point = sum((ln.amount for ln in lines), Decimal(0))
        totals = sorted(p + h * per_hour + fee for p, h in matches)
        cuts = quantiles(totals, n=10, method="inclusive") if n > 1 else [totals[0]] * 9
        p10, p90 = _cents(cuts[0]), _cents(cuts[8])
        auto, why = self._auto(n, point, p10, p90, gr_s1)
        return Estimate(point, p10, p90, n, used, lines, auto, why, conf, cur)

    @staticmethod
    def _priced(rows: Sequence[RepairRow], cards: PriceCards) -> list[tuple[Decimal, Decimal]]:
        """(parts cost, hours) of each row that can be priced at today's cards."""
        out: list[tuple[Decimal, Decimal]] = []
        for r in rows:
            parts = _parts_cost(r, cards)
            if parts is not None and r.labour_hours is not None:
                out.append((parts, Decimal(str(r.labour_hours))))
        return out

    @staticmethod
    def _auto(n: int, point: Decimal, p10: Decimal, p90: Decimal, gr_s1: GrS1Params) -> tuple[bool, str]:
        if n < gr_s1.min_matches:
            return False, f"{n} similar repairs (under {gr_s1.min_matches}): draft, a technician checks"
        share = (p90 - p10) / point if point > 0 else Decimal(1)
        if share > gr_s1.max_width_share:
            return False, (
                f"{n} similar repairs, but the range is {share * 100:.0f}% of the estimate "
                f"(over {gr_s1.max_width_share * 100:.0f}%): draft, a technician checks"
            )
        return True, f"{n} similar repairs, range {share * 100:.0f}% of the estimate: priced without a technician"
