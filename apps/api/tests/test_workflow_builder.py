"""Workflow Studio's AI workflow builder (di.actions.workflow_builder): the demo's workflow.draft and the guided planner
workflow.plan, and the rule-based Ask's workflow.draft runner.

- a fully specified description gives a complete plan at once (no questions) with 0 check errors: the blocks the
  workflow needs to run plus exactly the ones it asks for (nothing from the standard template), the trigger and run
  settings it names
- with the defaults, a plan holds only the required blocks (one ingestion channel, validation, mapping, model,
  snapshot) and passes the checks with no warning
- a vague one asks the workflow type first, and only that
- "ingest from salesforce ..." resolves to the CRM source, adds currency conversion and late-event ordering, runs every
  30 minutes; the details round asks only what the description did not settle
- a system that is not connected, one with no feed, one Circularity cannot write to: said so, with real choices
- outbound asks the delivery method from what the target accepts
- every plan graph, for every readable source and every target and delivery, passes the server's checks
- the person creates it: workflow.create with the plan's graph, then workflow.save with its settings, through the
  pipeline with the person's permission; workflow.validate shows 0 errors and Run now is accepted
- Ask "Build an ingest for Dealer network with currency conversion": the demo's text and wfdiff card; the draft call is
  recorded as skipped (Ask never writes)
The language model is switched off here (model_slots returns {}), so every answer is the deterministic reading.
"""

import pytest
from sqlalchemy import text

import di.actions.workflow_builder as B
import di.actions.workflows as wf
from di import golden, policy, state
from di.actions.pipeline import Actor, CallContext
from di.ask.fallback import ask_rule
from di.auth import load_context
from di.db import SessionLocal, engine
from di.reads.common import SOURCES
from tests import starting
from tests.helpers import call

DEV = "developer"


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(B, "model_slots", lambda prompt: {})


def plan(prompt: str, answers: dict | None = None, user: str = DEV) -> dict:
    r = call("workflow.plan", {"prompt": prompt, "answers": answers or {}}, user)
    assert r["ok"], r
    return r["output"]


def ids(out: dict) -> list[str]:
    return [q["id"] for q in out["questions"]]


def refs(p: dict) -> list[str]:
    return [n["ref"] for n in p["graph"]["nodes"]]


# ---------------------------------------------------------------- the planner
def test_fully_specified_prompt_gives_a_complete_tailored_plan():
    out = plan(
        "Build an ingest from Dealer network without currency conversion, with unit normalisation and an error handler "
        "but no audit log, every 15 minutes, 3 retries, alert when a run fails"
    )
    assert out["status"] == "ready" and out["questions"] == []
    p = out["plan"]
    assert (p["type"], p["src"], p["trigger"]) == ("ingest", "dlr", {"t": "schedule", "min": 15})
    assert p["settings"] == {"retries": 3, "alert": "A run fails"}
    assert p["checks"]["errors"] == [] and wf.errors(p["graph"], "pipe") == []
    r = refs(p)
    assert "x_units" in r and "x_err" in r
    assert "x_fx" not in r and "x_audit" not in r and "x_pub" not in r  # not asked for: not added
    assert set(p["diff"]["added"]) == {"Normalise units", "Error handler"}
    assert "Validation & enrichment" in p["diff"]["required"]
    assert any(c.startswith("Trigger: Every 15 min") for c in p["diff"]["changed"])
    # a tailored name and description, not the stock "Ingest · Machinio"
    assert p["name"] == "Dealer network ingest · unit normalisation"
    assert "normalise units" in p["desc"] and "audit" not in p["desc"]
    assert p["owner"] == SOURCES["dlr"]["owner"]
    # the steps in run order, each with why; left to right
    order = [s["id"] for s in p["steps"]]
    assert order.index("r") < order.index("v") < order.index("s_units") < order.index("m")
    xs = {n["id"]: n["x"] for n in p["graph"]["nodes"]}
    assert xs["r"] < xs["v"] < xs["s_units"] < xs["m"] < xs["c_dem"]
    assert all(s["why"] for s in p["steps"])
    assert next(s for s in p["steps"] if s["id"] == "s_units")["status"] == "added"
    # what the person's Create button sends
    assert p["create"]["type"] == "ingest" and p["create"]["src"] == "dlr" and p["create"]["graph"] == p["graph"]
    assert p["save"]["trig"] == p["trigger"] and p["save"]["retries"] == 3


