"""The ten-stage journey of a case run (plan 9, P9-2.21; story X-05; registry entry I-12), for the run view.

    journey(run) -> [JourneyStage]   pure: ten stages in order, from the stage records and calls of one run

`run` is what the run view reads (`di.repositories.run_trace`, and a run of `di.services.screens.agents`): `stages`, the
stage records `{stage, agent, status, output, sources, reasons, confidence, threshold}`, and `calls`, the run's calls
`{n, tool, ok, held, input, stage}`. The chain's twelve stages become the journey's ten:

    1 lease_end   2 return_auth   3 transit   4 intake ("Received")   5 condition ("Inspect and grade")
    6 "Decide": demand, fit_for_use, valuation and disposition up to the submit, as sub-steps
    7 "Approve": the disposition stage's wait for an approval (or the standing policy's)
    8 follow_through ("Execute")   9 outcome   10 reconcile

Status of a stage record: `done` Completed, `skipped` Skipped, `waiting` Waiting for approval at 7 and Running elsewhere, `held`
Warning, `exception` Failed. A stage with no record is Queued, "not reached": nothing is invented for it. A record stored by
`analytics` (before P9-2.21) shows as stage 10.
Owns: the mapping and the nine fields of the stage panel (purpose, agent, activity, evidence, calls, result, validation, state
change, next step) with the model's reading. Never does: read the database, call an action or write anything (Next, Back and
Replay of the view change no row). Pure.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from di.services.agents.chain import AGENT_IDS
from di.services.agents.stage_context import StageId

Status = Literal["Queued", "Running", "Completed", "Waiting for approval", "Warning", "Failed", "Skipped"]
APPROVER = "Approver"  # the role that approves a decision (`decision.approve`; Admin may too)
DECIDE: tuple[StageId, ...] = ("demand", "fit_for_use", "valuation", "disposition")
# (number, name, the chain stages it shows, its purpose)
STAGES: tuple[tuple[int, str, tuple[StageId, ...], str], ...] = (
    (1, "Lease end", ("lease_end",), "Read the lease and the customer's intent for the asset."),
    (2, "Return authorised", ("return_auth",), "Read the return authorisation, its fees and the asset's book value."),
    (3, "Pickup and transit", ("transit",), "Follow the shipment until the goods are received."),
    (4, "Received", ("intake",), "Check that the return record is complete and ask for what is missing."),
    (5, "Inspect and grade", ("condition",), "Read the grade and the inspection of the asset's condition."),
    (6, "Decide", DECIDE, "Read demand and fit for use, value the routes and submit the decision."),
    (7, "Approve", ("disposition",), "A person with authority approves the decision."),
    (8, "Execute", ("follow_through",), "Follow the instructions through to the enterprise systems."),
    (9, "Outcome", ("outcome",), "Read the final acknowledgements, the actual costs and the realised value."),
    (10, "Reconcile", ("reconcile",), "Compare predicted and actual line by line and carry open items forward."),
)  # fmt: skip
MAPPED: dict[str, Status] = {"done": "Completed", "skipped": "Skipped", "held": "Warning", "exception": "Failed"}
SEVERITY: tuple[Status, ...] = ("Failed", "Warning", "Running", "Waiting for approval", "Queued", "Completed", "Skipped")


@dataclass(frozen=True)
class JourneyStage:
    n: int
    name: str
    status: Status
    agent: str
    purpose: str
    activity: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    validation: list[str] = field(default_factory=list)
    state_change: str = ""
    next_step: str = ""
    reading: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _records(run: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    by = {str(r["stage"]): r for r in run.get("stages") or []}
    if "analytics" in by and "reconcile" not in by:  # a record from before P9-2.21
        by["reconcile"] = by["analytics"]
    return by


def _out(rec: Mapping[str, Any]) -> Mapping[str, Any]:
    return rec.get("output") or {}


def _submitted(rec: Mapping[str, Any]) -> bool:
    out = _out(rec)
    return bool(out.get("submitted") or out.get("approved") or rec["status"] == "done")


def _status(rec: Mapping[str, Any], waiting: Status) -> Status:
    return waiting if rec["status"] == "waiting" else MAPPED.get(str(rec["status"]), "Running")


def _decide_status(recs: Mapping[str, Mapping[str, Any]]) -> Status:
    got = [recs[i] for i in DECIDE if i in recs]
    if not got:
        return "Queued"
    mapped: list[Status] = []
    for r in got:
        if r["stage"] == "disposition" and r["status"] == "waiting" and _submitted(r):
            mapped.append("Completed")  # submitted: what it waits for is the approval, stage 7
        else:
            mapped.append(_status(r, "Running"))
    if len(got) < len(DECIDE) and all(m in ("Completed", "Skipped") for m in mapped):
        return "Running"
    return next((s for s in SEVERITY if s in mapped), "Running")


def _approve_status(recs: Mapping[str, Mapping[str, Any]]) -> Status:
    rec = recs.get("disposition")
    if rec is None or not _submitted(rec):
        return "Queued"  # not submitted yet: the approval is not reached
    return _status(rec, "Waiting for approval")


def _stage_status(n: int, recs: Mapping[str, Mapping[str, Any]], ids: Sequence[StageId]) -> Status:
    if n == 6:
        return _decide_status(recs)
    if n == 7:
        return _approve_status(recs)
    rec = recs.get(ids[0])
    return "Queued" if rec is None else _status(rec, "Running")


def _calls(run: Mapping[str, Any], ids: Sequence[StageId], n: int) -> list[dict[str, Any]]:
    """The run's calls made in these stages (a call keeps its stage, `runtime._log_step`); the approval stage makes none."""
    if n == 7:
        return []
    mine = [c for c in run.get("calls") or [] if c.get("stage") in ids]
    return [{k: c.get(k) for k in ("n", "tool", "input", "ok", "held")} for c in mine]


