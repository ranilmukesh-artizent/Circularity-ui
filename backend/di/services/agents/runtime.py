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

Plan 9 (P9-2.4, I-10): the pipeline's hold policy (`di.services.actions.hold`) holds a stage call for a person by the stage's
autonomy, value, confidence and open exceptions, and every write of a tainted run (`ctx.taint`, from the run state); the held
reasons go to the stage record. `stage_confidence` gives a case with no condition confidence none, so it is never held for it.

Plan 9 (P9-2.18, R16): after a stage's deterministic step, when the router has a model for role `stage`, the stage's reasoner
(`stage_reasoner`) reads it and its reading joins the stage record (`_stage_record`, `_read_stage`); a held concern holds the
stage and every later write, and nothing is asked when no model answers.

Plan 9 (P9-2.24): no transaction stays open across a model call. The deterministic step is saved and committed (the stage
record, the run row), the `agent_run` row lock is released, the stage reasoner or the fraud review answers, and the lock is taken
again to write the reading (`_read_after`, `_review_off_lock`): a run that moved meanwhile is re-read, never written over. The
deduped `queue.plan` job is enqueued after the reading. A tainted fraud review taints the run, as a stage reading does.

Plan 9 (P9-2.2, I-8): a playbook registered in `playbook_versions` is an LLM playbook: `step` runs it through the
`AgentLoop` (`loop_runner()`; tests swap it with `set_loop`). A call the pipeline holds is a deferred call: the run waits with
`state.deferred = {tool_call_id: proposal_id}`, and `wake` resumes the loop with each accepted proposal's output once all are
decided. The run state keeps `playbook_version`; a resume whose version is gone stops the run.

Plan 9 (P9-8.7): `adapter_author` is an LLM playbook with its own steps (`playbooks/adapter_author.run`): the model drafts a
connector spec, code checks it, and one proposal holds `registry.saveEntry` for a person; a legacy `wake` runs it on to done.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import di.repositories.cases  # registers case.evidence (the worker imports only what its jobs need)
import di.services.actions.decisions  # registers evidence.request, case.reevaluate, decision.submit
import di.services.actions.execution  # registers instruction.resend
import di.services.actions.lifecycle  # noqa: F401 - registers transit.flagDelay (P9-2.20)
from di.core import jobs, policy, tracing
from di.core.auth import load_context
from di.core.config import get_settings
from di.repositories import stage_outcomes
from di.repositories.live_rules import live_pack
from di.services.actions.fraud import review_case, triage_case  # also registers fraud.hold in the worker
from di.services.actions.pipeline import Actor, CallContext, after, invoke
from di.services.agents import calibrate, chain, lifecycle_evidence, limits, playbook_versions, registry, stage_reasoner
from di.services.agents.forbidden import forbidden
from di.services.agents.fraud_review import review_fraud
from di.services.agents.loop import AgentLoop, LoopSpec
from di.services.agents.playbooks import adapter_author, stage_chain
from di.services.agents.playbooks import case_autopilot as autopilot
from di.services.agents.playbooks import stage_reasoner as stage_playbook
from di.services.agents.playbooks.case_autopilot import Done, Halt, Skip, Wait
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.agents.stage_context import STAGE_IDS, StageContext
from di.services.agents.stages import CHAIN, disposition, outcome
from di.services.cases import store
from di.services.llm import router
from di.services.modeler.evidence import evidence_of
from di.services.modeler.fraud import FraudResult

log = logging.getLogger(__name__)
PLAYBOOKS = {autopilot.NAME: stage_chain, stage_chain.NAME: stage_chain}  # case_autopilot is an alias of the chain
JOB = "agent.step"
QUEUE_JOB = "queue.plan"  # P9-2.8: plans a pack's open queue of an org; its end wakes the runs waiting `queue`
_REACHED = (*autopilot.ACTIONS, *stage_chain.ACTIONS, *adapter_author.ACTIONS, *(a for m in CHAIN for a in m.ACTIONS))
_FORBIDDEN = [a for a in _REACHED if forbidden(a)]
if _FORBIDDEN:
    raise RuntimeError(f"playbooks reach actions no agent may run: {_FORBIDDEN}")
READ_STATUSES = ("done", "waiting", "held")  # the stage records a stage's model reads (P9-2.18)
STOPPING = ("Run limit reached", "is stopped by Admin")  # refusals that stop a run rather than fail it


