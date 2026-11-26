"""The Agents page (plan 8, MVP-11.8): the agent registry, the agents' runs, the proposals waiting for a person and
the tool catalogue.

    GET /api/screens/agents
        agents     the registry (table agent_identity): [{id, name, kind, autonomy, enabled, org_scope, tools,
                   created_by}], seeded first, then by id. Admin edits them with agent.update (enable or stop,
                   autonomy, tools, org scope)
        orgs       the org unit ids an org scope may name
        mcp_tools  the MCP tool ids an agent's tools may name (besides the action ids of `tools`)
        runs       the newest agent runs (table agent_run) on cases the account may see: [{id, agent, agentName,
                   playbook, case_id, status, step, stage, reason, waiting, created_at, updated_at, steps}]
                   stage    the stage of the chain the run is at (`lease_end` … `reconcile`, P9-2.1 and P9-2.21), null once it has
                            finished or when it has no position (a run started before the chain)
                   waiting  {kind: "proposal", proposal: id} or {kind: "approval", case_id}: what the run waits for
                            from a person, else null
                   reason   why it failed or stopped, or the note it finished with, else null
                   steps    the calls it made: [{n, tool, ok, note, at}] (note: the refusal, or the proposal it held)
                   journey  the ten stages of its journey, [JourneyStage] (P9-2.21, `di.services.agents.journey`): a stage
                            with no record is "Queued", nothing is invented for it
        proposals  the pending proposals the account may act on (di.services.agents.proposals.pending_for): accept
                   or reject them with proposal.accept and proposal.reject, as the person (`own`: only reject)
        tools      the tool catalogue (di.services.agents.catalog), read only: every action with its input schema and
                   whether an agent may call it
        llm        the language models (di.services.llm.view): [{id, provider, model, roles, rpm, tpm, rpd, enabled,
                   priority, used_minute: {requests, tokens}, used_day, cooling_until}]; Admin switches and orders them
                   with llm.setModel (plan 9 P9-2.3), other roles see an empty list
        can        {manage}: the account may change agents (manageAgents). The actions check again.

Access: the `agents` page (Admin, Developer). Agents never decide a proposal or change an agent: the page's buttons
are the signed-in person's actions.

    GET /api/screens/agents/models   (plan 8 UI gaps: the Models panel, on the Agents page and the Modeler)
        base       the base predictor's model version (FormulaPredictor.model_version, "v1.3")
        active     {template: id of its active calibration model, or null} for every template
        activeRatedLife  the id of the active remaining-life model (kind rated_life, P9-3.10), or null
        activePrice      the id of the active device price model (kind price, P9-6.9), or null; its metrics
                         carry mae, mape, coverage (against target 0.8), n_train, n_test and window
        activeTakeUp     the id of the active take-up model (kind take_up, P9-4.11), or null; its metrics carry log_loss, brier,
                         baseline_log_loss, baseline_brier, market, window and bands [{lo, hi, offered, accepted, predicted}]
        models     every fitted model (table model_version), newest first: [{id, template, status, created_by,
                   approved_by, created_at, factors: [{route, cls, factor}], metrics: {n, active_id, mae_active,
                   mae_candidate}, proposal: {by, at} | null, blocks: {propose, promote}}]
                   blocks  why the signed-in person may not propose or approve it (its permission, maker-checker, not
                           proposed yet, already proposed), else null: the buttons show the reason, the actions check
                           again (di.services.actions.models)
                   metrics.shadow  (a price candidate, P9-6.18) {n, min, settled, mae, coverage, mae_active, coverage_active}:
                           the evaluations it was shadowed on and its error against the active model's on the settled ones
                           (di.services.device.price_shadow); a price model is promotable from `min` evaluations
        can      {fit, promote}: manageFlows (fit and propose) and approve.flows (approve the promotion)
        repairAccuracy  (plan 9, P9-4.5) the repair estimate replayed on held-out repairs: {rows: [{org_unit_id | null,
                   model_class, as_of, n, mae, mae_share, coverage, auto_share, instant}] (newest per org unit and class,
                   only tenants the person sees), bar: {min_coverage, max_mae_share, holdout_weeks} (GR-S1),
                   can: {compute}: manageMarketTables}; serviceDesk.computeAccuracy is computeRepairAccuracy()
    Access: the `agents` or the `modeler` page (Admin, Developer, Planner, Approver, Executive), so an Approver can
    approve what a Planner proposed.

Facade (frontend/src/api/agents.ts): useAgents() reads this; updateAgent, acceptProposal and rejectProposal are the
agent.update, proposal.accept and proposal.reject actions; registerAgent is agent.register. useModels() reads the
models; fitModel, proposeModel and promoteModel are model.fit, model.propose and model.promote.
"""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.core.redact import clean
from di.repositories import repair_accuracy as accuracy_repo
from di.repositories.constants import TOOLS_BY_ID
from di.repositories.model_versions import ModelRow
from di.repositories.orgs import units
from di.services.actions.models import model_json, promote_block, proposal_of, propose_block
from di.services.agents import proposals, registry
from di.services.agents.catalog import catalog
from di.services.agents.journey import journey
from di.services.agents.stage_context import STAGE_IDS
from di.services.device import price_shadow
from di.services.engine.predictor import FormulaPredictor
from di.services.llm.view import models_view
from di.services.modeler.templates import template_keys
from di.services.service_desk import accuracy

