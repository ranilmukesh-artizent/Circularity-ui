"""Plan 9, P9-10.17 (stories TN-21, TN-22): the telecom close records the new spend avoided, and two worked questions.

`close_case` of an approved redeploy keeps, on the case, the purchase price the unit replaced (the catalogue price of its model),
the days from removal to the inventory's install confirmation and whether the unit was reused. `wq_tn_1` (power units idle in
one region while another buys new) and `wq_tn_2` (idle spares by region, count and value) are answered from the canonical store
by `analytics.answer`, within the scope's org units. Records are written through the adapters' own `map`; no source-sim.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services import questions  # noqa: F401  (registers the pack questions)
from di.services.canonical import store as canonical
from di.services.cases import close_telecom_network as close
from di.services.cases import store as case_store
from di.services.device import analytics
from tests import starting
from tests.test_tn_cross_region import _clean as _clean_xr
from tests.test_tn_cross_region import _idle, _req, _write

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG, OTHER = "Customer A", "Customer B"
CASE = "RT-TNCLOSE1"


def _clean() -> None:
    _clean_xr()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE key LIKE '%SN-TNC-%' OR (model = 'market' AND key LIKE '%:%-%')"))
        conn.execute(text("DELETE FROM canonical WHERE key LIKE '%SN-TNC-%'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'market' AND key IN (:a, :b)"),
                     {"a": f"{ORG}:PSU-48", "b": f"{ORG}:RRU-4410"})  # fmt: skip
        conn.execute(text("DELETE FROM case_record WHERE id = :c"), {"c": CASE})
        conn.execute(text("DELETE FROM instruction WHERE case_id = :c"), {"c": CASE})


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


def _ask(qid: str, orgs: set[str] | None = None) -> analytics.Answer:
    with SessionLocal() as s:
        return analytics.answer(s, qid, analytics.Scope(frozenset(orgs)) if orgs else None, clock.now().date())


def _open_case(route: str = "redeploy", acknowledged: bool = True) -> None:
    """TN-S1: SN-TNC-0001 (RRU-4410), removed 10 Nov, approved for `route`; the inventory confirmed the transfer on 17 Nov."""
    with SessionLocal() as s:
        canonical.apply(s, "tn_decom", ADAPTERS["tn_decom"].map(Record("removal_jobs", "J1:SN-TNC-0001", {
            "jobId": "J1", "siteId": "SITE-1", "removedAt": "2026-11-10", "programme": "P", "serial": "SN-TNC-0001",
            "model": "RRU-4410", "org_unit_id": ORG})))  # fmt: skip
        canonical.apply(s, "tn_spares", ADAPTERS["tn_spares"].map(Record("catalogue", "x", {
            "model": "RRU-4410", "newPrice": 9800, "generation": "4", "org_unit_id": ORG})))  # fmt: skip
        case_store.insert_new(s, {
            "id": CASE, "template": "telecom_network", "owner": "planner.a", "location": "North", "stage": "approved",
            "assetId": f"{ORG}:SN-TNC-0001", "network": {"model": "RRU-4410"}, "routes": [], "recommendation": None,
            "chosen": {"id": route, "dest": {"site": "SITE-N-014", "region": "North"}},
            "exec": {"approved_by": "approver"},
        })  # fmt: skip
        if acknowledged:
            s.execute(text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, status, acknowledged_at) "
                "VALUES (:c, 'AP-TNC', 0, 'site_transfer', 'tn_inv', 'tnc-1', 'acknowledged', :at)"),
                {"c": CASE, "at": datetime(2026, 11, 17, 10, tzinfo=UTC)})  # fmt: skip
        s.commit()


def test_tn_22_close_records_new_spend_avoided():
    _open_case()
    with SessionLocal() as s:
        r = close.close_case(s, CASE)
        s.commit()
        c = case_store.get(s, CASE)
    assert r.status == "closed"
    assert r.new_spend_avoided == 9800 and r.days_to_redeploy == 7 and r.reused is True
    assert c is not None and c["close"]["telecom"] == {
        "new_spend_avoided": 9800.0,
        "purchase_price": 9800.0,
        "days_to_redeploy": 7,
        "reused": True,
        "route": "redeploy",
    }


def test_tn_22_close_waits_for_the_install_confirmation_and_leaves_other_cases():
    _open_case(acknowledged=False)
    with SessionLocal() as s:
        assert close.close_case(s, CASE).status == "waiting_for_install"
        assert close.close_case(s, "RT-1048").status == "not_applicable"


def test_tn_22_a_recycled_unit_is_not_reused():
    _open_case(route="recycle")
    with SessionLocal() as s:
        r = close.close_case(s, CASE)
    assert r.status == "closed" and r.reused is False and r.new_spend_avoided == 0


def test_tn_22_power_unit_question_answered():
    _idle(4, "North")
    _req("West", "PSU-48", "PR-3301", 3)
    a = _ask("wq_tn_1", {ORG})
    assert a.sentence == (
        "4 returned PSU-48 units sat idle in North while West raised 1 purchase requisition: spares targets are set per "
        "region, so one region's surplus is never offered to another."
    )
    assert len(a.examples) == 3 and all(e["region"] == "North" and e["req_id"] == "PR-3301" for e in a.examples)


def test_tn_22_power_unit_question_stays_in_scope():
    _idle(4, "North")
    _req("West", "PSU-48", "PR-3301", 3)
    assert "No idle" in _ask("wq_tn_1", {OTHER}).sentence


def test_tn_21_idle_spares_by_region():
    _idle(3, "North")
    _idle(1, "South", tag="B")
    _write("catalogue", {"model": "PSU-48", "newPrice": 1000, "generation": "2"})
    a = _ask("wq_tn_2", {ORG})
    pts = a.chart["series"][0]["points"]
    assert [(p["x"], p["y"]) for p in pts] == [("North", 3), ("South", 1)]
    assert a.sentence.startswith("North holds the most idle spares: 3 units worth 3,000")
    assert a.examples and a.examples[0]["region"] == "North"
