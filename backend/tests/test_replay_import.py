"""P9-7.1 (story X-06; registry entry I-16): a history batch is checked row by row and imported.

Rows are data, not language: nothing here reads or writes free text, so the model-first rule (R16) has nothing to route. The
checks are pandera's (lazy); a bad row is held with one reason, a personal column refuses the whole import, the Executive
role only reads, and an org unit outside the person's tenants is out of reach.
"""

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.modeler.pack import load_pack
from di.services.replay import history
from tests import starting
from tests.helpers import call

PACK, ORG = "tool_fleet", "Customer A"
NOW = datetime(2026, 11, 1, tzinfo=UTC)
HEAD = ["item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "cost_logistics", "cost_refurb",
        "cost_test", "cost_fees", "market", "fact.condition", "fact.condition.at"]  # fmt: skip
FIXTURES = next(p for p in (Path("/fixtures/replay"), Path(__file__).parents[2] / "fixtures" / "replay") if p.is_dir())


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM replay_batch"))
        s.commit()
    starting.reset()


def route() -> str:
    return load_pack(PACK).routes[0].id


def row(n: int, **over: str) -> dict[str, str]:
    base = {
        "item_id": f"T{n:03d}", "class": load_pack(PACK).classes[0].id, "decided_at": "2026-05-04", "reason": "x",
        "actual_route": route(), "realised_value": "120.50", "cost_logistics": "5", "cost_refurb": "10", "cost_test": "2",
        "cost_fees": "3", "market": "US", "fact.condition": "B", "fact.condition.at": "2026-05-01T08:00:00",
    }  # fmt: skip
    return {**base, **over}


def as_csv(rows: list[dict[str, str]], head: list[str] | None = None) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=head or HEAD, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def mixed() -> list[dict[str, str]]:
    """10 good rows, then an unknown route, a repeated item_id, a future date and a missing value."""
    return [
        *(row(n) for n in range(1, 11)), row(11, actual_route="scrap"), row(1), row(13, decided_at="2027-01-01"),
        row(14, realised_value=""),
    ]  # fmt: skip


def test_x_06_import_checks_rows_and_holds_with_reasons():
    rows = mixed()
    ok_items, held = history.import_history(rows, load_pack(PACK), now=NOW)
    assert len(ok_items) == 10 and len(held) == 4
    assert sorted(h["held_reason"] for h in held) == sorted(
        [
            f"Route 'scrap' is not a route of {PACK}.",
            "Duplicate item_id.",
            "No valid decision date.",
            "No realised value.",
        ]
    )
    out = ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": as_csv(rows)}, "planner.a"))
    assert (out["rows"], out["held"]) == (14, 4)
    assert out["held_reasons"] == {
        f"Route 'scrap' is not a route of {PACK}.": 1, "Duplicate item_id.": 1, "No valid decision date.": 1,
        "No realised value.": 1,
    }  # fmt: skip
    assert out["period"] == ["2026-05-04", "2026-05-04"]
    listed = ok(call("replay.batches", {"pack": PACK, "org_unit_id": ORG}, "planner.a"))["batches"]
    assert listed[0]["id"] == out["id"] and len(listed[0]["held_items"]) == 4
    assert [h["n"] for h in listed[0]["held_items"]] == [11, 12, 13, 14]  # the row of the file each came from


def test_x_06_negative_cost_and_fact_without_date_are_held():
    rows = [row(1, cost_fees="-3"), row(2, **{"fact.condition.at": ""}), row(3)]
    ok_items, held = history.import_history(rows, load_pack(PACK), now=NOW)
    assert [h["held_reason"] for h in held] == ["Costs cannot be negative.", "Fact condition has no date."]
    assert [i["item_id"] for i in ok_items] == ["T003"]


def test_x_06_import_appends_to_a_batch_and_sees_its_ids():
    first = ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": as_csv([row(1), row(2)])}, "planner.a"))
    more = ok(call("replay.import", {"pack": PACK, "org_unit_id": ORG, "batch_id": first["id"],
                                     "csv": as_csv([row(2), row(3)])}, "planner.a"))  # fmt: skip
    assert more["id"] == first["id"] and (more["rows"], more["held"]) == (4, 1)
    assert more["held_reasons"] == {"Duplicate item_id.": 1}


def test_x_06_import_refuses_personal_columns():
    head = [*HEAD, "customer_name"]
    r = call(
        "replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": as_csv([row(1) | {"customer_name": "x"}], head)}, "planner.a"
    )
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "Column customer_name looks like personal data. Send de-identified extracts only."
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM replay_batch")).scalar_one() == 0


def test_x_06_import_refuses_missing_column_and_too_many_rows():
    r = call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": "item_id,decided_at\nA,2026-01-01\n"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    big = "item_id,decided_at,actual_route,realised_value\n" + "a,b,c,1\n" * (history.MAX_ROWS + 1)
    r = call("replay.import", {"pack": PACK, "org_unit_id": ORG, "csv": big}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"


def test_x_06_import_executive_refused_planner_ok():
    body = {"pack": PACK, "org_unit_id": ORG, "csv": as_csv([row(1)])}
    r = call("replay.import", body, "exec")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert r["error"]["message"] == "The Executive view reads replay reports; a Planner or Admin runs them."
    assert ok(call("replay.import", body, "planner.a"))["rows"] == 1


def test_replay_batch_tenant_boundary():
    body = {"pack": PACK, "org_unit_id": ORG, "csv": as_csv([row(1)])}
    r = call("replay.import", body, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    r = call("replay.batches", {"pack": PACK, "org_unit_id": ORG}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM replay_batch")).scalar_one() == 0


@pytest.mark.parametrize(("pack", "name"), [("tool_fleet", "tool_fleet_returns.csv"), ("device", "device.csv")])
def test_x_06_sample_csv_valid(pack: str, name: str):
    body = (FIXTURES / name).read_text(encoding="utf-8")
    assert body.startswith(f"# python -m di.services.replay.sample {pack} 120\n")
    ok_items, held = history.import_history(history.parse_csv(body), load_pack(pack), now=NOW)
    assert (len(ok_items), len(held)) == (120, 0)
    out = ok(call("replay.import", {"pack": pack, "org_unit_id": ORG, "csv": body}, "planner.a"))
    assert (out["rows"], out["held"]) == (120, 0) and out["period"] is not None


def test_x_06_sample_is_deterministic():
    from di.services.replay.sample import make_csv

    assert make_csv("device", 120) == (FIXTURES / "device.csv").read_text(encoding="utf-8")