RUNS = 50
RUNS_SQL = (
    "SELECT r.id, r.agent, r.playbook, r.case_id, r.status, r.step, r.state, r.created_at, r.updated_at, c.owner "
    "FROM agent_run r LEFT JOIN case_record c ON c.id = r.case_id ORDER BY r.created_at DESC, r.id LIMIT :n"
)
STEPS_SQL = "SELECT run_id, n, tool, input, output, at FROM agent_run_step WHERE run_id = ANY(:ids) ORDER BY run_id, n"
STAGES_SQL = (
    "SELECT run_id, stage, agent, status, output, confidence, threshold, sources, reasons FROM agent_stage_record "
    "WHERE run_id = ANY(:ids)"
)


def _waiting(r: dict[str, Any]) -> dict[str, Any] | None:
    st = r["state"] or {}
    if r["status"] != "waiting":
        return None
    if st.get("waiting") == "proposal":
        return {"kind": "proposal", "proposal": st.get("proposal")}
    return {"kind": str(st.get("waiting") or "approval"), "case_id": r["case_id"]}


def _stage(r: dict[str, Any]) -> str | None:
    i = (r["state"] or {}).get("stage")
    return STAGE_IDS[i] if isinstance(i, int) and 0 <= i < len(STAGE_IDS) else None


def _step(row: dict[str, Any]) -> dict[str, Any]:
    out = row["output"] or {}
    ok = bool(out.get("ok"))
    held = ok and isinstance(out.get("output"), dict) and "held" in out["output"]
    note = f"Held for a person as proposal {out['output']['held']}." if held else None
    if not ok:
        note = (out.get("error") or {}).get("message")
    return {"n": row["n"], "tool": row["tool"], "ok": ok, "note": note, "at": row["at"].isoformat()}


def _call(row: dict[str, Any]) -> dict[str, Any]:
    """A call as the journey reads it: `{n, tool, ok, held, input, stage}` (the stage is in the logged output)."""
    out = row["output"] or {}
    held = out["output"].get("held") if isinstance(out.get("output"), dict) else None
    return {
        "n": row["n"],
        "tool": row["tool"],
        "ok": bool(out.get("ok")),
        "held": held,
        "input": clean(row["input"]),
        "stage": out.get("stage"),
    }


def _runs(p: Principal, s: Session, names: dict[str, str]) -> list[dict[str, Any]]:
    rows = [dict(r) for r in s.execute(text(RUNS_SQL), {"n": RUNS}).mappings()]
    rows = [r for r in rows if r["owner"] is None or p.tenant_ok(r["owner"])]
    ids = [r["id"] for r in rows]
    steps: dict[str, list[dict[str, Any]]] = {}
    calls: dict[str, list[dict[str, Any]]] = {}
    for st in s.execute(text(STEPS_SQL), {"ids": ids}).mappings():
        steps.setdefault(st["run_id"], []).append(_step(dict(st)))
        calls.setdefault(st["run_id"], []).append(_call(dict(st)))
    records: dict[str, list[dict[str, Any]]] = {}
    for rec in s.execute(text(STAGES_SQL), {"ids": ids}).mappings():
        records.setdefault(rec["run_id"], []).append(dict(rec))
    out = []
    for r in rows:
        state = r["state"] or {}
        out.append({
            "id": r["id"], "agent": r["agent"], "agentName": names.get(r["agent"], r["agent"]), "playbook": r["playbook"],
            "case_id": r["case_id"], "status": r["status"], "step": r["step"], "stage": _stage(r),
            "reason": state.get("reason") or state.get("note"),
            "waiting": _waiting(r), "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
            "steps": steps.get(r["id"], []),
            "journey": [j.as_dict() for j in journey({"stages": records.get(r["id"], []), "calls": calls.get(r["id"], [])})],
        })  # fmt: skip
    return out


