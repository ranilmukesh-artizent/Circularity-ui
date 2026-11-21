"""B15: the Workflow Studio's actions give the demo's results (fixtures/golden/workflow_writes.json).

Each golden scenario ran in a fresh copy of the demo, so each starts here from the starting workflows and runs. Every
call is replayed over HTTP and its result compared exactly (booleans strict; `seq` relative to the scenario's first
journaled call). A `flush` step is where the demo's run timers fired: here the queued `workflow.run` jobs run
in-process (the worker is stopped during the tests). Then the Workflow Studio's reads (the B14 endpoints) are compared
with what the demo's own functions returned.

**What a run draws at random.** The demo draws a run's duration and record count with Math.random, not with the
action's seeded generator, so the server cannot reproduce them (it draws its own, seeded from the run, in the same
ranges). For the runs a scenario makes, these fields are left out of the comparison, with what follows from them:
- the run's `dur` and `rows` (in the recent runs, the workflow's `last` and its history) and `lastRun.t0` (the start,
  now - duration), and the duration and record count of the earlier runs the history derives from the last one;
- the records in and out of each step (`run_counts`): compared as which steps carried records and which did not;
- the failed records (`failed_rows`, one per record validation rejected, a share of the run's records): compared as
  a prefix, since each row is a function of its position only.
Everything else (the states, the note, the per-step durations, the run ids, the success counts) is compared exactly.

**New workflow starts minimal (a deliberate change, decision log 21 Nov 2026).** The demo gave a new ingest, outbound
or decision workflow its full template graph; here New workflow starts from the blocks it needs to run (tpl
{k: "min"}). `_minimal_start` rewrites the scenarios' expectations accordingly: a workflow the scenario created gets
the minimal template, and where it still held the demo's template graph (as created, or reset to it), the minimal one.

The workflow.run output is the demo's ({id, name}) plus `run`, the id of the run record the job writes its progress
into; `run` is checked and set aside. The saved snapshot (`saved`, a JSON string) is compared parsed: the database
does not keep the key order of the graph inside it.
"""

import copy
import json

import pytest
from sqlalchemy import text

import di.actions.workflows as wf
from di import golden, state
from di.actions.workflow_builder import minimal_graph
from di.db import engine
from di.reads.common import SOURCES
from tests import starting
from tests.helpers import call, client, h, norm

G = golden.load("workflow_writes")
B14 = golden.load("screens/workflows")
STARTING_RUNS = {r["id"] for r in B14["runs"]}


def _min_tpl(tpl: dict) -> dict | None:
    """The minimal template workflow.create gives now, for the demo's generated one (None: not a generated template)."""
    k, sid = tpl.get("k"), tpl.get("src")
    if k == "ingest":
        return {"k": "min", "type": "ingest", "src": sid, "arrive": "api" if SOURCES[sid].get("interval") else "event"}
    if k == "out":
        return {"k": "min", "type": "out", "src": sid, "ch": tpl.get("ch") or (wf.DELIVER.get(sid) or ["api"])[0]}
    if k == "dec" and tpl.get("id") == "standard":
        return {"k": "min", "type": "dec", "id": "standard"}
    return None


def _trim(rec: dict | None, full: dict, mini: dict) -> None:
    """A run record's per-step fields (states, durations, order, the step index i) for the steps the minimal graph has."""
    if not rec:
        return
    every, keep = {n["id"] for n in full["nodes"]}, {n["id"] for n in mini["nodes"]}
    order = rec.get("order")
    if isinstance(rec.get("i"), int) and isinstance(order, list):
        rec["i"] = len([x for x in order[: rec["i"]] if x in keep])
    for f, v in list(rec.items()):
        if isinstance(v, dict) and set(v) & every:
            rec[f] = {k: x for k, x in v.items() if k in keep}
        elif isinstance(v, list) and v and all(isinstance(x, str) for x in v) and set(v) <= every:
            rec[f] = [x for x in v if x in keep]


