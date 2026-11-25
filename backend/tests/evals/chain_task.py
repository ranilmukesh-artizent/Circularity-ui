"""The chain task of the evals (plan 9, P9-2.15; stories X-05, X-15): run the stage chain on one case and say what happened.

    run_chain(inp, loop=None, plant=None) -> ChainOut     start state, open the case if it comes from data, plant text on its
                                                           evidence, drive the chain as the worker does, read the records

Owns: the scenario driver shared by the chain dataset and the injection dataset. Never does: judge the result (the
evaluators do) or call a model other than the loop it is given (none by default: the deterministic path, R16).
Each run starts from the demo's starting state and leaves it again, so a dataset's cases do not see one another.
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import chain, runtime
from di.services.agents.loop import AgentLoop
from di.services.cases import store
from tests import starting
from tests.evals.outcome import ChainIn, ChainOut
from tests.evals.scripted import live, no_model
from tests.helpers import call

ORG = "Customer A"
PLANNERS = {"Customer A": "planner-a", "Customer B": "planner-b", "Customer C": "planner-c"}
READING_KEYS = ("summary", "questions")
Plant = tuple[str, str, str]  # (evidence key, note, source label)


def clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))  # the stage records and the messages cascade
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


def _open(inp: ChainIn) -> str:
    if inp.case_id:
        return inp.case_id
    body = {"org_unit_id": ORG, "template_key": inp.template, "asset_key": f"T-EVAL-{inp.template}", "reason": "manual",
            "facts": inp.facts}  # fmt: skip
    r = call("case.open", body, "admin")
    assert r.get("ok"), r
    return str(r["output"]["case_id"])


def _plant(case_id: str, plant: Plant) -> None:
    key, note, source = plant
    with SessionLocal() as s:
        data = s.execute(text("SELECT data FROM case_record WHERE id = :c"), {"c": case_id}).scalar_one()
        for e in data["evidence"]:
            if e["k"] == key:
                e["note"], e["source"] = note, source
        s.execute(text("UPDATE case_record SET data = CAST(:d AS jsonb) WHERE id = :c"), {"d": json.dumps(data), "c": case_id})
        s.commit()


def reading_texts(reading: Mapping[str, Any]) -> list[str]:
    """Every sentence of a stage reading (a `StageReading` as JSON) that a person would read."""
    out = [str(reading.get("summary") or ""), *map(str, reading.get("questions") or [])]
    out += [str(f.get("text") or "") for f in reading.get("findings") or []]
    out += [str(c.get("text") or "") for c in reading.get("concerns") or []]
    if rec := reading.get("recommendation"):
        out.append(str(rec.get("why") or ""))
    return [t for t in out if t]


def run_chain(inp: ChainIn, loop: AgentLoop | None = None, plant: Plant | None = None) -> ChainOut:
    starting.reset()
    clean()
    runtime.set_loop(loop or live() or no_model())
    try:
        case_id = _open(inp)
        if plant:
            _plant(case_id, plant)
        with SessionLocal() as s:
            owner = s.execute(text("SELECT data->>'owner' FROM case_record WHERE id = :c"), {"c": case_id}).scalar_one()
            run_id = runtime.start(s, "recover-chain", "stage_chain", case_id, account=PLANNERS[owner])
            s.commit()
            status = runtime.run_until_blocked(s, run_id)
        with SessionLocal() as s:
            recs = chain.records_of(s, run_id)
            case = store.get(s, case_id) or {}
            journal = sorted(set(s.execute(text("SELECT action FROM action_journal")).scalars()))
            props = sorted(set(s.execute(text("SELECT action FROM agent_proposal")).scalars()))
        rec = case.get("recommendation") or {}
        readings = [t for r in recs for t in reading_texts(r.output.get("reading") or {})]
        rules = [{k: v for k, v in r.output.items() if k not in ("reading", "model")} for r in recs]  # not the model's words
        blob = json.dumps({"case": case, "outputs": rules}, default=str)
        return ChainOut(
            case_id=case_id, run_status=status, route=rec.get("id"), stages={r.stage: r.status for r in recs},
            hold_reasons=sorted({str(x.get("reason")) for r in recs for x in r.reasons}), journal=journal, proposals=props,
            readings=readings, facts_blob=blob,
        )  # fmt: skip
    finally:
        runtime.set_loop(None)