_LOOP: AgentLoop | None = None


def set_loop(loop: AgentLoop | None) -> None:
    """Use `loop` for LLM playbooks (a test's scripted model); None goes back to the Pydantic AI adapter."""
    global _LOOP
    _LOOP = loop


def loop_runner() -> AgentLoop:
    return _LOOP if _LOOP is not None else PydanticAILoop()


def _enqueue(s: Session, run_id: str) -> None:
    jobs.enqueue(s, JOB, {"run_id": run_id}, dedupe_key=f"{JOB}:{run_id}")


def start(s: Session, agent: str, playbook: str, case_id: str | None, *, account: str, propose_only: bool = False) -> str:
    llm = playbook not in PLAYBOOKS and playbook_versions.known(playbook)
    if playbook not in PLAYBOOKS and not llm:
        raise ValueError(f"unknown playbook {playbook!r}")
    if registry.get(s, agent) is None:
        raise ValueError(f"unknown agent {agent!r}")
    first = {"playbook_version": playbook_versions.latest(playbook)} if llm else stage_chain.start_state()
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
            "st": json.dumps({"account": account} | ({"propose_only": True} if propose_only else {}) | first),
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


def _log_step(s: Session, run_id: str, action: str, i: dict, out: dict, stage: str | None = None) -> None:
    """One call of the run, numbered from 1 (agent_run_step.n). A call of a stage keeps the stage id in its output (`stage`),
    so the journey (P9-2.21) shows each call under its own stage."""
    s.execute(
        text(
            "INSERT INTO agent_run_step (run_id, n, tool, input, output) "
            "VALUES (:r, (SELECT coalesce(max(n), 0) + 1 FROM agent_run_step WHERE run_id = :r), :t, "
            "CAST(:i AS jsonb), CAST(:o AS jsonb))"
        ),
        {"r": run_id, "t": action, "i": json.dumps(i), "o": json.dumps(out | ({"stage": stage} if stage else {}), default=str)},
    )


def _failed_instruction(s: Session, case_id: str) -> bool:
    q = text("SELECT 1 FROM instruction WHERE case_id = :c AND status = 'failed' LIMIT 1")
    return s.execute(q, {"c": case_id}).first() is not None


def _context(s: Session, run: dict) -> CallContext | None:
    pctx = load_context(s)
    account = policy.account(run["state"].get("account") or "", pctx)
    if account is None:
        return None
    taint = bool(
        (run["state"] or {}).get("tainted")
    )  # an untrusted tool returned in an earlier loop: every write is held (P9-2.4)
    return CallContext(actor=Actor(account=account, ctx=pctx), session=s, preparer=run["agent"], run_id=run["id"], taint=taint)


def _preparer(run: dict, agent: registry.Agent, defn: chain.StageDef) -> str:
    """Who prepares a call: the stage's own agent in a `stage_chain` run, when the run's agent acts (autonomy `act`); the
    run's agent otherwise (an agent that only proposes or reads keeps its holds), and always in the `case_autopilot` alias."""
    if run["playbook"] == autopilot.NAME or agent.autonomy != "act":
        return str(run["agent"])
    return defn.agent_id


def _stage_record(
    s: Session,
    run: dict,
    stage: int,
    defn: chain.StageDef,
    st: dict[str, Any],
    case: dict,
    status: chain.Status,
    reasons: list[dict[str, Any]] | None = None,
) -> chain.StageRecord:
    """The stage's deterministic record, saved. A reading the run already holds is applied; asking the model is not done here
    (no transaction may stay open across a model call): `_read_after` does it once the step is saved (P9-2.24)."""
    rec = chain.build_record(defn, CHAIN[stage], st, case, status)
    rec.reasons = reasons or []  # why the hold policy held a call of the stage (P9-2.4)
    cached = (st.get("readings") or {}).get(defn.id)
    if status in READ_STATUSES and defn.id in stage_playbook.REASONED and cached is not None:
        chain.apply_reading(rec, cached, st)
    chain.save_record(s, run["id"], run["case_id"], rec)
    return rec


def _stage_loop(s: Session) -> AgentLoop | None:
    """The loop that reads a stage (P9-2.18): a scripted one (tests), else the router's when it has a model for role `stage`;
    None leaves every stage record as the rules wrote it."""
    if _LOOP is not None:
        return _LOOP
    return PydanticAILoop() if router.chain_for(s, "stage") else None


