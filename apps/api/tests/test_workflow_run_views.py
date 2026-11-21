"""The run views of a workflow read one set of real figures (plan 6 follow-up, decision D-Fabric).

For a run that happened in the app, the Runs table's in / out / errors (`run_figures`, one per history entry), the Data
quality panel (`quality`, the latest real run) and View failed records (`failed_rows`) count the same held records:
failed_record rows under the run's key that are still held, counted per record (a record held on two fields is one
record). The demo's seeded runs never ran: their figures are `{"real": false}` and the page keeps the demo's estimate
for them, as the Monitor does for a workflow without real runs (D1); a workflow whose last run is seeded has no
`quality` ("No real run yet").
"""

import pytest
from sqlalchemy import text

from di import state
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import client, h

WID = "WF-104"  # Ingest · Oracle Order Management: its validation step is "v"
KEY = "RUN-VIEW1"
TS = 1791363600000


def setup_module():
    starting.reset()


def teardown_module():
    _clear()
    starting.reset()


def _clear() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM failed_record WHERE run_id LIKE 'RUN-VIEW%'"))
    state.reset(["workflows", "workflow_runs"])


@pytest.fixture(autouse=True)
def fresh():
    _clear()
    yield
    _clear()


def detail(wid: str) -> dict:
    r = client.get(f"/api/screens/workflows/{wid}", headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()


def real_run(st: str = "warning", rows: int | None = 50, key: str = KEY) -> None:
    """A finished real run of WID under `key`: it read `rows` records and held A1, A2 and A3 at the validation step (A3
    on two fields); A4 was held too and reprocessed since, so it no longer counts."""
    from di.canonical.failed import hold

    with SessionLocal() as s:
        held = [("A1", "qty", 0), ("A2", "qty", -1), ("A3", "qty", 0), ("A3", "price", None), ("A4", "qty", 0)]
        for ext, field, v in held:
            hold(s, run_kind="workflow", run_id=key, source_id="oms", step="v", resource="orders", ext_id=ext,
                 field=field, rule="range" if field == "qty" else "required", value=v, reason=f"{field} broke a rule",
                 payload={"id": ext})  # fmt: skip
        s.execute(text("UPDATE failed_record SET status = 'reprocessed' WHERE run_id = :k AND ext_id = 'A4'"), {"k": key})
        w = state.get(s, "workflows", WID)
        rec = {"id": KEY, "wf": WID, "name": w["name"], "ts": TS, "trig": "Manual", "dur": 2.5, "rows": rows, "state": st,
               "note": "3 records held at Validation & enrichment"}  # fmt: skip
        state.add(s, "workflow_runs", key, rec)
        w["last"] = {"ts": TS, "state": st, "dur": 2.5, "rows": rows, "note": rec["note"]}
        w["lastRun"] = {"id": KEY, "ts": TS, "t0": TS - 2500, "trig": "Manual", "states": {}, "dur": {}, "order": [],
                        "status": st, "note": rec["note"], "counts": {}, "held": 3, "key": key}  # fmt: skip
        state.put(s, "workflows", WID, w)
        s.commit()


def test_the_runs_table_the_data_quality_panel_and_the_failed_records_count_the_same_held_records():
    real_run()
    d = detail(WID)
    assert d["history"][0]["id"] == KEY
    assert len(d["run_figures"]) == len(d["history"])
    assert d["run_figures"][0] == {"real": True, "key": KEY, "in": 50, "out": 47, "held": 3}
    q = d["quality"]
    assert {k: q[k] for k in ("real", "key", "run", "state", "in", "held", "valid")} == {
        "real": True, "key": KEY, "run": KEY, "state": "warning", "in": 50, "held": 3, "valid": 47,
    }  # fmt: skip
    # held records by step, field and rule, most first: A1, A2, A3 broke the qty range, A3 also the price rule
    assert q["groups"] == [
        {"step": "v", "label": "Validation & enrichment", "field": "qty", "rule": "range", "n": 3},
        {"step": "v", "label": "Validation & enrichment", "field": "price", "rule": "required", "n": 1},
    ]
    assert len(d["failed_rows"]) == 4 and len({r["rec"] for r in d["failed_rows"]}) == q["held"] == 3


def test_a_failed_run_has_no_out_figure():
    real_run("failed")
    d = detail(WID)
    assert d["run_figures"][0] == {"real": True, "key": KEY, "in": 50, "out": None, "held": 3}
    assert d["quality"]["state"] == "failed" and d["quality"]["held"] == 3


def test_a_run_in_progress_has_no_figures_yet():
    with SessionLocal() as s:
        rec = {"id": "RUN-VIEW2", "wf": WID, "name": "x", "ts": TS, "trig": "Manual", "dur": None, "rows": None,
               "state": "running", "note": ""}  # fmt: skip
        state.add(s, "workflow_runs", "RUN-VIEW2", rec)
        s.commit()
    d = detail(WID)
    assert d["history"][0]["state"] == "running"
    assert d["run_figures"][0] == {"real": True, "key": "RUN-VIEW2", "in": None, "out": None, "held": None}


@pytest.mark.parametrize("wid", ["WF-101", "WF-104", "WF-116"])
def test_seeded_runs_keep_the_demo_figures_and_have_no_data_quality(wid):
    """The seeded runs (the demo's S.wf.runs, or the workflow's recorded last run) never ran in the app."""
    d = detail(wid)
    assert d["history"] and d["run_figures"] == [{"real": False}] * len(d["history"])
    assert d["quality"] is None and d["failed_rows"] == []
