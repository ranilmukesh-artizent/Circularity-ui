"""Plan 9, P9-4.5 (story SD-08): the repair estimate replayed on held-out repairs.

Every repair closed in the last weeks is estimated from the repairs closed before it, at the cards of its close day; the
figures per tool class (held-out count, MAE, coverage, share auto-priced) are computed, and a class below the bar loses
instant pricing. The expectations are worked again here from the same rows and the pack's rate cards; parts are left out of
the rows so the parts card version does not matter.

It starts and ends with the demo reset.
"""

import json
import statistics
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal, engine
from di.repositories import repair_accuracy as repo
from di.repositories import service_tickets
from di.services.modeler.tables import market_spec
from di.services.models.cost import RepairCostModel
from di.services.service_desk import accuracy
from di.services.service_desk import estimate as est
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, tool_case_facts

D = Decimal
ORG = "tool-fleet-a"
AS_OF = date(2026, 10, 7)
CUT = date(2026, 8, 12)  # AS_OF less 8 weeks


def _cents(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), ROUND_HALF_UP)


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM service_ticket"))
        conn.execute(text("DELETE FROM repair_history"))
        conn.execute(text("DELETE FROM repair_accuracy"))
        conn.execute(text("DELETE FROM job WHERE kind = 'serviceDesk.accuracy'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _history(rows: list[dict]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, NULL, "
                ":cls, 18, 'MOT', 'US', '[]'::jsonb, :hours, false, 5, :actual, 'USD', :closed, 'rephist')"
            ),
            [{"org": ORG, "cls": "CRH", "actual": 300, **r} for r in rows],
        )


def _rows(cls: str, prefix: str, n: int, start: date, step: int, actual) -> list[dict]:
    return [{"id": f"RH-{prefix}{i}", "cls": cls, "hours": 2.0 + 0.25 * (i % 3), "closed": start + timedelta(days=i * step),
             "actual": actual(i)} for i in range(n)]  # fmt: skip


def _seed() -> tuple[list[dict], list[dict]]:
    """Sixty old CRH repairs, twelve held out, one on the cut-off day and one after the day; a few DCD repairs."""
    old = _rows("CRH", "O", 60, date(2024, 1, 1), 5, lambda i: 250)
    held = _rows("CRH", "H", 12, date(2026, 9, 1), 3, lambda i: 200 + 15 * i)
    edge = [{"id": "RH-EDGE", "cls": "CRH", "hours": 2.0, "closed": CUT, "actual": 250},
            {"id": "RH-LATE", "cls": "CRH", "hours": 2.0, "closed": date(2026, 10, 8), "actual": 250}]  # fmt: skip
    dcd = _rows("DCD", "D", 8, date(2026, 9, 2), 3, lambda i: 150) + _rows("DCD", "E", 20, date(2025, 1, 1), 9, lambda i: 150)
    rows = old + held + edge + dcd
    _history(rows)
    return rows, held