def test_defaults_give_only_the_required_blocks():
    p = plan("ingest from salesforce every 30 minutes", {"_defaults": True})["plan"]
    assert sorted(refs(p)) == sorted(["crm", "x_gw", "x_val", "crm", "c_dem", "snap"])  # a schedule polls the API
    assert p["checks"]["errors"] == [] and p["checks"]["warnings"] == []
    assert p["diff"]["added"] == [] and all(s["status"] in ("required", "fixed") for s in p["steps"])
    assert all(s["why"].startswith(("Required to run", "Fixed step", "Reads", "Maps")) for s in p["steps"])
    # its default trigger (On event) gives event ingestion instead of the API gateway; both only when asked
    ev = plan("ingest from salesforce", {"_defaults": True})["plan"]
    assert "x_evt" in refs(ev) and "x_gw" not in refs(ev)
    both = plan("ingest from salesforce", {"_defaults": True, "channels": "both"})["plan"]
    assert {"x_gw", "x_evt"} <= set(refs(both))
    # the usual transform for the source type is offered, not added
    q = plan("ingest from salesforce")
    steps_q = next(x for x in q["questions"] if x["id"] == "steps")
    assert steps_q["default"] == [] and any("usual for this source" in c["hint"] for c in steps_q["choices"])


def test_vague_prompt_asks_the_type_first():
    out = plan("make a workflow")
    assert out["status"] == "questions" and ids(out) == ["type"]
    q = out["questions"][0]
    assert [c["value"] for c in q["choices"]] == ["ingest", "out", "dec", "blank"] and q["default"] == "ingest"
    assert all(c["label"] and c["hint"] for c in q["choices"])
    # the answer moves it on to the system
    nxt = plan("make a workflow", {"type": "ingest"})
    assert ids(nxt) == ["system"]
    assert all(SOURCES[c["value"]]["status"] != "unavailable" for c in nxt["questions"][0]["choices"])


def test_the_language_model_only_resolves_what_the_description_mentions(monkeypatch):
    guess = {"type": "ingest", "system": "crm", "trigger": "schedule", "minutes": 30, "steps": ["x_fx"], "name": "Made up"}
    monkeypatch.setattr(B, "model_slots", lambda prompt: guess)
    assert ids(plan("make a workflow")) == ["type"]  # nothing in the description to resolve: still asks
    # a word that names several systems: the model picks among them only
    oracle = plan("ingest from oracle", {"_defaults": True})
    assert ids(oracle) == ["system"]
    monkeypatch.setattr(B, "model_slots", lambda prompt: {"system": "tms"})
    assert plan("ingest from oracle", {"_defaults": True})["plan"]["src"] == "tms"
    # a name that is not one of ours: the model's reading is used and said
    monkeypatch.setattr(B, "model_slots", lambda prompt: {"system": "crm", "name": "Made up"})
    out = plan("ingest from our sales pipeline tool", {"_defaults": True})
    assert out["plan"]["src"] == "crm" and any("as CRM" in n for n in out["notes"])
    assert out["plan"]["name"] != "Made up"


