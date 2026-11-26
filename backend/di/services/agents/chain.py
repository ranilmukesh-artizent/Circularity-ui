"""The stage chain (plan 9, P9-2.1; registry entry I-7; research F section 8a): one agent per stage, application code
picking the next stage, each stage leaving a typed record.

    stage_defs(pack) -> [StageDef]       pure: the twelve stages of the effective pack (after the org's overlay, I-4), with
                                         the D1 defaults for whatever the pack does not say
    build_record(defn, mod, st, case, status) -> StageRecord      pure: what a stage module says about the case now
    save_record / records_of             the table `agent_stage_record` (migration 0034), one row per (run, stage)
    run_chain(s, case_id, account=...)   starts a `stage_chain` run (agent `recover-chain`), runs it until it is blocked
                                         and returns its records; the worker path (`agent.step`) is the same walk

The stage outputs live in `agent_stage_record`, a blackboard, not in messages between agents. No model is involved: the
stage modules (`di.services.agents.stages`) are pure, the runtime runs their calls through the action pipeline as the
stage's agent. Since P9-2.18, when the router has a model for role `stage` the runtime asks the stage's reasoner
(`di.services.agents.stage_reasoner`) to read the stage after its deterministic step, and `apply_reading` adds the reading to
the record (`kind` `llm`); no model leaves the record as it was. The chain calls the one decider (`decide_case`, I-6) only
through the actions it runs (R19), and never an
action in `FORBIDDEN_ACTIONS` (AGENTS.md rule 10). Holding by stage autonomy and confidence arrives with P9-2.4.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.agents.stage_context import LEGACY_STAGE_IDS, STAGE_IDS, Autonomy, StageContext, StageId, StageKind
from di.services.agents.stages import CHAIN, StageModule, disposition
from di.services.modeler.pack import Pack
from di.services.modeler.stages import StageKey

__all__ = [
    "Autonomy", "ChainRun", "StageDef", "StageId", "StageKind", "StageRecord", "Status", "apply_reading",
    "build_record", "case_value",
    "pack_rul_min", "records_of", "run_chain", "save_record", "stage_context", "stage_defs",
]  # fmt: skip

Status = Literal["done", "skipped", "held", "waiting", "exception"]
CHAIN_AGENT = "recover-chain"
THRESHOLD_RANGE = (0.65, 0.85)
DEFAULT_THRESHOLD = 0.75
# The D1 defaults: who runs each stage, how alone it may act (README D1; F section 8b).
AGENT_IDS: dict[StageId, str] = {
    "lease_end": "stage-lease", "return_auth": "stage-return", "transit": "stage-transit",
    "intake": "stage-intake", "condition": "stage-condition", "demand": "stage-demand", "fit_for_use": "stage-fit",
    "valuation": "stage-valuation", "disposition": "stage-disposition", "follow_through": "stage-follow",
    "outcome": "stage-outcome", "reconcile": "stage-reconcile",
}  # fmt: skip
DEFAULT_AUTONOMY: dict[StageId, Autonomy] = {
    "lease_end": "alone", "return_auth": "limits", "transit": "alone",
    "intake": "alone", "condition": "limits", "demand": "alone", "fit_for_use": "limits", "valuation": "alone",
    "disposition": "limits", "follow_through": "limits", "outcome": "limits", "reconcile": "alone",
}  # fmt: skip
LIFECYCLE: tuple[StageId, ...] = ("lease_end", "return_auth", "transit")  # stages 1 to 3 of the journey, before intake
# The pack's seven stages (B 1.2) and the chain's twelve: the pack stage whose threshold a chain stage takes, and (where the
# two correspond one to one) whose autonomy. Demand, fit-for-use and the three lifecycle stages have no stage of their own in
# the pack: they take the match (or receive) stage's threshold and the D1 autonomy.
THRESHOLD_FROM: dict[StageId, StageKey] = {
    "lease_end": "receive", "return_auth": "receive", "transit": "receive", "intake": "receive",
    "condition": "condition", "demand": "match", "fit_for_use": "match", "valuation": "value",
    "disposition": "decide", "follow_through": "execute", "outcome": "close", "reconcile": "close",
}  # fmt: skip
AUTONOMY_FROM: dict[StageId, StageKey] = {
    k: v for k, v in THRESHOLD_FROM.items() if k not in ("demand", "fit_for_use", "outcome", *LIFECYCLE)
}


@dataclass(frozen=True)
class StageDef:
    id: StageId
    agent_id: str
    kind: StageKind
    autonomy: Autonomy
    threshold: float
    value_limit: Decimal | None
    bulk_limit: int | None
    tools: tuple[str, ...]


@dataclass
class StageRecord:
    stage: StageId
    agent: str
    kind: StageKind
    autonomy: Autonomy
    status: Status
    output: dict[str, Any]
    confidence: float | None
    threshold: float
    sources: list[dict[str, Any]]
    reasons: list[dict[str, Any]] = field(default_factory=list)  # written by the hold check (P9-2.4)


@dataclass
class ChainRun:
    run_id: str
    status: str
    stages: list[StageRecord]


def stage_defs(pack: Pack) -> list[StageDef]:
    """The twelve stage definitions of the pack, in chain order. A threshold outside 0.65 to 0.85 raises ValueError (the
    overlay validator, P9-1.3, refuses it first); a pack without a stage list gets the defaults."""
    by_key = {s.key: s for s in pack.stages}
    out: list[StageDef] = []
    for module in CHAIN:
        sid = module.ID
        threshold = by_key[THRESHOLD_FROM[sid]].confidence if THRESHOLD_FROM[sid] in by_key else DEFAULT_THRESHOLD
        if not THRESHOLD_RANGE[0] <= threshold <= THRESHOLD_RANGE[1]:
            raise ValueError(f"the {sid} threshold {threshold} is outside {THRESHOLD_RANGE[0]} to {THRESHOLD_RANGE[1]}")
        akey = AUTONOMY_FROM.get(sid)
        own = by_key.get(akey) if akey else None
        out.append(
            StageDef(
                id=sid, agent_id=AGENT_IDS[sid],
                kind="queue" if sid == "disposition" and disposition.planner_name(pack) else "deterministic",
                autonomy=own.autonomy if own else DEFAULT_AUTONOMY[sid],
                threshold=float(threshold), value_limit=None, bulk_limit=None, tools=tuple(module.ACTIONS),
            )
        )  # fmt: skip
    return out


def pack_rul_min(pack: Pack) -> float | None:
    """The pack's remaining-life floor for a harvested part (the Quality-owned `valuer.rulMin` parameter, P9-3.20, else `rulMin`
    of the valuer's base parameters), if it names one."""
    own = pack.customer_layer.params.get("valuer.rulMin")
    v = own.value if own is not None else (pack.valuer.params.get("basep") or {}).get("rulMin")
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def case_value(case: Mapping[str, Any]) -> Decimal | None:
    """The net of the case's recommended route, the money a decision on it moves (None before it is valued)."""
    net = (case.get("chosen") or case.get("recommendation") or {}).get("net")
    return Decimal(str(net)) if isinstance(net, int | float) and not isinstance(net, bool) else None


