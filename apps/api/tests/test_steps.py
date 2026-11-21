"""The workflow step implementations (plan 6, task C4): di/workflow/steps.

Pure tests: records in, records out, with the settings keys of di/workflow/blocks.py. Only x_fx reads the database
(the dated `fx_rate` table, migration 0017); its test adds a rate inside the test's own transaction and rolls it back.
The sinks run with dry=True, so nothing is written anywhere.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.connectors.generic import to_usd
from di.workflow.blocks import default_cfg
from di.workflow.steps import STEPS, ExprError, Rec, Reject, StepCtx, StepResult, compile_expr

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
C4 = (
    "x_gw", "x_evt", "x_file", "x_val", "x_late", "x_fx", "x_utc", "x_units", "x_lookup", "x_filter", "x_expr",
    "x_agg", "x_join", "x_ident", "x_enrich", "x_branch", "x_wait", "x_loop", "x_call", "x_err", "x_audit", "x_pub",
)  # fmt: skip


def ctx(s=None, dry=True, logs=None):
    return StepCtx(
        s=s, run_id=None, wf={"id": "WF-T"}, node={"id": "n1"}, source_id="crm", now=NOW, dry=dry,
        log=(logs.append if logs is not None else None),
    )  # fmt: skip


def rec(ext_id, resource="orders", **data):
    return Rec(ext_id, resource, data, None, {})


def run(ref, recs, cfg=None, c=None) -> StepResult:
    return STEPS[ref](recs, cfg or {}, c or ctx())


# ------------------------------------------------------------------ catalogue
def test_every_c4_block_has_a_step():
    assert set(C4) <= set(STEPS)


@pytest.mark.parametrize("ref", C4)
def test_the_default_settings_pass_records_through(ref):
    """The catalogue's defaults reproduce today's behaviour: synced records (no file, no arrival time) go on."""
    recs = [rec("1", qty=1, updated_at="2026-11-20T10:00:00Z"), rec("2", qty=2, updated_at="2026-11-20T11:00:00Z")]
    res = run(ref, recs, default_cfg(ref))
    if ref == "x_err":
        assert res.out == [] and res.side["held"] == 2
    else:
        assert [r.ext_id for r in res.out] == ["1", "2"] and not res.rejected
        assert [r.data["qty"] for r in res.out] == [1, 2]


def test_steps_do_not_mutate_their_input():
    r = rec("1", amount=1002000, currency="INR", date="2026-10-10")
    run("x_fx", [r])
    assert r.data == {"amount": 1002000, "currency": "INR", "date": "2026-10-10"} and r.meta == {}


# ------------------------------------------------------------------ ingest
def test_x_gw_passes_through_with_its_limits():
    res = run("x_gw", [rec("1"), rec("2")], {"rate_limit_per_min": 600, "timeout_s": 30})
    assert [r.ext_id for r in res.out] == ["1", "2"] and not res.rejected
    assert res.out[0].meta["gw"] == {"rate_limit": 600, "timeout_s": 30}


def test_x_evt_orders_by_key_and_drops_exact_replays():
    a, b, a2 = rec("A", seq=2), rec("B", seq=1), rec("A", seq=2)
    res = run("x_evt", [a, b, a2], {"ordering_key": "seq"})
    assert [r.ext_id for r in res.out] == ["B", "A"]
    assert res.side["duplicates"] == 1


def test_x_file_checks_the_checksum():
    good = rec("1", qty=1)
    res = run("x_file", [good], {"path": "/in/a.csv"})
    digest = res.out[0].meta["file"]["checksum"]
    bad = Rec("2", "orders", {"qty": 2}, None, {"checksum": digest})  # the digest of another payload
    res = run("x_file", [good, bad], {"path": "/in/a.csv", "checksum_required": True})
    assert [r.ext_id for r in res.out] == ["1"]
    assert res.rejected[0].rule == "checksum"
    assert len(run("x_file", [good, bad], {"checksum_required": False}).out) == 2
    from_file = Rec("3", "orders", {"qty": 3}, None, {"file": {"name": "a.csv"}})
    res = run("x_file", [from_file], {"checksum_required": True})
    assert res.rejected[0].rule == "checksum" and "no checksum" in res.rejected[0].reason


# ------------------------------------------------------------------ quality
def test_x_val_rejects_per_rule_with_the_rule_name():
    rules = [
        {"field": "id", "check": "present"},
        {"field": "qty", "check": "type", "arg": "number"},
        {"field": "code", "check": "regex", "arg": r"INS-\d{5}"},
        {"field": "qty", "check": "range", "arg": "1..100"},
        {"field": "grade", "check": "in", "arg": "A,B,C"},
    ]
    ok = {"id": "x", "qty": 5, "code": "INS-12345", "grade": "B"}
    cases = {
        "present": {**ok, "id": ""},
        "type": {**ok, "qty": "five"},
        "regex": {**ok, "code": "INS-12"},
        "range": {**ok, "qty": 500},
        "in": {**ok, "grade": "Z"},
    }
    recs = [rec("ok", **ok)] + [rec(name, **d) for name, d in cases.items()]
    res = run("x_val", recs, {"rules": rules})
    assert [r.ext_id for r in res.out] == ["ok"]
    assert {j.rec.ext_id: j.rule for j in res.rejected} == {name: name for name in cases}
    j = next(j for j in res.rejected if j.rule == "range")
    assert isinstance(j, Reject) and j.field == "qty" and j.value == 500 and "1..100" in j.reason


def test_x_val_required_fields_and_comparison_ranges():
    res = run("x_val", [rec("1", qty=0), rec("2", qty=3), rec("3")], {
        "required": ["qty"], "rules": [{"field": "qty", "check": "range", "arg": ">0"}], "on_failure": "hold",
    })  # fmt: skip
    assert [r.ext_id for r in res.out] == ["2"]
    assert {(j.rec.ext_id, j.rule) for j in res.rejected} == {("1", "range"), ("3", "present")}
    assert res.side["on_failure"] == "hold"


def test_x_late_keeps_the_newest_per_key_and_drops_the_rest():
    recs = [
        rec("1", opportunity_id="O1", updated_at="2026-11-21T10:00:00Z", v=1),
        rec("2", opportunity_id="O1", updated_at="2026-11-21T11:00:00Z", v=2),
        rec("3", opportunity_id="O2", updated_at="2026-11-21T09:00:00Z", v=3),
        rec("4", opportunity_id="O1", updated_at="2026-11-21T10:30:00+00:00", v=4),
    ]
    res = run("x_late", recs, {"keys": ["opportunity_id"], "newest_by": "updated_at"})
    assert sorted(r.data["v"] for r in res.out) == [2, 3]
    assert res.side["dropped"] == 2 and not res.rejected


def test_x_late_window_rejects_too_late_events():
    on_time = Rec("1", "ev", {"k": "a", "t": "2026-11-21T11:30:00Z"}, None, {"received_at": "2026-11-21T11:40:00Z"})
    late = Rec("2", "ev", {"k": "b", "t": "2026-11-20T11:30:00Z"}, None, {"received_at": "2026-11-21T11:40:00Z"})
    synced = rec("3", "ev", k="c", t="2026-01-01T00:00:00Z")  # read by a sync: no arrival time, never late
    res = run("x_late", [on_time, late, synced], {"keys": ["k"], "newest_by": "t", "late_window_min": 60})
    assert [r.ext_id for r in res.out] == ["1", "3"] and res.rejected[0].rule == "late_window"


def test_x_ident_matches_inside_one_tenant_only():
    recs = [
        rec("a", tenant="CUSTOMER_A", serial="S1", tag=None),
        rec("b", tenant="CUSTOMER_A", serial=None, tag="T9"),
        rec("c", tenant="CUSTOMER_A", serial="S1", tag="T9"),
        rec("d", tenant="CUSTOMER_B", serial="S1", tag=None),
    ]
    res = run("x_ident", recs, {"keys": ["serial", "tag"]})
    ids = {r.ext_id: r.data["identity"] for r in res.out}
    assert ids["a"] == ids["b"] == ids["c"]
    assert ids["d"] != ids["a"]


# ------------------------------------------------------------------ transform
def test_x_fx_converts_at_the_dated_rate_and_records_it(session):
    session.execute(text("INSERT INTO fx_rate (date, currency, usd_rate) VALUES ('2026-11-01', 'INR', 84.0)"))
    try:
        c = ctx(s=session)
        old = rec("old", amount=1002000, currency="INR", date="2026-10-10")
        new = rec("new", amount=1002000, currency="INR", date="2026-11-05")
        usd = rec("usd", amount=10, currency="USD", date="2026-11-05")
        res = run("x_fx", [old, new, usd], {"currency": "USD"}, c)
        by = {r.ext_id: r for r in res.out}
        assert by["old"].data["amount"] == to_usd(1002000, "INR") == 12000.0
        assert by["old"].meta["fx"]["amount"] == {
            "from": "INR", "to": "USD", "rate": 83.5, "rate_date": "2026-10-06", "source_value": 1002000,
        }  # fmt: skip
        assert by["new"].data["amount"] == round(1002000 / 84.0, 2)
        assert by["new"].meta["fx"]["amount"]["rate_date"] == "2026-11-01"
        assert by["new"].data["currency"] == "USD" and by["usd"].data["amount"] == 10
        # rate date "run": the run's date (21 Nov) picks the newest rate
        res = run("x_fx", [old], {"currency": "EUR", "rate_date": "run"}, c)
        assert res.out[0].data["amount"] == round(1002000 / 84.0 * 0.92, 2)
        assert res.out[0].data["currency"] == "EUR"
        # a currency without a rate is rejected, never guessed
        res = run("x_fx", [rec("x", amount=1, currency="XYZ", date="2026-11-05")], {}, c)
        assert res.rejected[0].rule == "fx" and "XYZ" in res.rejected[0].reason
    finally:
        session.rollback()


def test_fx_rate_seed_matches_the_fixed_rates(session):
    rows = dict(session.execute(text("SELECT currency, usd_rate FROM fx_rate WHERE date = '2026-10-06'")).all())
    assert {k: float(v) for k, v in rows.items()} == {"USD": 1.0, "INR": 83.5, "EUR": 0.92}


def test_x_utc_normalises_local_times():
    res = run("x_utc", [rec("1", at="2026-10-05T15:41:00", end="2026-10-05T10:11:00-04:00")],
              {"fields": ["at", "end"], "source_zone": "+05:30"})  # fmt: skip
    r = res.out[0]
    assert r.data["at"] == "2026-10-05T10:11:00Z" and r.data["end"] == "2026-10-05T14:11:00Z"
    assert r.meta["source"]["at"] == "2026-10-05T15:41:00"


def test_x_units_converts_and_keeps_the_source_value():
    res = run("x_units", [rec("1", power=7500, power_unit="W", life="36 months"), rec("2", power=5)],
              {"units": {"power": "kW", "life": "years"}})  # fmt: skip
    r = res.out[0]
    assert r.data["power"] == 7.5 and r.data["life"] == 3.0 and r.meta["source"]["power"] == 7500
    assert res.rejected[0].rec.ext_id == "2" and res.rejected[0].rule == "units"
    res = run("x_units", [rec("1", power=55000)], {"units": [{"field": "power", "from": "W", "to": "kW"}]})
    assert res.out[0].data["power"] == 55


def test_x_lookup_maps_codes_and_rejects_unknown_ones():
    res = run("x_lookup", [rec("1", grade="Grade B"), rec("2", grade="Grade Q")], {"tables": {"grade": "grade"}})
    assert res.out[0].data["grade"] == "B" and res.out[0].meta["source"]["grade"] == "Grade B"
    assert res.rejected[0].rec.ext_id == "2" and res.rejected[0].rule == "lookup"
    res = run("x_lookup", [rec("1", plant="1030")], {"tables": {"plant": "location"}})
    assert res.out[0].data["plant"] == "Site 3"


def test_x_filter_keeps_matches_and_counts_the_rest():
    recs = [rec("1", qty=5, status="open"), rec("2", qty=0, status="open"), rec("3", qty=9, status="closed")]
    cond = [{"field": "qty", "check": "range", "arg": ">0"}, {"field": "status", "check": "in", "arg": "open"}]
    res = run("x_filter", recs, {"condition": cond})
    assert [r.ext_id for r in res.out] == ["1"] and res.side["filtered"] == 2 and not res.rejected
    res = run("x_filter", recs, {"condition": "qty > 0 and status == 'closed'"})
    assert [r.ext_id for r in res.out] == ["3"]
    assert len(run("x_filter", recs, {}).out) == 3


def test_x_expr_computes_a_derived_field():
    res = run("x_expr", [rec("1", qty=4, price=2.5, fee=1, line={"tax": 0.5})],
              {"target": "total", "expression": "qty * price + fee - line.tax"})  # fmt: skip
    assert res.out[0].data["total"] == 10.5
    assert res.out[0].meta["expr"]["total"] == "qty * price + fee - line.tax"
    assert run("x_expr", [rec("1", a=1, b=0)], {"target": "c", "expression": "a / b"}).out[0].data["c"] is None


@pytest.mark.parametrize("src", [
    "__import__('os')", "open('x')", "a.b()", "a[0]", "a ** 2", "a; b", "lambda: 1", "a if b else c",
    "x = 1", "a @ b", "`a`", "a.__class__", "a % 2", "{1: 2}", "1 +", "", "(a",
])  # fmt: skip
def test_x_expr_refuses_anything_outside_the_grammar(src):
    with pytest.raises(ExprError):
        compile_expr(src)


def test_expression_grammar():
    assert compile_expr("(1 + 2) * -3")(rec("1")) == -9
    assert compile_expr("a >= 2 and not b == 'x' or c != null")(rec("1", a=3, b="y", c=None)) is True
    assert compile_expr("missing + 1")(rec("1")) is None
    assert compile_expr("qty == 5")(rec("1", qty="5")) is True


def test_x_agg_groups_and_totals():
    recs = [rec("1", asset="A", parts=2, cost=10), rec("2", asset="A", parts=3, cost=5), rec("3", asset="B", parts=1, cost=7)]
    res = run("x_agg", recs, {"group_by": ["asset"], "totals": ["parts", {"field": "cost", "fn": "max", "as": "max_cost"}]})
    by = {r.data["asset"]: r.data for r in res.out}
    assert by == {
        "A": {"asset": "A", "parts": 5, "max_cost": 10, "count": 2},
        "B": {"asset": "B", "parts": 1, "max_cost": 7, "count": 1},
    }


def test_x_join_combines_two_inputs_inside_one_tenant():
    left = [
        rec("o1", "orders", tenant="T1", asset="A1"),
        rec("o2", "orders", tenant="T2", asset="A1"),
        rec("o3", "orders", tenant="T1", asset="A9"),
    ]
    right = [Rec("a1", "assets", {"tenant": "T1", "asset": "A1", "model": "Voltara"}, None, {"node": "n7"})]
    res = run("x_join", left + right, {"input": "n7", "key": "asset"})
    assert [r.ext_id for r in res.out] == ["o1"]
    assert res.out[0].data["n7"]["model"] == "Voltara"
    assert res.side["unmatched"] == 2
    res = run("x_join", left + right, {"input": "assets", "key": "asset", "how": "left"})
    assert [r.ext_id for r in res.out] == ["o1", "o2", "o3"] and res.out[0].data["assets"]["model"] == "Voltara"


def test_x_enrich_adds_reference_data_and_keeps_the_source():
    table = {"MTR-2041": {"model": "Voltara 75kW", "site": "Site 3"}}
    res = run("x_enrich", [rec("1", asset_id="MTR-2041"), rec("2", asset_id="NOPE")],
              {"model": "Asset & component", "key": "asset_id", "fields": ["model"], "table": table})  # fmt: skip
    assert res.out[0].data["asset"] == {"model": "Voltara 75kW"} and res.out[0].data["asset_id"] == "MTR-2041"
    assert "asset" not in res.out[1].data and res.side["missing"] == 1


# ------------------------------------------------------------------ branch and flow
def test_x_branch_splits_by_condition():
    recs = [rec("1", grade="A"), rec("2", grade="C"), rec("3", grade="B")]
    res = run("x_branch", recs, {"condition": [{"field": "grade", "check": "in", "arg": "A,B"}]})
    assert [r.ext_id for r in res.out] == ["1", "3"]
    assert [r.ext_id for r in res.side["then"]] == ["1", "3"]
    assert [r.ext_id for r in res.side["else"]] == ["2"]


def test_x_loop_expands_items():
    res = run("x_loop", [rec("W1", items=[{"sku": "a"}, {"sku": "b"}]), rec("W2")], {"items_path": "items"})
    assert [(r.ext_id, r.data.get("sku")) for r in res.out] == [("W1#0", "a"), ("W1#1", "b"), ("W2", None)]
    assert res.out[0].meta["parent"] == "W1"


def test_x_wait_and_x_call_minimal():
    res = run("x_wait", [rec("1", ready=True), rec("2", ready=False)], {"duration_min": 15, "until": "ready == true"})
    assert [r.ext_id for r in res.out] == ["1"] and [r.ext_id for r in res.side["waiting"]] == ["2"]
    assert res.side["resume_at"] == "2026-11-21T12:15:00Z"
    res = run("x_call", [rec("1")], {"workflow": "WF-2"})
    assert [r.ext_id for r in res.out] == ["1"] and res.side["call"] == {"workflow": "WF-2", "records": 1}


def test_sinks_collect_without_side_effects_when_dry():
    logs: list[str] = []
    bad = Reject(rec("9", qty=-1), "qty", "range", -1, "below 1")
    res = run("x_err", [bad], {"action": "hold"}, ctx(logs=logs))
    assert res.out == [] and res.side["held"] == 1 and res.side["rejects"][0]["rule"] == "range"
    assert res.side["held_ids"] == []
    assert run("x_err", [bad], {"action": "drop"}).side["dropped"] == 1
    res = run("x_audit", [rec("1"), rec("2")], {"level": "info"}, ctx(logs=logs))
    assert res.side["audit"]["records"] == 2 and logs
    res = run("x_pub", [rec("1")], {"topic": "asset.updated"})
    assert res.side["publish"] == {"topic": "asset.updated", "count": 1, "keys": ["1"], "sent": False}