def test_salesforce_ingest_with_currency_and_dedupe_every_30_minutes():
    prompt = "ingest from salesforce with currency conversion and dedupe, every 30 minutes"
    out = plan(prompt)
    assert out["status"] == "questions"
    got = {u["slot"]: u["value"] for u in out["understood"]}
    assert got["system"] == "CRM · Salesforce Sales Cloud" and got["trigger"] == "Every 30 min"
    # never asked again: type, system, trigger, steps
    assert not {"type", "system", "trigger", "steps"} & set(ids(out))
    assert {"handling", "retries", "alert"} <= set(ids(out))
    name_q = next(q for q in out["questions"] if q["id"] == "name")
    assert name_q["default"] == "CRM ingest · de-duplication and currency conversion"
    # answering with the defaults gives the plan
    answers = {q["id"]: q["default"] for q in out["questions"]}
    done = plan(prompt, answers)
    assert done["status"] == "ready"
    p = done["plan"]
    assert p["src"] == "crm" and p["trigger"] == {"t": "schedule", "min": 30}
    assert {"x_fx", "x_late"} <= set(refs(p)) and p["checks"]["errors"] == []
    assert set(p["diff"]["added"]) == {"Convert currency", "Order late events"}
    # "use the defaults for the rest" gives the same plan
    assert plan(prompt, {"_defaults": True})["plan"]["graph"] == p["graph"]


def test_unknown_system_offers_the_closest_real_ones():
    out = plan("Ingest from Workday every hour")
    assert ids(out) == ["system"]
    q = out["questions"][0]
    assert "workday" in q["note"] and "could not find" in q["note"]
    assert q["choices"] and all(SOURCES[c["value"]].get("read") for c in q["choices"])
    # a near miss is matched by its spelling
    near = plan("ingest from Salesfroce")
    assert near["questions"][0]["choices"][0]["value"] == "crm"


def test_systems_that_cannot_be_used_are_explained():
    iot = plan("ingest from device telemetry")
    assert ids(iot) == ["system"] and "no connected feed" in iot["notes"][0]
    assert "iot" not in [c["value"] for c in iot["questions"][0]["choices"]]
    ariba = plan("send approved instructions to SAP Ariba")
    assert ids(ariba) == ["system"] and "does not write to it" in ariba["notes"][0]
    assert all(wf.DELIVER.get(c["value"]) for c in ariba["questions"][0]["choices"])
    oracle = plan("ingest from oracle")
    assert ids(oracle) == ["system"] and oracle["questions"][0]["note"]
    assert {c["value"] for c in oracle["questions"][0]["choices"][:3]} == {"lease", "tms", "repair"}


def test_outbound_asks_the_delivery_method_the_target_accepts():
    out = plan("send approved instructions to SAP S/4HANA")
    assert ids(out) == ["delivery"]
    assert [c["value"] for c in out["questions"][0]["choices"]] == wf.DELIVER["erp"]
    refused = plan("send approved instructions to SAP S/4HANA as events")
    assert "does not accept events" in refused["notes"][0] and ids(refused) == ["delivery"]
    done = plan("send approved instructions to SAP S/4HANA by file with a code lookup", {"_defaults": True})
    p = done["plan"]
    assert (p["type"], p["src"], p["ch"], p["trigger"]) == ("out", "erp", "file", {"t": "approval"})
    assert p["checks"]["errors"] == [] and "x_lookup" in refs(p) and "a_file" in refs(p) and "x_man" in refs(p)
    assert p["diff"]["added"] == ["Code-table lookup"]


def test_every_plan_graph_passes_the_server_checks():
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account(DEV, pctx), ctx=pctx), session=s)
        all_steps = list(B.STEP_ORDER)
        for sid in B.readable(ctx):
            for answers in ({"_defaults": True}, {"_defaults": True, "steps": all_steps, "handling": [], "keep_std": "no"}):
                out = B.plan("ingest", {"type": "ingest", "system": sid, **answers}, ctx, use_model=False)
                assert out["status"] == "ready", (sid, out["notes"])
                assert wf.errors(out["plan"]["graph"], "pipe") == [], sid
        for sid in B.writable(ctx):
            for ch in wf.DELIVER[sid]:
                for steps in ([], list(B.OUT_STEPS)):
                    out = B.plan("outbound", {"type": "out", "system": sid, "delivery": ch, "steps": steps, "_defaults": True},
                                 ctx, use_model=False)  # fmt: skip
                    assert wf.errors(out["plan"]["graph"], "pipe") == [], (sid, ch)
        for dk in B.DECISIONS:
            for handling in (["x_audit"], []):
                out = B.plan(
                    "decision", {"type": "dec", "decision": dk, "handling": handling, "_defaults": True}, ctx, use_model=False
                )
                assert wf.errors(out["plan"]["graph"], "dec") == [], dk
        s.rollback()