def page(p: Principal, s: Session) -> dict[str, Any]:
    p.require_page("agents")
    agents = registry.all_agents(s)
    return {
        "agents": [a.as_dict() for a in agents],
        "orgs": list(units(s)),
        "mcp_tools": list(TOOLS_BY_ID),
        "runs": _runs(p, s, {a.id: a.name for a in agents}),
        "proposals": proposals.pending_for(s, p.account, p.ctx),
        "tools": catalog(),
        "llm": models_view(s) if policy.can(p.account, "manageAgents", p.ctx) else [],
        "can": {"manage": policy.can(p.account, "manageAgents", p.ctx)},
    }


MODELS_SQL = (
    "SELECT id, template, factors, status, created_by, approved_by, metrics, created_at, kind, pack, trained_at, data_window, "
    "quality, drift, drift_status, cadence, next_due FROM model_version "
    "ORDER BY created_at DESC, id DESC"
)


def models(p: Principal, s: Session) -> dict[str, Any]:
    p.require_any_page(("agents", None), ("modeler", None))
    if p.account.role == "Finance":  # Finance opens the Modeler for the market tables (P9-4.2), not the model candidates
        raise HTTPException(403, {"code": "out_of_scope", "message": "Not available for the Finance view."})
    can_fit, can_promote = p.can("manageFlows"), p.can("approve.flows")
    rows = [ModelRow(*r) for r in s.execute(text(MODELS_SQL))]
    active = {t: None for t in template_keys()} | {
        m.template: m.id for m in rows if m.status == "active" and m.kind == "calibration"
    }
    rated = next((m.id for m in rows if m.status == "active" and m.kind == "rated_life"), None)
    price = next((m.id for m in rows if m.status == "active" and m.kind == "price"), None)
    take_up = next((m.id for m in rows if m.status == "active" and m.kind == "take_up"), None)
    out = []
    for m in rows:
        j = model_json(m)
        metrics = {k: v for k, v in (m.metrics or {}).items() if k != "proposal"}
        blocks: dict[str, str | None] = {"propose": None, "promote": None}
        if m.status == "candidate":
            blocks = {
                "propose": propose_block(m) if can_fit else "Only a Planner or Admin proposes a model for promotion.",
                "promote": (
                    promote_block(m, p.account.id, s) if can_promote else "Only an Approver or Admin approves a promotion."
                ),
            }
        if m.kind == "price" and m.status == "candidate":  # P9-6.18: the shadow beside the model's own held-out metrics
            metrics["shadow"] = price_shadow.stats(s, m.id)
        out.append({**j, "metrics": metrics, "proposal": proposal_of(m), "blocks": blocks})
    can = {"fit": can_fit, "promote": can_promote}
    acc = _repair_accuracy(p, s)
    return {
        "base": FormulaPredictor.model_version,
        "active": active,
        "activeRatedLife": rated,
        "activePrice": price,
        "activeTakeUp": take_up,
        "models": out,
        "can": can,
        "repairAccuracy": acc,
    }


def _repair_accuracy(p: Principal, s: Session) -> dict[str, Any]:
    """The newest held-out accuracy of the repair estimate per org unit and tool class, those the principal's tenants allow
    (plan 9, P9-4.5; di.services.service_desk.accuracy), with GR-S1's bar."""
    b = accuracy.bar()
    rows = [r for r in accuracy_repo.latest_all(s) if r.org_unit_id is None or p.tenant_ok(r.org_unit_id)]
    return {
        "rows": [
            {"org_unit_id": r.org_unit_id, "model_class": r.model_class, "as_of": r.as_of.isoformat(), "n": r.n,
             "mae": float(r.mae), "mae_share": float(r.mae_share), "coverage": float(r.coverage),
             "auto_share": float(r.auto_share), "instant": r.instant}
            for r in rows
        ],
        "bar": {"min_coverage": float(b.min_coverage), "max_mae_share": float(b.max_mae_share), "holdout_weeks": b.holdout_weeks},
        "can": {"compute": p.can("manageMarketTables")},
    }  # fmt: skip