def _save_state(s: Session, run_id: str, st: dict[str, Any]) -> None:
    """Write the run's state only: never its status or step (a person's accept may have moved those)."""
    s.execute(
        text("UPDATE agent_run SET state = CAST(:st AS jsonb), updated_at = now() WHERE id = :i"),
        {"st": json.dumps(st, default=str), "i": run_id},
    )


def _read_after(s: Session, run: dict, defn: chain.StageDef, case: dict, rec: chain.StageRecord) -> None:
    """After the stage's step is saved: its model's reading, asked once per stage and run (a miss too: the run state keeps it),
    added to the record (P9-2.18). P9-2.24: the step (its record, the run row) is committed first and the `agent_run` row lock
    is released, so no transaction stays open across the model call and a person's accept never waits for it. The lock is then
    taken again and the run re-read; the reading goes to the stage's record and to the `readings`, `concerns` and `tainted`
    keys of the fresh state only, never over the run's status or step. An untrusted tool the reasoner read taints the run's
    later writes (P9-2.4)."""
    if rec.status not in READ_STATUSES or defn.id not in stage_playbook.REASONED:
        return
    run_id = run["id"]
    now = get(s, run_id)
    if now is None or defn.id in ((now["state"] or {}).get("readings") or {}):
        return  # gone, or read already (a cached miss included)
    loop = _stage_loop(s)
    ctx = _context(s, now) if loop is not None else None
    got = None
    if loop is not None and ctx is not None:
        s.commit()  # nothing of this session is open or locked while the model answers
        got = stage_reasoner.reason_stage(s, ctx, defn.id, case, rec.output, loop=loop)
    fresh = get(s, run_id, for_update=True)
    if fresh is None:
        return
    st = dict(fresh["state"] or {})
    readings = st.setdefault("readings", {})
    if defn.id in readings:
        return  # another worker read it meanwhile
    readings[defn.id] = None
    if got is not None:
        entry: dict[str, Any] = {"reading": got.reading.model_dump(mode="json"), "model": got.model}
        if got.dropped:  # concerns that cited no source: kept where a person can see them (P9-2.24)
            entry["dropped"] = [c.model_dump(mode="json") for c in got.dropped]
        readings[defn.id] = entry
        st["tainted"] = bool(st.get("tainted")) or got.tainted
        chain.apply_reading(rec, entry, st)
        chain.save_record(s, run_id, run["case_id"], rec)
    _save_state(s, run_id, st)


def _review_off_lock(s: Session, run: dict, ctx: CallContext, case: dict, result: FraudResult, st: dict[str, Any]) -> str | None:
    """The model's fraud review of the intake triage (P9-2.19), asked with no transaction open (P9-2.24): the step so far is
    committed, the review is asked, the run row is locked again and re-read. A run that moved meanwhile (stopped, woken, a
    state a person changed) is left alone: its status is returned and nothing is written, the step runs again from the run as it
    is. Otherwise `st["fraud_review"]` holds the review (or None) and a tainted review taints the run, now and for this step's
    own calls; None is returned."""
    loop = loop_runner()
    s.commit()
    got = review_fraud(s, ctx, case, result, loop=loop)
    fresh = get(s, run["id"], for_update=True)
    if fresh is None:
        return "stopped"
    if fresh["status"] != "running" or int(fresh["step"]) != int(run["step"]) or (fresh["state"] or {}) != (run["state"] or {}):
        return str(fresh["status"])
    st["fraud_review"] = got.model_dump(mode="json") if got is not None else None
    if got is not None and got.tainted:
        st["tainted"] = True
        ctx.taint = True
    return None


def stage_confidence(ctx_stage: StageContext, case: dict) -> StageContext:
    """The stage context the hold policy reads, with the confidence rule scoped to a case that has a confidence (P9-2.4).
    - condition: a case without a `grade` evidence record (an industrial case has none) is read as 0.0 by the stage module,
      which would hold every call at a threshold; it has no confidence, so None here.
    - intake: its confidence is how complete the evidence is, and its one write (`evidence.request`) is the remedy for a low
      value, so holding it for that would stop the fix; None here.
    - lease end, return authorised, transit (P9-2.20): the same, their writes ask for the missing record or flag a late one.
    The industrial demo's cases and RT-1048 are therefore never held for a confidence they do not have."""
    if (ctx_stage.stage == "condition" and evidence_of(case, "grade") is None) or ctx_stage.stage in ("intake", *chain.LIFECYCLE):
        ctx_stage.confidence = None
    return ctx_stage


