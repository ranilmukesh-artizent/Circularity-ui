"""The Agents page (plan 8, MVP-11.8): the agent registry, the agents' runs, the proposals waiting for a person and
the tool catalogue.

    GET /api/screens/agents
        agents     the registry (table agent_identity): [{id, name, kind, autonomy, enabled, org_scope, tools,
                   created_by}], seeded first, then by id. Admin edits them with agent.update (enable or stop,
                   autonomy, tools, org scope)
        orgs       the org unit ids an org scope may name
        mcp_tools  the MCP tool ids an agent's tools may name (besides the action ids of `tools`)
        runs       the newest agent runs (table agent_run) on cases the account may see: [{id, agent, agentName,
                   playbook, case_id, status, step, reason, waiting, created_at, updated_at, steps}]
                   waiting  {kind: "proposal", proposal: id} or {kind: "approval", case_id}: what the run waits for
                            from a person, else null
                   reason   why it failed or stopped, or the note it finished with, else null
                   steps    the calls it made: [{n, tool, ok, note, at}] (note: the refusal, or the proposal it held)
        proposals  the pending proposals the account may decide (di.services.agents.proposals.pending_for): accept
                   or reject them with proposal.accept and proposal.reject, as the person
        tools      the tool catalogue (di.services.agents.catalog), read only: every action with its input schema and
                   whether an agent may call it
        can        {manage}: the account may change agents (manageAgents). The actions check again.

Access: the `agents` page (Admin, Developer). Agents never decide a proposal or change an agent: the page's buttons
are the signed-in person's actions.

Facade (frontend/src/api/agents.ts): useAgents() reads this; updateAgent, acceptProposal and rejectProposal are the
agent.update, proposal.accept and proposal.reject actions.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.repositories.constants import TOOLS_BY_ID
from di.repositories.orgs import units
from di.services.agents import proposals, registry
from di.services.agents.catalog import catalog

RUNS = 50
RUNS_SQL = (
    "SELECT r.id, r.agent, r.playbook, r.case_id, r.status, r.step, r.state, r.created_at, r.updated_at, c.owner "
    "FROM agent_run r LEFT JOIN case_record c ON c.id = r.case_id ORDER BY r.created_at DESC, r.id LIMIT :n"
)
STEPS_SQL = "SELECT run_id, n, tool, output, at FROM agent_run_step WHERE run_id = ANY(:ids) ORDER BY run_id, n"


def _waiting(r: dict[str, Any]) -> dict[str, Any] | None:
    st = r["state"] or {}
    if r["status"] != "waiting":
        return None
    if st.get("waiting") == "proposal":
        return {"kind": "proposal", "proposal": st.get("proposal")}
    return {"kind": str(st.get("waiting") or "approval"), "case_id": r["case_id"]}


def _step(row: dict[str, Any]) -> dict[str, Any]:
    out = row["output"] or {}
    ok = bool(out.get("ok"))
    held = ok and isinstance(out.get("output"), dict) and "held" in out["output"]
    note = f"Held for a person as proposal {out['output']['held']}." if held else None
    if not ok:
        note = (out.get("error") or {}).get("message")
    return {"n": row["n"], "tool": row["tool"], "ok": ok, "note": note, "at": row["at"].isoformat()}


def _runs(p: Principal, s: Session, names: dict[str, str]) -> list[dict[str, Any]]:
    rows = [dict(r) for r in s.execute(text(RUNS_SQL), {"n": RUNS}).mappings()]
    rows = [r for r in rows if r["owner"] is None or p.tenant_ok(r["owner"])]
    steps: dict[str, list[dict[str, Any]]] = {}
    for st in s.execute(text(STEPS_SQL), {"ids": [r["id"] for r in rows]}).mappings():
        steps.setdefault(st["run_id"], []).append(_step(dict(st)))
    out = []
    for r in rows:
        state = r["state"] or {}
        out.append({
            "id": r["id"], "agent": r["agent"], "agentName": names.get(r["agent"], r["agent"]), "playbook": r["playbook"],
            "case_id": r["case_id"], "status": r["status"], "step": r["step"],
            "reason": state.get("reason") or state.get("note"),
            "waiting": _waiting(r), "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
            "steps": steps.get(r["id"], []),
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
        "can": {"manage": policy.can(p.account, "manageAgents", p.ctx)},
    }