def _minimal_start(sc: dict) -> dict:
    """The scenario with New workflow's minimal start in place of the demo's full template (see the module docstring)."""
    sc = copy.deepcopy(sc)
    obs = sc["observed"]
    made: set[str] = set()  # the workflows New workflow made from a generated template, as they stand at the end
    for c in sc["calls"]:  # ids are reused after a delete, so follow the calls in order
        if c.get("action") in ("workflow.create", "workflow.duplicate") and (c.get("result") or {}).get("ok"):
            plain = c["action"] == "workflow.create" and "graph" not in c["input"] and "tpl" not in c["input"]
            (made.add if plain else made.discard)(c["result"]["output"]["id"])
    given = {c["input"].get("id") for c in sc["calls"] if "graph" in (c.get("input") or {})}  # saved with a graph of its own
    swap: dict[str, tuple[dict, dict]] = {}
    for w in obs["workflows"]:
        if w["id"] not in made or not w.get("tpl") or not (mt := _min_tpl(w["tpl"])):
            continue
        full, mini = wf.build(w["tpl"]), minimal_graph(mt)
        swap[w["id"]] = (full, mini)
        w["tpl"] = mt
        if w["id"] in given:
            continue
        if norm(w.get("graph")) == norm(full):
            w["graph"] = copy.deepcopy(mini)
            _trim(w.get("lastRun"), full, mini)
        if isinstance(w.get("saved"), str):
            sv = json.loads(w["saved"])
            if norm(sv.get("g")) == norm(full):
                sv["g"] = copy.deepcopy(mini)
                w["saved"] = json.dumps(sv)
    for wid, d in obs["detail"].items():
        if d and wid in swap and norm(d.get("template")) == norm(swap[wid][0]):
            d["template"] = copy.deepcopy(swap[wid][1])
        w = next((x for x in obs["workflows"] if x["id"] == wid), None)
        if d and wid in swap and w and norm(w.get("graph")) == norm(swap[wid][1]):  # per-step reads follow its steps
            keep = {n["id"] for n in swap[wid][1]["nodes"]}
            d["run_counts"] = {k: v for k, v in d["run_counts"].items() if k in keep}
            _trim(d.get("run_from_last"), swap[wid][0], swap[wid][1])
    return sc


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def run_queued() -> int:
    """Run the queued workflow.run jobs, oldest first, as the worker would."""
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND status = 'queued' ORDER BY id")
        ).all()
    for job_id, payload in rows:
        wf.run_job(payload)
        with engine.begin() as conn:
            conn.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})
    return len(rows)


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(wf, "STEP_SECONDS", 0)
    monkeypatch.setattr(wf, "QUICK_SECONDS", 0)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    state.reset(["workflows", "workflow_runs"])
    return


# ---------------------------------------------------------------- what a run draws at random
def _new_runs(obs: dict) -> set[str]:
    return {r["id"] for r in obs["runs"]} - STARTING_RUNS


def _mask_wf(w: dict, new: set[str]) -> dict:
    w = dict(w)
    if w.get("saved"):
        w["saved"] = json.loads(w["saved"])
    lr = w.get("lastRun")
    if lr and lr.get("id") in new:
        w["lastRun"] = {k: v for k, v in lr.items() if k != "t0"}
        w["last"] = {k: v for k, v in w["last"].items() if k not in ("dur", "rows")}
    return w


def _mask_run(r: dict, new: set[str], drop_all: bool = False) -> dict:
    return {k: v for k, v in r.items() if k not in ("dur", "rows")} if drop_all or r["id"] in new else r


def _ran(w: dict | None, new: set[str]) -> bool:
    return bool(w and (w.get("lastRun") or {}).get("id") in new)


def _list_view(w: dict) -> dict:
    stat = "failing" if w["status"] == "published" and w.get("last") and w["last"]["state"] == "failed" else w["status"]
    return {k: v for k, v in w.items() if k not in ("graph", "saved", "tpl")} | {"stat": stat}


def _check_run_fields(w: dict) -> None:
    """The server's own draws are in the demo's ranges."""
    last = w["last"]
    assert 1 <= last["dur"] <= 4.5, last
    lo, hi = (1, 6) if w["cat"] == "Outbound" else (1, 1) if w["cat"] == "Decision" else (30, 900)
    assert lo <= last["rows"] <= hi, last