def calibrated(s: Session, ctx_stage: StageContext, pack: str) -> StageContext:
    """The stage context with its raw confidence passed through the pack stage's active calibration (P9-2.9, story X-05).
    No active calibration, or no confidence: unchanged, so the stage keeps its raw one ("not calibrated yet"). The stage's
    record keeps the raw value, which is what the next calibration is fitted on."""
    if ctx_stage.confidence is None:
        return ctx_stage
    steps = stage_outcomes.active_steps(s, pack, ctx_stage.stage)
    if steps is not None:
        ctx_stage.confidence = round(calibrate.apply(steps, ctx_stage.confidence), 3)
    return ctx_stage


def _stage_done(s: Session, run: dict, stage: int, defn: chain.StageDef, st: dict[str, Any], case: dict, nxt: Done) -> str:
    """The stage's last step: its record, its confidence for the stages after it, then the next stage (or the end)."""
    rec = _stage_record(s, run, stage, defn, st, case, "skipped" if nxt.skipped else "done")
    st.setdefault("confidence", {})[defn.id] = CHAIN[stage].confidence(st, case)
    n = int(run["step"]) + 1
    if stage + 1 >= len(CHAIN):
        stage_chain.finish(st)
        status = _save(s, run, "done", n, st | {"note": "playbook finished"})
    else:
        stage_chain.advance_stage(st, stage)
        status = _save(s, run, "running", n, st)
    _read_after(s, run, defn, case, rec)
    return status


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
    if run["playbook"] == adapter_author.NAME:  # P9-8.7: its own steps, not one tool loop
        status, new = adapter_author.run(s, ctx, st, loop_runner())
        return _save(s, run, status, n + 1, new)
    if run["playbook"] not in PLAYBOOKS:
        return _llm_step(s, run, ctx)
    case = store.get(s, run["case_id"]) if run["case_id"] else None
    if case is None:
        return _save(s, run, "failed", n, st | {"reason": f"No live case {run['case_id']}."})
    stage, sub = stage_chain.where(st, n)
    sid = STAGE_IDS[stage] if stage < len(STAGE_IDS) else str(stage)
    # one `stage` span per stage and run: later steps of the stage update its row (P9-2.6, I-12)
    with tracing.span(
        s, f"stage {sid}", kind="stage", run_id=run_id, span_id=f"{run_id}:{sid}",
        attrs={"di.stage": sid, "di.agent": run["agent"]},
    ):  # fmt: skip
        return _stage_step(s, run, agent, ctx, case, stage, sub)


