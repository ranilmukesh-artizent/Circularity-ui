"""The agent runtime (plan 8, MVP-11.5): an agent runs a playbook on a case, one step at a time, on the job queue.

    start(s, agent, playbook, case_id, *, account) -> run_id
        a run (table agent_run, status running) and its first `agent.step` job; the agent acts as `account` (the
        person who started it), as every agent call does
    step(s, run_id) -> status
        the next playbook step: a call runs through pipeline.invoke as the account, prepared by the agent, with the
        run's id (so the kill switch, autonomy, org scope and run limits apply, MVP-11.1/11.3), and is kept in
        agent_run_step. A held answer (MVP-11.4) -> `waiting` with the proposal id in `state`; a stopped agent or a
        reached run limit -> `stopped`; another refusal -> `failed`.
    wake(s, run_id)                   a proposal of the run was decided: accepted -> running again (a new job);
                                      rejected -> stopped
    resume_waiting(s, case_id)        the case was approved: runs waiting for that approval run on (a new job); the
                                      decision.approve and decision.override pipelines call it (pipeline.after)

The worker's `agent.step` job runs steps until the run is no longer running. Nothing polls: a waiting run is woken
by the person's action. The runtime never calls an action no agent may run (asserted at import).

Plan 9 (P9-2.1): every playbook walks the stage chain (`playbooks/stage_chain.py`, `stages/`; registry entry I-7).
`stage_chain` prepares each call as the stage's own agent (`StageDef.agent_id`, when the run's agent acts) with
`ctx.stage` set; `case_autopilot` is an alias that makes the same calls in the same order as the run's own agent. After a
stage's last call (or when it waits, is held or fails) its record is upserted in `agent_stage_record`.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import di.repositories.cases  # registers case.evidence (the worker imports only what its jobs need)
import di.services.actions.decisions  # registers evidence.request, case.reevaluate, decision.submit
import di.services.actions.execution  # noqa: F401 - registers instruction.resend
from di.core import jobs, policy
from di.core.auth import load_context
from di.core.config import get_settings
from di.repositories.live_rules import live_pack
from di.services.actions.pipeline import Actor, CallContext, after, invoke
from di.services.agents import chain, limits, registry
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.playbooks import case_autopilot as autopilot
from di.services.agents.playbooks import stage_chain
from di.services.agents.playbooks.case_autopilot import Done, Halt, Skip, Wait
from di.services.agents.stages import CHAIN
from di.services.cases import store

log = logging.getLogger(__name__)
PLAYBOOKS = {autopilot.NAME: stage_chain, stage_chain.NAME: stage_chain}  # case_autopilot is an alias of the chain
JOB = "agent.step"
_REACHED = (*autopilot.ACTIONS, *stage_chain.ACTIONS, *(a for m in CHAIN for a in m.ACTIONS))
_FORBIDDEN = [a for a in _REACHED if a.startswith(FORBIDDEN_ACTIONS)]
if _FORBIDDEN:
    raise RuntimeError(f"playbooks reach actions no agent may run: {_FORBIDDEN}")
STOPPING = ("Run limit reached", "is stopped by Admin")  # refusals that stop a run rather than fail it


def _enqueue(s: Session, run_id: str) -> None:
    jobs.enqueue(s, JOB, {"run_id": run_id}, dedupe_key=f"{JOB}:{run_id}")


def start(s: Session, agent: str, playbook: str, case_id: str | None, *, account: str) -> str:
    if playbook not in PLAYBOOKS:
        raise ValueError(f"unknown playbook {playbook!r}")
    if registry.get(s, agent) is None:
        raise ValueError(f"unknown agent {agent!r}")
    run_id = "AR-" + uuid.uuid4().hex[:12]
    s.execute(
        text(
            "INSERT INTO agent_run (id, agent, playbook, case_id, status, step, state) "
            "VALUES (:i, :a, :p, :c, 'running', 0, CAST(:st AS jsonb))"
        ),
        {
            "i": run_id,
            "a": agent,
            "p": playbook,
            "c": case_id,
            "st": json.dumps({"account": account} | stage_chain.start_state()),
        },
    )
    _enqueue(s, run_id)
    return run_id


def autostart(s: Session, case_id: str, account: str | None) -> str | None:
    """P9-0.9: start the case autopilot for a case just opened (the worker's `agent.autostart` job), or say why not.

    Starts only when DI_AUTOPILOT_ON_OPEN is on, the agent DI_AUTOPILOT_AGENT is enabled with autonomy `act`, there is
    an account to act for (the opener's, else DI_AUTOPILOT_ACCOUNT) and the agent has no run on the case yet. Returns the
    run id, or None after one info line naming the reason. The run still holds its decision for a person."""
    cfg = get_settings()

    def skip(why: str) -> str | None:
        log.info("autopilot not started for %s: %s", case_id, why)
        return None

    if not cfg.autopilot_on_open:
        return skip("autopilot off")
    agent = registry.get(s, cfg.autopilot_agent)
    if agent is None or not agent.enabled:
        return skip(f"agent {cfg.autopilot_agent} is stopped")
    if agent.autonomy != "act":
        return skip(f"agent {cfg.autopilot_agent} only proposes")
    who = account or cfg.autopilot_account
    if not who:
        return skip("no account to act for")
    q = text("SELECT 1 FROM agent_run WHERE agent = :a AND case_id = :c LIMIT 1")
    if s.execute(q, {"a": agent.id, "c": case_id}).first():
        return skip("already running")
    return start(s, agent.id, autopilot.NAME, case_id, account=who)


def get(s: Session, run_id: str, for_update: bool = False) -> dict | None:
    lock = " FOR UPDATE" if for_update else ""
    q = f"SELECT id, agent, playbook, case_id, status, step, state FROM agent_run WHERE id = :i{lock}"  # noqa: S608 - fixed columns
    row = s.execute(text(q), {"i": run_id}).mappings().first()
    return dict(row) if row else None


def _save(s: Session, run: dict, status: str, n: int, st: dict[str, Any]) -> str:
    s.execute(
        text("UPDATE agent_run SET status = :s, step = :n, state = CAST(:st AS jsonb), updated_at = now() WHERE id = :i"),
        {"s": status, "n": n, "st": json.dumps(st, default=str), "i": run["id"]},
    )
    return status


def _log_step(s: Session, run_id: str, action: str, i: dict, out: dict) -> None:
    """One call of the run, numbered from 1 (agent_run_step.n)."""
    s.execute(
        text(
            "INSERT INTO agent_run_step (run_id, n, tool, input, output) "
            "VALUES (:r, (SELECT coalesce(max(n), 0) + 1 FROM agent_run_step WHERE run_id = :r), :t, "
            "CAST(:i AS jsonb), CAST(:o AS jsonb))"
        ),
        {"r": run_id, "t": action, "i": json.dumps(i), "o": json.dumps(out, default=str)},
    )


def _failed_instruction(s: Session, case_id: str) -> bool:
    q = text("SELECT 1 FROM instruction WHERE case_id = :c AND status = 'failed' LIMIT 1")
    return s.execute(q, {"c": case_id}).first() is not None


def _context(s: Session, run: dict) -> CallContext | None:
    pctx = load_context(s)
    account = policy.account(run["state"].get("account") or "", pctx)
    if account is None:
        return None
    return CallContext(actor=Actor(account=account, ctx=pctx), session=s, preparer=run["agent"], run_id=run["id"])


def _preparer(run: dict, agent: registry.Agent, defn: chain.StageDef) -> str:
    """Who prepares a call: the stage's own agent in a `stage_chain` run, when the run's agent acts (autonomy `act`); the
    run's agent otherwise (an agent that only proposes or reads keeps its holds), and always in the `case_autopilot` alias."""
    if run["playbook"] == autopilot.NAME or agent.autonomy != "act":
        return str(run["agent"])
    return defn.agent_id


def _stage_record(
    s: Session, run: dict, stage: int, defn: chain.StageDef, st: dict[str, Any], case: dict, status: chain.Status
) -> None:
    chain.save_record(s, run["id"], run["case_id"], chain.build_record(defn, CHAIN[stage], st, case, status))


def _stage_done(s: Session, run: dict, stage: int, defn: chain.StageDef, st: dict[str, Any], case: dict, nxt: Done) -> str:
    """The stage's last step: its record, its confidence for the stages after it, then the next stage (or the end)."""
    _stage_record(s, run, stage, defn, st, case, "skipped" if nxt.skipped else "done")
    st.setdefault("confidence", {})[defn.id] = CHAIN[stage].confidence(st, case)
    n = int(run["step"]) + 1
    if stage + 1 >= len(CHAIN):
        stage_chain.finish(st)
        return _save(s, run, "done", n, st | {"note": "playbook finished"})
    stage_chain.advance_stage(st, stage)
    return _save(s, run, "running", n, st)


def step(s: Session, run_id: str) -> str:
    """Run the next step of a running run; returns its status afterwards."""
    run = get(s, run_id, for_update=True)
    if run is None:
        raise LookupError(f"no agent run {run_id}")
    st, n = dict(run["state"] or {}), int(run["step"])
    if run["status"] != "running":
        return str(run["status"])
    agent = registry.get(s, run["agent"])
    ctx = _context(s, run)
    if agent is None or ctx is None or limits.stopped(ctx, agent):
        return _save(s, run, "stopped", n, st | {"reason": "The agent is stopped."})
    case = store.get(s, run["case_id"]) if run["case_id"] else None
    if case is None:
        return _save(s, run, "failed", n, st | {"reason": f"No live case {run['case_id']}."})
    stage, sub = stage_chain.where(st, n)
    st |= {"stage": stage, "sub": sub, "legacy": run["playbook"] == autopilot.NAME}
    st["failed_instruction"] = _failed_instruction(s, case["id"])
    pack = live_pack(s, case)
    if (floor := chain.pack_rul_min(pack)) is not None:
        st["rul_min"] = floor
    nxt = stage_chain.next_step(stage, sub, st, case)
    if nxt is None:
        return _save(s, run, "done", n, st | {"note": "playbook finished"})
    try:
        defn = chain.stage_defs(pack)[stage]
    except ValueError as e:
        return _save(s, run, "failed", n, st | {"reason": str(e)})
    if isinstance(nxt, Skip):
        stage_chain.advance_step(st, stage, sub)
        return _save(s, run, "running", n + 1, st)
    if isinstance(nxt, Wait):
        _stage_record(s, run, stage, defn, st, case, "waiting")
        return _save(s, run, "waiting", n, st | {"waiting": nxt.reason})
    if isinstance(nxt, Halt):
        _stage_record(s, run, stage, defn, st, case, "skipped")
        stage_chain.finish(st)
        return _save(s, run, "done", n, st | {"note": nxt.note})
    if isinstance(nxt, Done):
        return _stage_done(s, run, stage, defn, st, case, nxt)
    ctx.preparer = _preparer(run, agent, defn)
    ctx.stage = chain.stage_context(defn, CHAIN[stage], st, case)
    r = invoke(nxt.action, nxt.input, ctx)
    _log_step(s, run_id, nxt.action, nxt.input, r)
    if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
        stage_chain.advance_step(st, stage, sub)
        _stage_record(s, run, stage, defn, st, case, "held")
        return _save(s, run, "waiting", n + 1, st | {"waiting": "proposal", "proposal": r["output"]["held"]})
    if r["ok"] or r["error"]["code"] == "duplicate":
        if r["ok"]:
            CHAIN[stage].record(sub, r["output"], st)
        stage_chain.advance_step(st, stage, sub)
        return _save(s, run, "running", n + 1, st)
    msg = r["error"]["message"]
    _stage_record(s, run, stage, defn, st, case, "exception")
    status = "stopped" if any(x in msg for x in STOPPING) else "failed"
    return _save(s, run, status, n, st | {"reason": msg})


def run_until_blocked(s: Session, run_id: str, max_steps: int = 50) -> str:
    """What the worker's job does: step until the run is no longer running, committing each step."""
    status = "running"
    for _ in range(max_steps):
        status = step(s, run_id)
        s.commit()
        if status != "running":
            break
    return status


def wake(s: Session, run_id: str) -> None:
    """A proposal of the run was decided (proposal.accept, proposal.reject)."""
    run = get(s, run_id, for_update=True)
    if run is None or run["status"] != "waiting" or (run["state"] or {}).get("waiting") != "proposal":
        return
    st = dict(run["state"])
    p = s.execute(text("SELECT status FROM agent_proposal WHERE id = :i"), {"i": st.get("proposal")}).scalar()
    st.pop("waiting", None)
    if p == "accepted":
        _save(s, run, "running", int(run["step"]), st)
        _enqueue(s, run_id)
    elif p == "rejected":
        _save(s, run, "stopped", int(run["step"]), st | {"reason": "A person rejected the proposal."})


def resume_waiting(s: Session, case_id: str) -> int:
    """The case was approved: every run waiting for that approval runs on. Returns how many."""
    ids = s.execute(
        text("SELECT id FROM agent_run WHERE case_id = :c AND status = 'waiting' AND state->>'waiting' = 'approval'"),
        {"c": case_id},
    ).scalars()
    n = 0
    for run_id in list(ids):
        run = get(s, run_id, for_update=True)
        if run is None:
            continue
        st = dict(run["state"])
        st.pop("waiting", None)
        _save(s, run, "running", int(run["step"]), st)
        _enqueue(s, run_id)
        n += 1
    return n


@after("decision.approve")
@after("decision.override")
def _approved(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    resume_waiting(ctx.session, str(i["case_id"]))
