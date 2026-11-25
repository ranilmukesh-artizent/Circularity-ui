"""Plan 9, P9-6.8 (story DV-05): the payout of a received device is adjusted by the pack's table `payout_rules` (US, from
`valuer.params.market_tables` of the device pack, I-15) when the lab's grading and diagnostics differ from the quote. A gap of
at most `max_auto_gap` (guardrail GR-D11, 10 percent) is adjusted at once, recorded on the case and sent to the trade-in
platform as a `payout` instruction; a bigger one waits for Customer care, who decide it with `payout.decide` (a person's: no
agent, never the person who prepared the payout, never another tenant). Nothing here writes language, so there is no model
call: every figure and word comes from the table's result and the quote.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories import market_tables as tables_repo
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import store
from di.services.device import intake as device_intake
from di.services.device import payout
from di.services.instructions import queue, writers
from tests import starting
from tests.device_registry import seed_registry
from tests.helpers import call, client, h

ORG = "Customer A"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM device_tradein"))
        conn.execute(text("DELETE FROM device_price_point"))
        conn.execute(text("DELETE FROM instruction WHERE kind = 'payout'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _imei(n: int) -> str:
    return f"3599900000{n:05d}"


def _open(n: int = 1, *, declared: str = "B", graded: str | None = "B", battery: float | None = 84, fails: list | None = None,
          photos: tuple[str, ...] = ("PH-1", "PH-2"), org: str = ORG) -> dict[str, Any]:  # fmt: skip
    """Land a trade-in (quote $410), the lab's grading and diagnostics, and a clear registry check and wipe; open its case."""
    when = (clock.now() - timedelta(days=5)).isoformat()
    imei = _imei(n)
    seed_registry(imei)
    facts = {"battery_health_pct": battery, "functional_fails": fails if fails is not None else [], "photo_refs": list(photos)}
    if graded:
        facts["cosmetic_grade"] = graded
    with SessionLocal() as s:
        canonical.apply(s, "dvlab", [Fact("condition", f"IMEI:{imei}", k, v) for k, v in facts.items() if v is not None])
        lab.land_tradein(
            s,
            {
                "tradeInId": f"TI-{n:05d}", "imei": imei,
                "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
                "quote": {"declaredGrade": declared, "amount": 410, "currency": "USD", "quotedAt": when},
                "partner": "P01", "batchId": None, "bulk": False, "receivedAt": when, "payoutAmount": 410,
            },
            org,
        )  # fmt: skip
        s.commit()
    with SessionLocal() as s:
        (cid,) = device_intake.open_pending(s, org)
        s.commit()
        c = store.get(s, cid)
    assert c is not None
    return c


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _instructions(cid: str) -> list[dict]:
    with SessionLocal() as s:
        return [
            dict(r)
            for r in s.execute(text("SELECT * FROM instruction WHERE case_id = :c AND kind = 'payout'"), {"c": cid}).mappings()
        ]


@pytest.fixture
def sending(monkeypatch):
    """The suite sends no instructions; a payout test that looks at the queued row switches sending on."""
    monkeypatch.setattr(queue, "enabled", lambda: True)


def test_dv_05_payout_within_10_percent(sending):
    c = _open()
    p = c["payout"]
    assert (p["status"], p["quote"], p["adjusted"], p["gap_pct"]) == ("adjusted", 410.0, 385.4, -0.06)
    assert p["reason"] == "Battery health 80–84%" and p["table"] == "US payout rules v1" and p["auto"] is True
    with SessionLocal() as s:
        log = s.execute(
            text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id DESC"), {"c": c["id"]}
        ).all()
    line = "Payout adjusted −6% ($410 → $385.40): Battery health 80–84% (US payout rules v1)"
    assert (line, "system") in [tuple(r) for r in log]
    (ins,) = _instructions(c["id"])
    assert (ins["kind"], ins["system"], ins["idem_key"]) == ("payout", "dvlab", f"PAYOUT.{c['id']}.38540")
    page = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]["payout"]
    assert (page["status"], page["adjusted"], page["gapPct"], page["table"]) == ("adjusted", 385.4, -0.06, "US payout rules v1")