def _clean(out: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in out.items() if k not in ("reading", "model")}


def _result(n: int, recs: Mapping[str, Mapping[str, Any]], ids: Sequence[StageId]) -> dict[str, Any]:
    if n == 6:
        return {i: _clean(_out(recs[i])) for i in DECIDE if i in recs}
    if n == 7:
        rec = recs.get("disposition")
        return {} if rec is None else {k: v for k, v in _clean(_out(rec)).items() if k in ("approved", "submitted")}
    rec = recs.get(ids[0])
    return {} if rec is None else _clean(_out(rec))


def _validation(recs: Sequence[Mapping[str, Any]]) -> list[str]:
    """Why a stage is held or failed, how sure it is against its threshold, and what its model's reading worries about."""
    out: list[str] = []
    for r in recs:
        out += [str(x.get("detail")) for x in r.get("reasons") or [] if x.get("detail")]
        if r.get("confidence") is not None:
            out.append(f"Confidence {float(r['confidence']):.2f} against a threshold of {float(r['threshold']):.2f}.")
        reading = _out(r).get("reading") or {}
        out += [f"{c.get('kind', 'concern')}: {c.get('text')}" for c in reading.get("concerns") or []]
    return out


def _reading(recs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for r in reversed(recs):
        reading = _out(r).get("reading")
        if reading:
            return {"model": _out(r).get("model"), "reading": reading}
    return None


def _activity(status: Status, recs: Sequence[Mapping[str, Any]], calls: Sequence[Mapping[str, Any]], n: int) -> str:
    if not recs and n != 7:
        return "Not reached."
    if status == "Queued":
        return "Not reached."
    if status == "Waiting for approval":
        return f"Waiting for an {APPROVER} to approve the decision."
    if status == "Skipped":
        reason = _out(recs[0]).get("reason") if recs else None
        return f"Skipped: {reason}." if reason else "Skipped."
    if status == "Warning":
        return "Held for a person to look at it."
    if status == "Failed":
        return "A call was refused."
    if status == "Running":
        return {6: "Working through its sub-steps.", 9: "Waiting for Finance to confirm the outcome."}.get(
            n, "Waiting on an outside event."
        )
    return f"Made {len(calls)} call{'' if len(calls) == 1 else 's'}." if calls else "Read the records; no call was needed."


def _state_change(status: Status, calls: Sequence[Mapping[str, Any]], n: int) -> str:
    writes = [str(c["tool"]) for c in calls if c.get("ok") and not c.get("held") and not str(c["tool"]).startswith("case.get")]
    if n == 7:
        return "The case is approved and its instructions are sent." if status == "Completed" else "None yet."
    if writes:
        return "Changed: " + ", ".join(dict.fromkeys(writes)) + "."
    return "No change to the case." if status in ("Completed", "Skipped") else "None yet."


def _next_step(i: int, status: Status, names: Sequence[str]) -> str:
    if status == "Waiting for approval":
        return f"An {APPROVER} approves or overrides the decision."
    if status in ("Warning", "Failed"):
        return "Blocked: a person resolves it, or escalates to an Admin. It never skips silently."
    if status == "Queued":
        return "Waits for the stages before it."
    if i + 1 >= len(names):
        return "End of the journey."
    return f"Next: {names[i + 1]}."


def journey(run: Mapping[str, Any]) -> list[JourneyStage]:
    """The ten stages of the run, in order."""
    recs = _records(run)
    names = [name for _, name, _, _ in STAGES]
    out: list[JourneyStage] = []
    for i, (n, name, ids, purpose) in enumerate(STAGES):
        mine = [recs[s] for s in ids if s in recs]
        status = _stage_status(n, recs, ids)
        calls = _calls(run, ids, n)
        agents = list(dict.fromkeys(str(r["agent"]) for r in mine)) or [AGENT_IDS[ids[0]]]
        out.append(
            JourneyStage(
                n=n, name=name, status=status, agent=", ".join(agents), purpose=purpose,
                activity=_activity(status, mine, calls, n),
                evidence=[dict(x) for r in mine for x in r.get("sources") or []],
                calls=calls, result=_result(n, recs, ids), validation=_validation(mine),
                state_change=_state_change(status, calls, n), next_step=_next_step(i, status, names), reading=_reading(mine),
            )
        )  # fmt: skip
    return out
