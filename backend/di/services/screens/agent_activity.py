"""Agent activity (UI audit 2026-11-26, gap 12): what each agent did, per case and pack, read only, for every role that has
My work (Planner, Approver, Executive, Engineer, Finance, Warehouse Manager, Developer, Admin).

    GET /api/screens/agent-activity
        events   the newest first (at most EVENTS): [{id, at, agent, agentName, kind, title, detail, case_id, pack,
                 run_id, proposal_id}]
                 kind  held      a proposal an agent prepared that still waits for a person
                       accepted  a person accepted it (it ran as that person)
                       rejected  a person rejected it
                       refused   a call of a run the server refused (the refusal is the detail)
                       run       an agent run (status and the note it finished with)
        agents   [{id, name}] the agents that appear in the events, for the filter
        packs    [{key, name}] the packs that appear in the events, for the filter
        can      {runAgent}: the account may run the case autopilot on a case (agent.startRun, propose only)

Access: an event of a case is listed only when the case is in the account's tenants and warehouse (`Principal.tenant_ok`
and `location_ok`, as My work does); a case the server cannot place is nobody's (fail closed). An event with no case
(a flow proposal) is listed only to an account that holds the held action's own permission. The page changes nothing:
a person decides a proposal in My work, on Home or in the assistant (`ProposalRow`), not here.

Facade (frontend/src/api/agentActivity.ts): useAgentActivity().
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.services.actions.registry import ACTIONS
from di.services.actions.scope import case_scope
from di.services.agents import registry
from di.services.cases.process import pack_of

EVENTS = 200
PROPOSALS_SQL = (
    "SELECT id, agent, action, case_id, run_id, status, created_at, decided_by, decided_at, result "
    "FROM agent_proposal ORDER BY id DESC LIMIT :n"
)
RUNS_SQL = "SELECT id, agent, case_id, status, state, created_at, updated_at FROM agent_run ORDER BY created_at DESC, id LIMIT :n"
REFUSED_SQL = (
    "SELECT s.run_id, s.n, s.tool, s.output, s.at, r.agent, r.case_id FROM agent_run_step s JOIN agent_run r ON r.id = s.run_id "
    "WHERE (s.output ->> 'ok') = 'false' ORDER BY s.at DESC, s.run_id, s.n LIMIT :n"
)


def _visible(p: Principal, case_id: str | None, permission: str | None) -> bool:
    if not case_id:
        return permission is None or policy.can(p.account, permission, p.ctx)
    where = case_scope(case_id)
    return where is not None and p.tenant_ok(where[0]) and p.location_ok(where[1])


def _title(action: str) -> str:
    a = ACTIONS.get(action)
    return a.title if a else action


def page(p: Principal, s: Session) -> dict[str, Any]:
    p.require_page("agent-activity")
    names = {a.id: a.name for a in registry.all_agents(s)}
    packs: dict[str, str] = {}
    pack_cache: dict[str | None, tuple[str, str]] = {}

    def pack(case_id: str | None) -> tuple[str, str]:
        if case_id not in pack_cache:
            pk = pack_of(s, case_id)
            pack_cache[case_id] = (pk.key, pk.name)
        return pack_cache[case_id]

    events: list[dict[str, Any]] = []

    def add(**e: Any) -> None:
        key, name = pack(e["case_id"])
        packs[key] = name
        events.append({"agentName": names.get(e["agent"], e["agent"]), "pack": key, "run_id": None, "proposal_id": None} | e)

    for r in s.execute(text(PROPOSALS_SQL), {"n": EVENTS}).mappings():
        act = ACTIONS.get(r["action"])
        perm = act.permission if act else None
        if not _visible(p, r["case_id"], perm):
            continue
        kind = {"pending": "held", "accepted": "accepted", "rejected": "rejected"}.get(r["status"], "rejected")
        by = f" by {r['decided_by']}" if r["decided_by"] else ""
        detail = {"held": "Waits for a person.", "accepted": f"Accepted{by}.", "rejected": f"Rejected{by}."}[kind]
        if r["status"] == "expired":
            detail = "Expired without a decision."
        add(
            id=f"p{r['id']}", at=(r["decided_at"] or r["created_at"]).isoformat(), agent=r["agent"], kind=kind,
            title=_title(r["action"]), detail=detail, case_id=r["case_id"], run_id=r["run_id"], proposal_id=r["id"],
        )  # fmt: skip
    for r in s.execute(text(RUNS_SQL), {"n": EVENTS}).mappings():
        if not _visible(p, r["case_id"], None):
            continue
        st = r["state"] or {}
        note = st.get("reason") or st.get("note") or ""
        add(
            id=f"r{r['id']}", at=r["updated_at"].isoformat(), agent=r["agent"], kind="run", title=f"Run {r['status']}",
            detail=str(note), case_id=r["case_id"], run_id=r["id"],
        )  # fmt: skip
    for r in s.execute(text(REFUSED_SQL), {"n": EVENTS}).mappings():
        if not _visible(p, r["case_id"], None):
            continue
        err = ((r["output"] or {}).get("error") or {}).get("message") or "Refused."
        add(
            id=f"s{r['run_id']}-{r['n']}", at=r["at"].isoformat(), agent=r["agent"], kind="refused",
            title=_title(r["tool"]), detail=str(err), case_id=r["case_id"], run_id=r["run_id"],
        )  # fmt: skip
    events.sort(key=lambda e: e["at"], reverse=True)
    events = events[:EVENTS]
    seen = {e["agent"] for e in events}
    return {
        "events": events,
        "agents": [{"id": a, "name": names.get(a, a)} for a in sorted(seen)],
        "packs": [{"key": k, "name": n} for k, n in sorted(packs.items())],
        "can": {"runAgent": policy.can(p.account, "runAgent", p.ctx)},
    }