def test_dv_05_same_grade_good_battery_is_as_quoted(sending):
    c = _open(battery=95)
    assert (c["payout"]["status"], c["payout"]["adjusted"], c["payout"]["reason"]) == ("adjusted", 410.0, "As quoted")


def test_dv_05_gap_over_10_waits_for_customer_care_with_photos():
    c = _open(declared="A", graded="C")
    p = c["payout"]
    assert (p["status"], p["gap_pct"], p["adjusted"], p["auto"]) == ("waiting", -0.3, 287.0, False)
    assert p["reason"] == "Graded two or more grades below the quote" and p["photos"] == ["PH-1", "PH-2"]
    with SessionLocal() as s:
        q = "SELECT type, owner_role, status, cause, action FROM work_item WHERE case_id = :c AND type = 'payout_gap'"
        item = s.execute(text(q), {"c": c["id"]}).mappings().one()
    assert (item["owner_role"], item["status"]) == ("Planner", "open") and item["action"].startswith("Customer care:")
    assert "PH-1" in item["cause"] and "-30%" in item["cause"].replace("−", "-")
    assert _instructions(c["id"]) == []  # nothing is sent until a person decides


def test_dv_05_a_functional_fail_is_20_percent_and_waits():
    c = _open(fails=["camera"])
    assert (c["payout"]["status"], c["payout"]["gap_pct"], c["payout"]["reason"]) == ("waiting", -0.2, "Functional test failed")


def test_dv_05_no_payout_until_the_lab_has_graded_and_read_the_battery():
    assert _open(graded=None).get("payout") is None
    assert _open(2, battery=None).get("payout") is None


def test_dv_05_the_table_is_pack_data_and_rule_values_come_from_it():
    with SessionLocal() as s:
        tables_repo.ensure_seeded(s, "device")
        row = tables_repo.effective(s, None, "device", "returns", "US", "payout_rules", clock.now().date())
        s.commit()
    assert row is not None and row.kind == "decision_table" and row.version == 1
    cases = [
        (("B", "B", 84, 0), (-0.06, "Battery health 80–84%")), (("B", "B", 70, 0), (-0.12, "Battery health under 80%")),
        (("A", "B", 99, 0), (-0.15, "Graded one grade below the quote")),
        (("A", "D", 99, 0), (-0.3, "Graded two or more grades below the quote")),
        (("C", "C", 90, 2), (-0.2, "Functional test failed")), (("C", "C", 90, 0), (0.0, "As quoted")),
    ]  # fmt: skip
    for (declared, actual, battery, fails), (pct, reason) in cases:
        got = payout.evaluate(
            row, {"declared_grade": declared, "actual_grade": actual, "battery_pct": battery, "functional_fails": fails}
        )
        assert (got.outputs["adjust_pct"], got.outputs["reason"]) == (pct, reason)


def test_dv_05_assess_payout_is_computed_from_the_table_result():
    got = payout.assess_payout(
        {"amount": 410, "currency": "USD"}, {"adjust_pct": -0.06, "reason": "r"}, max_auto_gap=Decimal("0.10")
    )
    assert (got.adjusted, got.gap_pct, got.auto) == (Decimal("385.40"), Decimal("-0.06"), True)
    edge = payout.assess_payout(
        {"amount": 410, "currency": "USD"}, {"adjust_pct": -0.10, "reason": "r"}, max_auto_gap=Decimal("0.10")
    )
    assert edge.auto is True  # exactly the limit is still automatic
    over = payout.assess_payout(
        {"amount": 410, "currency": "USD"}, {"adjust_pct": -0.15, "reason": "r"}, max_auto_gap=Decimal("0.10")
    )
    assert (over.auto, over.adjusted) == (False, Decimal("348.50"))


def test_dv_05_the_limit_is_guardrail_gr_d11():
    from di.services.modeler.pack import load_pack

    g = next(x for x in load_pack("device").guardrails if x.id == "GR-D11")
    assert (g.param.field, g.param.value, g.owner) == ("max_auto_gap", 0.1, "Customer care")


