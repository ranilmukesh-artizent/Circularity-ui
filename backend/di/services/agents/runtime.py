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
from di.services.actions.pipeline import Actor, CallContext, after, invoke
from di.services.agents import limits, registry
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.playbooks import case_autopilot as autopilot
from di.services.cases import store

log = logging.getLogger(__name__)
PLAYBOOKS = {autopilot.NAME: autopilot}
JOB = "agent.step"
_FORBIDDEN = [a for p in PLAYBOOKS.values() for a in p.ACTIONS if a.startswith(FORBIDDEN_ACTIONS)]
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
        {"i": run_id, "a": agent, "p": playbook, "c": case_id, "st": json.dumps({"account": account})},
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
    pb = PLAYBOOKS[run["playbook"]]
    nxt = pb.next_step(n, st, case, _failed_instruction(s, case["id"]))
    if isinstance(nxt, pb.Skip):
        return _save(s, run, "running", n + 1, st)
    if isinstance(nxt, pb.Wait):
        return _save(s, run, "waiting", n, st | {"waiting": nxt.reason})
    if isinstance(nxt, pb.Done):
        return _save(s, run, "done", n, st | {"note": nxt.note})
    r = invoke(nxt.action, nxt.input, ctx)
    _log_step(s, run_id, nxt.action, nxt.input, r)
    if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
        return _save(s, run, "waiting", n + 1, st | {"waiting": "proposal", "proposal": r["output"]["held"]})
    if r["ok"] or r["error"]["code"] == "duplicate":
        if r["ok"]:
            pb.record(n, r["output"], st)
        return _save(s, run, "running", n + 1, st)
    msg = r["error"]["message"]
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