def test_the_person_creates_the_plan_and_it_checks_clean():
    state.reset(["workflows", "workflow_runs"])
    p = plan("ingest from salesforce with currency conversion and dedupe, every 30 minutes", {"_defaults": True})["plan"]
    # a planner may plan but not create (the server's permission check)
    assert plan("ingest from salesforce", {"_defaults": True}, user="planner-a")["status"] == "ready"
    no = call("workflow.create", p["create"], "planner-a")
    assert not no["ok"] and no["error"]["code"] == "out_of_scope"
    made = call("workflow.create", p["create"], DEV)
    assert made["ok"], made
    wid = made["output"]["id"]
    saved = call("workflow.save", {"id": wid, **p["save"]}, DEV)
    assert saved["ok"], saved
    v = call("workflow.validate", {"id": wid}, DEV)
    assert v["ok"] and v["output"]["errors"] == []
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
    assert w["name"] == p["name"] and w["desc"] == p["desc"] and w["trig"] == {"t": "schedule", "min": 30}
    assert (w["retries"], w["alert"], w["owner"]) == (3, "A run fails", "Sales Operations") and w["graph"] == p["graph"]
    pub = call("workflow.publish", {"id": wid}, DEV)
    assert pub["ok"], pub
    run = call("workflow.run", {"id": wid}, DEV)
    assert run["ok"], run
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    state.reset(["workflows", "workflow_runs"])


def test_planning_saves_nothing():
    with engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM action_journal")).scalar_one()
    plan("ingest from salesforce", {"_defaults": True})
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM action_journal")).scalar_one() == before


# ---------------------------------------------------------------- the demo's draft and Ask
def test_workflow_draft_action_is_the_demos_draft():
    r = call("workflow.draft", {"source_id": "dlr", "desc": "with currency conversion"}, DEV)
    assert r["ok"] and r["output"]["source_id"] == "dlr" and r["output"]["errors"] == 0
    assert r["output"]["steps"] == len(r["output"]["draft"]["steps"]) == 11
    assert call("workflow.draft", {"source_id": "nope"}, DEV)["error"]["code"] == "not_found"
    # a step the source's standard ingest lacks goes in before the field mapping
    d = B.af_wf_draft("crm", "dedupe and currency")
    m = next(e for e in d["graph"]["edges"] if e["b"] == "m")
    assert m["a"] == "ai1" and [s["label"] for s in d["steps"] if s["id"].startswith("ai")] == [
        "Convert currency",
        "Order late events",
    ]
    assert d["errors"] == []


def test_ask_builds_an_ingest_like_the_demo():
    q = "Build an ingest for Dealer network with currency conversion"
    want = next(a["run"] for a in golden.load("ask")["answers"] if a["q"] == q and a["as"] == DEV)
    with SessionLocal() as s:
        pctx = load_context(s)
        acct = policy.account(DEV, pctx)
        got = ask_rule(
            q, CallContext(actor=Actor(account=acct, ctx=pctx), session=s), {"page": "home", "role": acct.role, "object": None}
        )
        s.rollback()
    assert got["intent"] == "workflow.draft" and got["text"] == want["text_out"] and got["cards"] == want["cards"]
    card = got["cards"][0]["data"]
    assert any(st["fixed"] for st in card["steps"]) and any("currency" in st["label"].lower() for st in card["steps"])
    assert [(c["action"], c["skipped"]) for c in got["calls"]] == [("workflow.draft", True)]
