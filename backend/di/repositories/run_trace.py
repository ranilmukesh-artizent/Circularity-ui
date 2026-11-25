"""The run view read model (plan 9, P9-2.6; registry entry I-12): everything one agent run did, for `agent.runTrace`.

    latest_run_for_case(s, case_id) -> run id | None
    run_trace(s, run_id) -> dict | None
        run (status, step, why it ended or waits, model, tokens), stages (the typed records of the chain), calls
        (`agent_run_step`), spans (a tree: each has `children`), journal (the rows with the run's id), proposals (with the
        hold reasons) and pauses (the journaled `agent.setEnabled` rows of the run's agent: who, when, on or off)

Read only. Call inputs go through `di.core.redact.clean`; span attributes were cleaned when written.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.redact import clean


def latest_run_for_case(s: Session, case_id: str) -> str | None:
    q = text("SELECT id FROM agent_run WHERE case_id = :c ORDER BY created_at DESC, id DESC LIMIT 1")
    return s.execute(q, {"c": case_id}).scalar()


def span_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The spans (in start order) as a forest: each span gets `children`; one whose parent is not among them is a root."""
    nodes = {x["span_id"]: {**x, "children": []} for x in spans}
    roots: list[dict[str, Any]] = []
    for x in spans:
        parent = nodes.get(x["parent_id"]) if x["parent_id"] else None
        (parent["children"] if parent else roots).append(nodes[x["span_id"]])
    return roots


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def _rows(s: Session, sql: str, **p: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in s.execute(text(sql), p).mappings()]


def run_trace(s: Session, run_id: str) -> dict[str, Any] | None:
    run = s.execute(
        text(
            "SELECT r.id, r.agent, coalesce(a.name, r.agent) AS agent_name, r.playbook, r.case_id, r.status, r.step, r.state, "
            "r.created_at, r.updated_at FROM agent_run r LEFT JOIN agent_identity a ON a.id = r.agent WHERE r.id = :i"
        ),
        {"i": run_id},
    ).mappings().first()  # fmt: skip
    if run is None:
        return None
    st = dict(run["state"] or {})
    stages = _rows(
        s,
        "SELECT stage, agent, kind, autonomy, status, output, confidence, threshold, sources, reasons, at "
        "FROM agent_stage_record WHERE run_id = :r",
        r=run_id,
    )
    order = ["intake", "condition", "demand", "fit_for_use", "valuation", "disposition", "follow_through", "analytics"]
    stages.sort(key=lambda x: order.index(x["stage"]) if x["stage"] in order else len(order))
    for x in stages:
        x["confidence"] = None if x["confidence"] is None else float(x["confidence"])
        x["threshold"] = float(x["threshold"])
        x["at"] = _iso(x["at"])
    calls = _rows(s, "SELECT n, tool, input, output, at FROM agent_run_step WHERE run_id = :r ORDER BY n", r=run_id)
    for c in calls:
        c["input"], c["at"] = clean(c["input"]), _iso(c["at"])
        out = c["output"]
        c["ok"] = not (isinstance(out, dict) and out.get("ok") is False)
        c["held"] = out["output"].get("held") if isinstance(out, dict) and isinstance(out.get("output"), dict) else None
        c["output"] = None  # the result lives in the journal and the records; the view shows the call and its outcome
    spans = _rows(
        s,
        "SELECT span_id, trace_id, parent_id, name, kind, started_at, ended_at, status, attrs FROM trace_span "
        "WHERE run_id = :r ORDER BY started_at, span_id",
        r=run_id,
    )
    for x in spans:
        x["started_at"], x["ended_at"] = _iso(x["started_at"]), _iso(x["ended_at"])
    journal = _rows(
        s,
        "SELECT seq, action, actor, role, preparer, case_id, at FROM action_journal WHERE run_id = :r ORDER BY seq",
        r=run_id,
    )
    for j in journal:
        j["at"] = _iso(j["at"])
    proposals = _rows(
        s,
        "SELECT id, action, status, case_id, reasons, decided_by, decided_at, created_at FROM agent_proposal "
        "WHERE run_id = :r ORDER BY id",
        r=run_id,
    )
    for p in proposals:
        p["decided_at"], p["created_at"] = _iso(p["decided_at"]), _iso(p["created_at"])
    pauses = [
        {"by": j["actor"], "on": bool(j["input"].get("on")), "at": _iso(j["at"])}
        for j in _rows(
            s,
            "SELECT actor, input, at FROM action_journal WHERE action = 'agent.setEnabled' AND input->>'id' = :a ORDER BY seq",
            a=run["agent"],
        )
    ]
    usage = st.get("usage") or {}
    return {
        "run": {
            "id": run["id"], "agent": run["agent"], "agentName": run["agent_name"], "playbook": run["playbook"],
            "case_id": run["case_id"], "status": run["status"], "step": run["step"], "reason": st.get("reason"),
            "waiting": st.get("waiting"), "model": st.get("model"), "model_route": st.get("model_route"),
            "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")} if usage else None,
            "created_at": _iso(run["created_at"]), "updated_at": _iso(run["updated_at"]),
        },
        "stages": stages,
        "calls": calls,
        "spans": span_tree(spans),
        "journal": journal,
        "proposals": proposals,
        "pauses": pauses,
    }  # fmt: skip