def stage_context(defn: StageDef, mod: StageModule, st: dict[str, Any], case: Mapping[str, Any]) -> StageContext:
    """What the pipeline is told about a call made in this stage (`CallContext.stage`)."""
    return StageContext(
        stage=defn.id, autonomy=defn.autonomy, confidence=mod.confidence(st, case), threshold=defn.threshold,
        value=case_value(case), value_limit=defn.value_limit, bulk_limit=defn.bulk_limit,
        guardrail_holds=[str(h["id"]) for h in case.get("approvalHolds") or [] if isinstance(h, Mapping)],  # P9-11.9
        model_concerns=[t for texts in (st.get("concerns") or {}).values() for t in texts],
        value_holds=[
            str(h["reason"]) for h in case.get("approvalHolds") or [] if isinstance(h, Mapping) and h.get("kind") == "value"
        ],  # P9-9.11: an approval limit the decision is over (a used car's recon)
    )  # fmt: skip


def apply_reading(rec: StageRecord, entry: Mapping[str, Any], st: dict[str, Any]) -> None:
    """Add a stage model's reading (`stage_reasoner.StageReading` as JSON, with the `model` that answered) to the stage's record
    (P9-2.18). The deterministic output, confidence and sources are kept as they are; the reading goes to `output.reading`
    and the model to `output.model`, and a `deterministic` record becomes `llm`. A concern with `hold` holds the stage (a
    status `done` or `waiting` becomes `held`, reason `model_concern`) and, through `st["concerns"]`, every later write of the
    run. It only adds caution: a record that was held stays held, and a reading with no concern changes nothing else."""
    reading = dict(entry["reading"])
    rec.output = {**rec.output, "reading": reading, "model": entry.get("model")}
    if rec.kind == "deterministic":
        rec.kind = "llm"
    held = [c["text"] for c in reading.get("concerns") or [] if c.get("hold")]
    if held:
        st.setdefault("concerns", {})[rec.stage] = held
        rec.reasons = [*rec.reasons, *({"reason": "model_concern", "detail": t} for t in held)]
        if rec.status in ("done", "waiting"):
            rec.status = "held"


