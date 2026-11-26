"""P9-7.7 (story SD-10; registry entries I-15 and I-17): the FR market canary for the service-desk tables.

A rollout of `subject_kind 'table'` releases a market's tables (the pilot market's own rate cards and decision tables) to a share
of that market's tickets; the rest are priced from the standard quote (the pack's other market in the same currency). The flow
under it is the org's tool-fleet flow; its done replay is the precondition, as for a flow canary. Nothing here reads or writes
free text (R16): every figure of the report is code, money stays Decimal in the valuer and the tables return classes and shares.
"""

import json
from datetime import date

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import rollouts
from di.services.modeler.canary_stats import sd_measures
from di.services.modeler.rollout import Rollout, assign
from di.services.service_desk import inputs as sd_inputs
from tests import flowkit, starting
from tests.flowkit import ok
from tests.helpers import call, client, h
from tests.test_rollout import MAKER_TEXT, ORG, replay_done, shadow_flow

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM rollout"))
            s.execute(text("DELETE FROM replay_run"))
            s.execute(text("DELETE FROM replay_batch"))
            s.execute(text("DELETE FROM case_record WHERE id LIKE 'SD10-%'"))
            s.execute(text("DELETE FROM market_table WHERE version >= 90"))
            s.commit()

    clean()
    starting.reset()
    flowkit.reset_flows()
    yield
    clean()
    flowkit.reset_flows()
    starting.reset()


def table_canary(share: int = 20, region: str = "FR") -> int:
    """Customer A's tool-fleet flow with a done replay; the FR tables released to `share` % of FR tickets. Answers the flow id."""
    fid = shadow_flow("tool_fleet")
    replay_done(fid)
    body = {"subject_kind": "table", "subject_id": str(fid), "region_key": "market", "region": region, "share": share}
    out = ok(call("rollout.startCanary", body, "approver"))
    assert out["stage"] == "canary" and out["subject_kind"] == "table"
    with SessionLocal() as s:
        s.execute(text("UPDATE rollout SET salt = 'sd10-salt'"))
        s.commit()
    return int(fid)


def trow(fid: int) -> Rollout:
    with SessionLocal() as s:
        r = s.execute(
            text(
                "SELECT id, subject_kind, subject_id, candidate_ver, base_ver, stage, region_key, region, share, salt "
                "FROM rollout WHERE subject_kind = 'table' AND subject_id = :f ORDER BY id"
            ),
            {"f": str(fid)},
        ).first()
    assert r is not None
    return Rollout(*r)


def tickets(prefix: str, market: str, n: int) -> list[dict]:
    return [{"id": f"SD10-{prefix}{k:03d}", "owner": ORG, "serviceDesk": {"market": market}} for k in range(n)]


def priced(cs: list[dict]) -> list[tuple[str, str]]:
    """(market whose tables price the ticket, arm) of each ticket; the assignments are stored."""
    with SessionLocal() as s:
        out = [rollouts.table_version_for(s, c) for c in cs]
        s.commit()
    return out


def ref(fid: int, **extra: object) -> dict:
    return {"subject_kind": "table", "subject_id": str(fid)} | extra


# ---------------------------------------------------------------- the split
def test_sd_10_fr_tickets_split_20_percent():
    fid = table_canary()
    r = trow(fid)
    assert (r.region_key, r.region, r.share) == ("market", "FR", 20)
    fr = tickets("FR", "FR", 200)
    got = priced(fr)
    canary = {c["id"] for c in fr if assign(c["id"], str(fid), r.salt, "FR", r) == "canary"}
    assert {c["id"] for c, g in zip(fr, got, strict=True) if g == ("FR", "canary")} == canary
    assert all(g in (("FR", "canary"), ("DE", "control")) for g in got)  # the rest: the standard quote (DE, also EUR)
    assert 25 <= len(canary) <= 55
    assert priced(fr) == got  # sticky: the same ticket is priced the same way again


def test_sd_10_other_markets_unaffected():
    table_canary()
    for market in ("DE", "UK", "US", "AU"):
        assert all(g == (market, "out") for g in priced(tickets(market, market, 20)))
    with SessionLocal() as s:
        assert not s.execute(text("SELECT 1 FROM rollout_assignment WHERE case_id LIKE 'SD10-DE%'")).first()


def test_sd_10_no_rollout_keeps_own_tables():
    assert all(g == ("FR", "none") for g in priced(tickets("FR", "FR", 5)))


def test_sd_10_pause_and_rollback_send_new_tickets_to_standard():
    fid = table_canary()
    first = priced(tickets("A", "FR", 40))
    ok(call("rollout.pause", ref(fid, reason="Margin looks wrong in week one"), "approver"))
    assert priced(tickets("A", "FR", 40)) == first  # assigned tickets keep their tables
    assert all(g == ("DE", "none") for g in priced(tickets("B", "FR", 20)))  # new ones: the standard quote
    ok(call("rollout.rollback", ref(fid, reason="Pilot ended, tables rewritten"), "approver"))
    assert all(g == ("DE", "none") for g in priced(tickets("C", "FR", 20)))