# ---------------------------------------------------------------- the replay
class Replay:
    def __init__(self, name: str):
        self.name, self.base = name, None

    def check(self, k: int, step: dict) -> None:
        where = f"{self.name} call {k}: {step['as']} {step['action']} {json.dumps(step['input'])[:80]}"
        exp = dict(step["result"])
        got = call(step["action"], step["input"], step["as"])
        if exp.get("ok") and "seq" in exp:
            assert "seq" in got, (where, got)
            if self.base is None:
                self.base = (exp["seq"], got["seq"])
            exp["seq"] = exp["seq"] - self.base[0] + self.base[1]
        if step["action"] == "workflow.run" and got.get("ok"):
            run = got["output"].pop("run")
            assert isinstance(run, str) and run.startswith("RUN-"), (where, run)
        assert norm(got) == norm(exp), where


@pytest.mark.parametrize("name", list(G))
def test_scenario(fresh, name):
    sc = _minimal_start(G[name])
    r = Replay(name)
    for k, step in enumerate(sc["calls"]):
        if step.get("flush"):
            run_queued()
            continue
        r.check(k, step)
    run_queued()  # anything still queued (the demo's timers would fire too)
    obs = sc["observed"]
    new = _new_runs(obs)

    # the list: workflows, recent runs, attention
    got = client.get("/api/screens/workflows", headers=h("admin")).json()
    want_wf = [_list_view(_mask_wf(w, new)) for w in obs["workflows"]]
    got_wf = [_mask_wf(w, new) for w in got["workflows"]]
    assert norm(got_wf) == norm(want_wf), f"{name}: workflows"
    for w in got["workflows"]:
        if _ran(w, new):
            _check_run_fields(w)
    assert norm([_mask_run(x, new) for x in got["runs"]]) == norm([_mask_run(x, new) for x in obs["runs"]]), f"{name}: runs"
    assert got["attention"] == obs["attention"], f"{name}: attention"

    # each workflow the scenario looked at
    for wid, want in obs["detail"].items():
        res = client.get(f"/api/screens/workflows/{wid}", headers=h("admin"))
        if want is None:
            assert res.status_code == 404, f"{name}: {wid} should be gone"
            continue
        assert res.status_code == 200, res.text
        d = res.json()
        w_want = next(x for x in obs["workflows"] if x["id"] == wid)
        ran = _ran(w_want, new)
        assert norm(_mask_wf(d["workflow"], new)) == norm(_mask_wf(w_want, new) | {"stat": want["stat"]}), f"{name}: {wid}"
        assert norm(d["template"]) == norm(want["template"]), f"{name}: {wid} template"
        hist_got = [_mask_run(x, new, drop_all=ran) for x in d["history"]]
        hist_want = [_mask_run(x, new, drop_all=ran) for x in want["history"]]
        assert norm(hist_got) == norm(hist_want), f"{name}: {wid} history"
        rfl_got, rfl_want = d["run_from_last"], want["run_from_last"]
        if ran:
            rfl_got, rfl_want = ({k: v for k, v in x.items() if k != "t0"} for x in (rfl_got, rfl_want))
        assert norm(rfl_got) == norm(rfl_want), f"{name}: {wid} run_from_last"
        if ran:
            pattern = {k: (v["in"] > 0, v["out"] > 0, v["rej"] > 0) for k, v in want["run_counts"].items()}
            assert {k: (v["in"] > 0, v["out"] > 0, v["rej"] > 0) for k, v in d["run_counts"].items()} == pattern, wid
            n = min(len(d["failed_rows"]), len(want["failed_rows"]))
            assert d["failed_rows"][:n] == want["failed_rows"][:n], f"{name}: {wid} failed rows"
            assert bool(d["failed_rows"]) == bool(want["failed_rows"]), f"{name}: {wid} failed rows"
        else:
            assert norm(d["run_counts"]) == norm(want["run_counts"]), f"{name}: {wid} run_counts"
            assert d["failed_rows"] == want["failed_rows"], f"{name}: {wid} failed rows"


# ---------------------------------------------------------------- the ports, against the recorded demo data
@pytest.mark.parametrize("w", B14["starting"], ids=lambda w: w["id"])
def test_template_graphs(w):
    """wfBuild: the template graph of every starting workflow, as the demo built it."""
    assert wf.build(w["tpl"]) == B14["detail"][w["id"]]["template"]