def build_record(defn: StageDef, mod: StageModule, st: dict[str, Any], case: Mapping[str, Any], status: Status) -> StageRecord:
    c = mod.confidence(st, case)
    return StageRecord(
        stage=defn.id, agent=defn.agent_id, kind=defn.kind, autonomy=defn.autonomy, status=status,
        output=mod.output(st, case), confidence=None if c is None else round(max(0.0, min(1.0, c)), 3),
        threshold=defn.threshold, sources=mod.sources(st, case),
    )  # fmt: skip


UPSERT = text(
    "INSERT INTO agent_stage_record (run_id, stage, case_id, agent, kind, autonomy, status, output, confidence, threshold, "
    "sources, reasons) VALUES (:run, :stage, :case, :agent, :kind, :autonomy, :status, CAST(:output AS jsonb), :conf, "
    ":threshold, CAST(:sources AS jsonb), CAST(:reasons AS jsonb)) "
    "ON CONFLICT (run_id, stage) DO UPDATE SET agent = EXCLUDED.agent, kind = EXCLUDED.kind, autonomy = EXCLUDED.autonomy, "
    "status = EXCLUDED.status, output = EXCLUDED.output, confidence = EXCLUDED.confidence, threshold = EXCLUDED.threshold, "
    "sources = EXCLUDED.sources, reasons = EXCLUDED.reasons, at = now()"
)
SELECT = text(
    "SELECT stage, agent, kind, autonomy, status, output, confidence, threshold, sources, reasons "
    "FROM agent_stage_record WHERE run_id = :run"
)


def save_record(s: Session, run_id: str, case_id: str, r: StageRecord) -> None:
    """Upsert the record of one stage of a run."""
    s.execute(
        UPSERT,
        {
            "run": run_id, "stage": r.stage, "case": case_id, "agent": r.agent, "kind": r.kind, "autonomy": r.autonomy,
            "status": r.status, "output": json.dumps(r.output, default=str), "conf": r.confidence, "threshold": r.threshold,
            "sources": json.dumps(r.sources, default=str), "reasons": json.dumps(r.reasons, default=str),
        },
    )  # fmt: skip


def records_of(s: Session, run_id: str) -> list[StageRecord]:
    """The run's stage records, in chain order (a stored `analytics` record, from before P9-2.21, last)."""
    rows = {str(r["stage"]): r for r in s.execute(SELECT, {"run": run_id}).mappings()}
    return [
        StageRecord(
            stage=sid, agent=r["agent"], kind=r["kind"], autonomy=r["autonomy"], status=r["status"], output=dict(r["output"]),
            confidence=None if r["confidence"] is None else float(r["confidence"]), threshold=float(r["threshold"]),
            sources=list(r["sources"]), reasons=list(r["reasons"]),
        )
        for sid in (*STAGE_IDS, *LEGACY_STAGE_IDS)  # a record of a run before P9-2.21 may be `analytics`
        if (r := rows.get(sid)) is not None
    ]  # fmt: skip


def run_chain(s: Session, case_id: str, *, account: str) -> ChainRun:
    """Start a `stage_chain` run for the case as `account`, run it until it is blocked (done, waiting for a person,
    stopped or failed) and return what it recorded."""
    from di.services.agents import runtime  # the runtime imports this module

    run_id = runtime.start(s, CHAIN_AGENT, "stage_chain", case_id, account=account)
    s.commit()
    status = runtime.run_until_blocked(s, run_id)
    return ChainRun(run_id, status, records_of(s, run_id))