def test_dv_05_the_writer_patches_the_trade_in_with_the_amount(monkeypatch, sending):
    c = _open()
    (ins,) = _instructions(c["id"])
    sent: list[tuple] = []

    class Fake:
        def request(self, method, path, **kw):
            sent.append((method, path, kw))

        def close(self):
            pass

    monkeypatch.setattr(writers, "client", lambda s, source: Fake())
    with SessionLocal() as s:
        out = writers.WRITERS["payout"](s, ins, store.get(s, c["id"]), {})
    assert sent == [("PATCH", "/tradeins/TI-00001", {"json": {"payoutAmount": 385.4}})]
    assert out.doc_ref == "TI-00001"


# ---------------------------------------------------------------- payout.decide (R21)
def _decide(cid: str, user: str = "planner.a", amount: float = 300, reason: str = "Photos show the back glass cracked") -> dict:
    return call("payout.decide", {"case_id": cid, "payout": amount, "reason": reason}, user)


def test_payout_decide_by_person(sending):
    c = _open(declared="A", graded="C")
    r = _decide(c["id"])
    assert r["ok"] is True, r
    p = _get(c["id"])["payout"]
    assert (p["status"], p["adjusted"], p["decided"]["by"], p["decided"]["reason"]) == (
        "decided",
        300.0,
        "planner-a",
        "Photos show the back glass cracked",
    )
    (ins,) = _instructions(c["id"])
    assert ins["idem_key"] == f"PAYOUT.{c['id']}.30000"
    with SessionLocal() as s:
        q = "SELECT count(*) FROM work_item WHERE case_id = :c AND type = 'payout_gap' AND status = 'open'"
        open_items = s.execute(text(q), {"c": c["id"]}).scalar()
    assert open_items == 0
    again = _decide(c["id"], amount=290)
    assert again["ok"] is False and again["error"]["code"] == "conflict"


def test_payout_decide_only_on_a_waiting_payout():
    c = _open()  # adjusted within the limit: nothing to decide
    assert _decide(c["id"])["error"]["code"] == "conflict"


def test_payout_decide_above_the_quote_is_a_validation_error():
    c = _open(declared="A", graded="C")
    r = _decide(c["id"], amount=410.01)
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert _decide(c["id"], amount=-1)["error"]["code"] == "validation_error"
    assert _get(c["id"])["payout"]["status"] == "waiting"


def test_payout_decide_agent_refused():
    assert "payout.decide" in FORBIDDEN_ACTIONS and forbidden("payout.decide")
    c = _open(declared="A", graded="C")
    r = client.post(
        "/api/actions/payout.decide", json={"case_id": c["id"], "payout": 300, "reason": "An agent decides this one"},
        headers=h("planner.a") | {"X-Circularity-Preparer": "gap", "X-Circularity-Confirmed": "true"},
    ).json()  # fmt: skip
    assert r["ok"] is False
    assert _get(c["id"])["payout"]["status"] == "waiting"


def test_payout_decide_tenant_boundary():
    c = _open(declared="A", graded="C")
    r = _decide(c["id"], user="planner.b")  # a planner of another tenant
    assert r["ok"] is False and r["error"]["code"] in ("tenant_boundary", "forbidden", "out_of_scope")
    assert _get(c["id"])["payout"]["status"] == "waiting"


def test_payout_decide_needs_the_permission():
    c = _open(declared="A", graded="C")
    r = _decide(c["id"], user="finance")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"


def test_payout_decide_maker_is_not_checker():
    """A payout a person prepared (`prepared_by`) is decided by someone else."""
    c = _open(declared="A", graded="C")
    with SessionLocal() as s:
        row = store.get(s, c["id"], for_update=True)
        row["payout"]["prepared_by"] = "planner-a"
        store.save(s, row)
        s.commit()
    own = _decide(c["id"], user="planner.a")
    assert own["ok"] is False and own["error"]["code"] == "conflict" and "cannot decide" in own["error"]["message"]
    assert _decide(c["id"], user="admin")["ok"] is True