# ---------------------------------------------------------------- the tables a ticket is priced from
def test_sd_10_inputs_cite_the_arms_table_version():
    fid = table_canary(share=50)
    cs = tickets("G", "FR", 40)
    ln = {"n": 1, "serial": "CRH-1", "model_class": "CRH", "age_months": 18, "cover_type": "fleet", "life_used_pct": 60}
    for c in cs:
        c["serviceDesk"] |= {"lines": [ln]}
    by_arm: dict[str, dict] = {}
    with SessionLocal() as s:
        for c in cs:
            arm = rollouts.table_version_for(s, c)[1]
            got = sd_inputs.gather(s, c, date(2026, 10, 7))
            assert got is not None
            by_arm.setdefault(arm, got)
        s.commit()
    assert trow(fid).share == 50 and set(by_arm) == {"canary", "control"}
    can, ctl = by_arm["canary"], by_arm["control"]
    assert can["tables"] == {"market": "FR", "arm": "canary", "label": "Pilot FR (new tables)"}
    assert ctl["tables"] == {"market": "DE", "arm": "control", "label": "Standard quote"}
    assert can["lines"][0]["credit"]["ref"].startswith("FR ") and ctl["lines"][0]["credit"]["ref"].startswith("DE ")
    assert can["currency"] == ctl["currency"] == "EUR"


# ---------------------------------------------------------------- the guards
def test_sd_10_needs_replay():
    fid = shadow_flow("tool_fleet")
    r = call("rollout.startCanary", ref(fid, region="FR", share=20), "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    assert r["error"]["message"] == "Run a replay of the service desk flow before a table canary (Modeler, Replay)."


def test_sd_10_a_table_maker_cannot_start_it():
    fid = shadow_flow("tool_fleet")
    replay_done(fid)
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO market_table (org_unit_id, pack, flow, market, name, kind, version, status, valid_from, currency, "
                "body, created_by) VALUES (NULL, 'tool_fleet', 'service_desk', 'FR', 'labour', 'rate_card', 91, 'draft', "
                "'2027-01-01', 'EUR', CAST(:b AS jsonb), 'approver')"
            ),
            {"b": json.dumps({"values": {"hour": 50}})},
        )
        s.commit()
    r = call("rollout.startCanary", ref(fid, region="FR", share=20), "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and r["error"]["message"] == MAKER_TEXT


def test_sd_10_unknown_market_is_refused():
    fid = shadow_flow("tool_fleet")
    replay_done(fid)
    r = call("rollout.startCanary", ref(fid, region="XX", share=20), "approver")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"


def test_sd_10_widen_is_person_only():
    fid = table_canary()
    from di.services.agents.forbidden import FORBIDDEN_ACTIONS

    assert "rollout.widen".startswith(FORBIDDEN_ACTIONS)
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/rollout.widen", json=ref(fid, share=40), headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    assert trow(fid).share == 20
    out = ok(call("rollout.widen", ref(fid, share=40), "approver"))
    assert out["stage"] == "canary" and trow(fid).share == 40


def test_sd_10_tenant_boundary():
    fid = table_canary()
    r = call("rollout.report", ref(fid), "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"


# ---------------------------------------------------------------- the report
def seed(rid: int, arm: str, shapes: list[tuple[str, float, float | None, int]]) -> None:
    """One decided ticket per shape (best option, its expected margin, its take-up, its days) in the arm."""
    with SessionLocal() as s:
        for n, (best, margin, take, days) in enumerate(shapes):
            cid = f"SD10-{arm[:2].upper()}{n:03d}"
            opt = {"k": best, "eligible": True, "expected_margin": margin, "take_up": take, "days": days}
            data = {
                "approval": {"by": "t"}, "chosen": {"net": margin},
                "serviceDesk": {"market": "FR", "lines": [{"n": 1, "best": best, "options": [opt]}]},
            }  # fmt: skip
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, :o, 'Hub', 'closed', CAST(:d AS jsonb))"
                ),
                {"i": cid, "o": ORG, "d": json.dumps(data)},
            )
            s.execute(
                text("INSERT INTO rollout_assignment (rollout_id, case_id, arm, ver) VALUES (:r, :c, :a, 'FR')"),
                {"r": rid, "c": cid, "a": arm},
            )
        s.commit()


def test_sd_10_report_compares_arms():
    fid = table_canary()
    rid = trow(fid).id
    seed(rid, "canary", [("upgrade", 120.0, 0.4, 3)] * 6 + [("fix", 60.0, None, 5)] * 4)
    seed(rid, "control", [("upgrade", 90.0, 0.3, 3)] * 2 + [("fix", 50.0, None, 6)] * 6 + [("swap", 40.0, None, 2)] * 2)
    r = ok(call("rollout.report", ref(fid), "approver"))
    assert r["labels"] == {"canary": "Canary", "control": "Standard quote"}
    can, ctl = r["canary"]["sd"], r["control"]["sd"]
    assert r["canary"]["n"] == 10 and r["control"]["n"] == 10
    assert can["option_mix"] == {"fix": 0.4, "swap": 0.0, "upgrade": 0.6}
    assert ctl["option_mix"] == {"fix": 0.6, "swap": 0.2, "upgrade": 0.2}
    assert can["margin_per_ticket"] == pytest.approx(96.0) and ctl["margin_per_ticket"] == pytest.approx(56.0)
    assert can["upgrade_take_up"] == pytest.approx(0.4) and ctl["upgrade_take_up"] == pytest.approx(0.3)
    assert can["days_to_option"] == pytest.approx(3.8) and ctl["days_to_option"] == pytest.approx(4.6)
    assert r["band"]["diff"] == pytest.approx(40.0)


def test_sd_10_measures_are_pure_and_empty_safe():
    assert sd_measures([]) == {
        "tickets": 0, "option_mix": {"fix": 0.0, "swap": 0.0, "upgrade": 0.0}, "margin_per_ticket": None,
        "upgrade_take_up": None, "days_to_option": None,
    }  # fmt: skip
    one = sd_measures([{"lines": [{"best": "fix", "margin": 10.0, "take_up": None, "days": 4}, {"best": None}]}])
    assert one["option_mix"]["fix"] == 1.0 and one["margin_per_ticket"] == 10.0 and one["days_to_option"] == 4.0