def _expected(rows: list[dict], target: dict, rate: Decimal, fee: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """(point, p10, p90) of one target from the rows of its class closed before it (parts are empty: parts cost 0)."""
    prior = [r for r in rows if r["cls"] == target["cls"] and r["closed"] < target["closed"]]
    hours = [D(str(r["hours"])) for r in prior]
    point = _cents(statistics.median(hours) * rate) + _cents(fee)
    q = statistics.quantiles(sorted(h * rate + fee for h in hours), n=10, method="inclusive")
    return point, _cents(q[0]), _cents(q[8])


def _card_numbers() -> tuple[Decimal, Decimal]:
    spec = market_spec("tool_fleet")
    assert spec is not None
    return (D(str(spec.table("labour").versions[0].values["US"]["per_hour"])),
            D(str(spec.table("terms").versions[0].values["US"]["test_fee"])))  # fmt: skip


def _accuracy_rows() -> dict[str, dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM repair_accuracy WHERE as_of = :d"), {"d": AS_OF})
        return {r.model_class: dict(r._mapping) for r in rows}


# ------------------------------------------------------------------ per family
def test_sd_08_accuracy_per_family():
    rows, held = _seed()
    out = call("serviceDesk.computeAccuracy", {}, "admin")
    assert out["ok"], out
    got = _accuracy_rows()
    assert set(got) == {"CRH", "DCD"}
    crh = got["CRH"]
    assert crh["n"] == sum(1 for r in rows if r["cls"] == "CRH" and CUT < r["closed"] <= AS_OF) == 12
    assert got["DCD"]["n"] == 8
    rate, fee = _card_numbers()
    errs, inside = [], 0
    for t in held:
        point, p10, p90 = _expected(rows, t, rate, fee)
        errs.append(abs(point - D(t["actual"])))
        inside += p10 <= D(t["actual"]) <= p90
    mae = _cents(sum(errs, D(0)) / 12)
    assert crh["mae"] == mae
    assert crh["coverage"] == (D(inside) / 12).quantize(D("0.0001"), ROUND_HALF_UP)
    share = (mae / D(str(statistics.median(D(t["actual"]) for t in held)))).quantize(D("0.0001"), ROUND_HALF_UP)
    assert crh["mae_share"] == share
    assert crh["instant"] == (crh["coverage"] >= D("0.70") and crh["mae_share"] <= D("0.15"))
    assert crh["auto_share"] == 1  # 60 or more matches, a narrow range: every one would have been auto-priced


# ------------------------------------------------------------------ below the bar
def _open(number: str) -> dict:
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == number)
        c = sd.open_from_ticket(s, row, "system")
        s.commit()
    return c


def test_sd_08_family_below_bar_loses_instant():
    _history(_rows("CRH", "T", 120, date(2023, 10, 7), 5, lambda i: 300))
    line = {"serial": "CRH-46042", "model_class": "CRH", "age_months": 18, "fault_code": "MOT", "fault_text": "Runs hot",
            "cover_type": "fleet", "cover_until": "2027-06-30"}  # fmt: skip
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_accuracy (org_unit_id, as_of, model_class, n, mae, mae_share, coverage, auto_share, instant) "
                "VALUES (:o, :d, 'CRH', 40, 20.00, 0.0500, 0.5500, 0.9000, false)"
            ),
            {"o": ORG, "d": AS_OF},
        )
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES ('CS0010077', :o, 'ACC-US-0042', 'US', 'Austin', NULL, "
                "CAST(:l AS jsonb), 'Site manager', false, '2026-10-07T09:00:00+00:00', 'sdesk')"
            ),
            {"o": ORG, "l": json.dumps([line])},
        )
    tool_case_facts("CRH-46042", {"cls": "CRH"})
    e = _open("CS0010077")["serviceDesk"]["lines"][0]["estimate"]
    assert e["n"] == 120 and e["auto"] is False
    assert e["reason"] == "Instant pricing is off for this family: held-out coverage 55% is under the 70% bar"
    assert e["confidence"] == 0.55 and e["item"] is not None  # a technician checks


# ------------------------------------------------------------------ no future rows
class _Spy(RepairCostModel):
    def __init__(self) -> None:
        self.calls: list[list[date]] = []

    def estimate(self, history, key, cards, gr_s1, coverage):  # type: ignore[no-untyped-def]
        if key.model_class == "CRH":
            self.calls.append([r.closed_on for r in history])
        return super().estimate(history, key, cards, gr_s1, coverage)


def test_sd_08_no_future_rows():
    _seed()
    with SessionLocal() as s:
        cards = est._cards(s, ORG, "US", AS_OF)
        window = [r for _, r in repo.window(s, date(2023, 1, 1), AS_OF + timedelta(days=1))]
    assert cards is not None
    spy = _Spy()
    accuracy.holdout(window, lambda d, m: cards, AS_OF, 8, spy, params=est.gr_s1(), bar=accuracy.bar())
    assert len(spy.calls) == 12  # the twelve held-out CRH repairs, in the order they closed
    for i, seen in enumerate(spy.calls):  # each repair is estimated from rows closed before its own day only
        closed = date(2026, 9, 1) + timedelta(days=3 * i)
        assert max(seen) < closed and len(seen) == 61 + i  # 60 old rows, the cut-off day's, and the earlier held-out ones
    assert date(2026, 10, 8) not in {d for seen in spy.calls for d in seen}


# ------------------------------------------------------------------ the job
def test_accuracy_job_queued_daily(monkeypatch):
    for name, mod in (("ensure_subscription", "webhook"), ("enqueue_due", "sync")):
        monkeypatch.setattr(f"di.connectors.{mod}.{name}", lambda *a: [])
    monkeypatch.setattr(worker, "tick_triggers", lambda: None)
    worker.periodic()
    worker.periodic()
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM job WHERE kind = 'serviceDesk.accuracy'")).scalar()
    assert n == 1
    assert "serviceDesk.accuracy" in worker.HANDLERS