def _stage_step(s: Session, run: dict, agent: registry.Agent, ctx: CallContext, case: dict, stage: int, sub: int) -> str:
    """The step of a `stage_chain` run once its stage is known (inside the stage's span)."""
    run_id, sid = run["id"], STAGE_IDS[stage]
    st, n = dict(run["state"] or {}), int(run["step"])
    st |= {"stage": stage, "sub": sub, "legacy": run["playbook"] == autopilot.NAME}
    st["failed_instruction"] = _failed_instruction(s, case["id"])
    pack = live_pack(s, case)
    if (floor := chain.pack_rul_min(pack)) is not None:
        st["rul_min"] = floor
    st["queue_planner"] = disposition.planner_name(pack)  # the disposition stage waits for the queue plan (P9-2.8)
    if sid == "intake" and pack.fraud is not None:  # the fraud triage of the intake stage (P9-2.11): intake holds on it
        result = triage_case(s, case, pack)
        due = "fraud_review" not in st and not case.get("fraud")  # the model reads the case off the lock (P9-2.24)
        if due and (moved := _review_off_lock(s, run, ctx, case, result, st)) is not None:
            return moved
        st["fraud"] = review_case(s, ctx, case, result, st).as_dict()  # the model may add a hold (P9-2.19)
    if sid in chain.LIFECYCLE:  # the lease, return and shipment records of the asset (P9-2.20); none: nothing changes
        lifecycle_evidence.refresh(s, case, st)
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
        rec = _stage_record(
            s, run, stage, defn, st, case, "held" if nxt.reason == "fraud" else "waiting"
        )  # a fraud hold is a hold (P9-2.11)
        status = _save(s, run, "waiting", n, st | {"waiting": nxt.reason})
        try:
            _read_after(s, run, defn, case, rec)
        finally:
            if nxt.reason == "queue":  # the deduped job is the fan-in: one plan for every case waiting in this pack and org
                key = f"{QUEUE_JOB}:{pack.key}:{case['owner']}"  # enqueued after the reading, so the plan cannot wake the run
                jobs.enqueue(s, QUEUE_JOB, {"pack": pack.key, "org_unit_id": case["owner"]}, dedupe_key=key)  # before it
        return status
    if isinstance(nxt, Halt):
        _stage_record(s, run, stage, defn, st, case, "skipped")
        stage_chain.finish(st)
        return _save(s, run, "done", n, st | {"note": nxt.note})
    if isinstance(nxt, Done):
        return _stage_done(s, run, stage, defn, st, case, nxt)
    ctx.preparer = _preparer(run, agent, defn)
    ctx.stage = calibrated(s, stage_confidence(chain.stage_context(defn, CHAIN[stage], st, case), case), pack.key)
    r = invoke(nxt.action, nxt.input, ctx)
    _log_step(s, run_id, nxt.action, nxt.input, r, sid)
    if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
        stage_chain.advance_step(st, stage, sub)
        rec = _stage_record(s, run, stage, defn, st, case, "held", r["output"].get("reasons"))
        status = _save(s, run, "waiting", n + 1, st | {"waiting": "proposal", "proposal": r["output"]["held"]})
        _read_after(s, run, defn, case, rec)
        return status
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
    run = get(s, run_id)
    # one `run` span per run: each burst of steps moves its end (P9-2.6, I-12)
    with tracing.span(
        s, "agent run", kind="run", run_id=run_id, span_id=run_id,
        attrs={"di.agent": run["agent"] if run else None, "di.playbook": run["playbook"] if run else None},
    ) as sp:  # fmt: skip
        for _ in range(max_steps):
            status = step(s, run_id)
            s.commit()
            if status != "running":
                break
        sp.attrs["di.status"] = status
    s.commit()
    return status


def wake(s: Session, run_id: str) -> None:
    """A proposal of the run was decided (proposal.accept, proposal.reject)."""
    run = get(s, run_id, for_update=True)
    if run is None or run["status"] != "waiting" or (run["state"] or {}).get("waiting") != "proposal":
        return
    st = dict(run["state"])
    if st.get("deferred"):  # an LLM run: it resumes once every proposal it waits for is decided
        return _wake_loop(s, run, st)
    p = s.execute(text("SELECT status FROM agent_proposal WHERE id = :i"), {"i": st.get("proposal")}).scalar()
    st.pop("waiting", None)
    if p == "accepted":
        _save(s, run, "running", int(run["step"]), st)
        _enqueue(s, run_id)
    elif p == "rejected":
        _save(s, run, "stopped", int(run["step"]), st | {"reason": "A person rejected the proposal."})