@pytest.mark.parametrize("w", B14["starting"], ids=lambda w: w["id"])
def test_run_simulation_matches_last_runs(w):
    """wfSimOutcome on a starting workflow gives the step states and per-step durations of its recorded last run,
    except where the demo's seeding injected a failure (Depot Repair's validation step)."""
    lr = w.get("lastRun")
    if not lr or w["src"] == "repair":
        return
    o = wf.sim_outcome(dict(w))
    assert o["states"] == lr["states"] and o["order"] == lr["order"] and o["status"] == lr["status"]
    assert norm(o["dur"]) == norm(lr["dur"])
    assert o["note"] == lr["note"]


# ---------------------------------------------------------------- block settings (plan 6, task C2)
def _new_ingest(src: str = "erp") -> tuple[str, dict]:
    r = call("workflow.create", {"type": "ingest", "src": src}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    return wid, client.get(f"/api/screens/workflows/{wid}", headers=h("developer")).json()["workflow"]


def _save(w: dict, graph: dict) -> dict:
    body = {"id": w["id"], "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": graph}
    return call("workflow.save", body, "developer")


def test_bad_settings_block_publish(fresh):
    """Review Focus 5: a setting the step cannot use is saved, the checks name the block and the field, and Publish is
    refused until it is fixed."""
    wid, w = _new_ingest()
    g = copy.deepcopy(w["graph"])
    v = next(n for n in g["nodes"] if n["ref"] == "x_val")
    v["cfg"] = {"rules": [{"field": "", "check": "present"}]}
    g["nodes"].append({"id": "fx", "k": "xf", "ref": "x_fx", "x": 0, "y": 400, "cfg": {"currency": "XYZ"}})
    assert _save(w, g)["ok"]
    stored = client.get(f"/api/screens/workflows/{wid}", headers=h("developer")).json()["workflow"]["graph"]
    assert next(n for n in stored["nodes"] if n["id"] == v["id"])["cfg"] == v["cfg"]  # kept as entered
    errs = [e["msg"] for e in call("workflow.validate", {"id": wid}, "developer")["output"]["errors"]]
    assert "Validation & enrichment: Rules rule 1 has no field." in errs
    assert "Convert currency: Target currency XYZ is not one of USD, EUR, INR." in errs
    r = call("workflow.publish", {"id": wid}, "developer")
    assert not r["ok"] and r["error"]["code"] == "conflict", r
    # fixed: the checks are clean of settings errors and it publishes
    v["cfg"] = {"rules": [{"field": "qty", "check": "range", "arg": ">0"}]}
    g["nodes"] = [n for n in g["nodes"] if n["id"] != "fx"]
    assert _save(w, g)["ok"]
    assert not [e for e in call("workflow.validate", {"id": wid}, "developer")["output"]["errors"] if ":" in e["msg"]]
    assert call("workflow.publish", {"id": wid}, "developer")["ok"]


def test_settings_are_stored_only_where_they_differ_from_the_defaults(fresh):
    """A graph saved without `cfg` (every workflow before settings existed) is stored as it is and reads as the defaults;
    settings equal to the defaults are not stored, so the graph stays the one the demo has."""
    from di.workflow.blocks import default_cfg, node_cfg

    wid, w = _new_ingest()
    g = copy.deepcopy(w["graph"])
    assert all("cfg" not in n for n in g["nodes"])
    v = next(n for n in g["nodes"] if n["ref"] == "x_val")
    v["cfg"] = default_cfg("x_val") | {"on_failure": "reject"}
    assert _save(w, g)["ok"]
    stored = client.get(f"/api/screens/workflows/{wid}", headers=h("developer")).json()["workflow"]["graph"]
    by = {n["id"]: n for n in stored["nodes"]}
    assert by[v["id"]]["cfg"] == {"on_failure": "reject"}
    assert all("cfg" not in n for nid, n in by.items() if nid != v["id"])
    assert node_cfg(by["r"]) == default_cfg("conn")
    # the starting workflows open with the defaults and no settings errors
    for sw in B14["starting"]:
        g0 = sw.get("graph") or wf.build(sw["tpl"])
        assert wf.cfg_checks(g0) == []