def resume_waiting(s: Session, case_id: str, waiting: str = "approval") -> int:
    """The case was approved (or, with `waiting="fraud"`, released from a fraud hold): every run waiting for that runs on.
    Returns how many."""
    ids = s.execute(
        text("SELECT id FROM agent_run WHERE case_id = :c AND status = 'waiting' AND state->>'waiting' = :w"),
        {"c": case_id, "w": waiting},
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


def wake_queue(s: Session, pack: str, org_unit_id: str) -> list[str]:
    """The queue of the pack in the org was planned (job `queue.plan`): every run waiting `queue` on a case of that pack and
    org runs on (a new job each). Returns their ids."""
    q = text(
        "SELECT r.id FROM agent_run r JOIN case_record c ON c.id = r.case_id "
        "WHERE r.status = 'waiting' AND r.state->>'waiting' = 'queue' AND c.owner = :o AND c.data ->> 'template' = :p "
        "ORDER BY r.id"
    )
    woken: list[str] = []
    for run_id in list(s.execute(q, {"o": org_unit_id, "p": pack}).scalars()):
        run = get(s, run_id, for_update=True)
        if run is None or run["status"] != "waiting":
            continue
        st = dict(run["state"])
        st.pop("waiting", None)
        _save(s, run, "running", int(run["step"]), st)
        _enqueue(s, run_id)
        woken.append(run_id)
    return woken


# --- LLM playbooks (P9-2.2) ------------------------------------------------------------------------------------------


def _accepted_results(s: Session, st: dict[str, Any]) -> dict[str, Any]:
    """What each deferred call now has: an accepted proposal's output (what the person's call returned), or the
    person's answer to a question."""
    out: dict[str, Any] = dict(st.get("answers") or {})
    for call_id, pid in (st.get("deferred") or {}).items():
        res = s.execute(text("SELECT result FROM agent_proposal WHERE id = :i AND status = 'accepted'"), {"i": pid}).scalar()
        out[call_id] = (res or {}).get("output")
    return out


def _wake_loop(s: Session, run: dict, st: dict[str, Any]) -> None:
    statuses = [
        s.execute(text("SELECT status FROM agent_proposal WHERE id = :i"), {"i": pid}).scalar() for pid in st["deferred"].values()
    ]
    rest = {k: v for k, v in st.items() if k != "waiting"}
    if "rejected" in statuses:
        _save(s, run, "stopped", int(run["step"]), rest | {"reason": "A person rejected the proposal."})
    elif all(x == "accepted" for x in statuses):
        _save(s, run, "running", int(run["step"]), rest)
        _enqueue(s, run["id"])


def _loop_prompt(run: dict, st: dict[str, Any]) -> str:
    return str(st.get("prompt") or (f"Work on case {run['case_id']}." if run["case_id"] else "Begin."))


def _llm_step(s: Session, run: dict, ctx: CallContext) -> str:
    """One run of the loop for an LLM playbook: it ends done, waiting (a deferred call), stopped or failed."""
    st, n = dict(run["state"] or {}), int(run["step"])
    name, version = run["playbook"], str(st.get("playbook_version"))
    spec: LoopSpec | None = playbook_versions.spec_for(name, version)
    if spec is None:
        now = playbook_versions.latest(name)
        why = f"The playbook changed since this run started (v{version}, now v{now})."
        return _save(s, run, "stopped", n, st | {"reason": why})
    started = s.execute(text("SELECT 1 FROM agent_run_message WHERE run_id = :r LIMIT 1"), {"r": run["id"]}).first()
    resume = _accepted_results(s, st) if started else None
    try:
        res = loop_runner().run(s, spec, _loop_prompt(run, st), ctx=ctx, resume=resume)
    except Exception as e:  # noqa: BLE001 - a provider error, a tool out of retries, the turn limit: the run fails, the reason is kept
        log.warning("agent run %s: the loop failed: %s", run["id"], e)
        s.rollback()
        return _save(s, run, "failed", n, st | {"reason": f"The model loop failed: {str(e)[:300]}"})
    if res.model is None:
        return _save(s, run, "stopped", n, st | {"reason": "No language model is configured."})
    st = {k: v for k, v in st.items() if k not in ("deferred", "questions", "answers", "waiting")}
    used = dict(st.get("usage") or {})
    st["usage"] = {k: int(used.get(k, 0)) + v for k, v in res.usage.items()}
    st["model"], st["tainted"] = res.model, bool(st.get("tainted")) or res.tainted
    if res.deferred:
        ext = {d.tool_call_id: d.proposal_id for d in res.deferred if d.kind == "external"}
        asks = {d.tool_call_id: d.question for d in res.deferred if d.kind == "question"}
        extra: dict[str, Any] = {"waiting": "proposal" if ext else "question", "deferred": ext}
        if asks:
            extra["questions"] = asks
        if ext:
            extra["proposal"] = next(iter(ext.values()))
        return _save(s, run, "waiting", n + 1, st | extra)
    out = res.output.model_dump(mode="json") if res.output is not None else None
    return _save(s, run, "done", n + 1, st | {"output": out, "note": "playbook finished"})


@after("outcome.confirm")
def _confirmed(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    """Finance confirmed the outcome (P9-2.21): the runs waiting in the outcome stage run on."""
    resume_waiting(ctx.session, str(i["case_id"]), outcome.WAITING)


@after("decision.approve")
@after("decision.override")
def _approved(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    resume_waiting(ctx.session, str(i["case_id"]))
