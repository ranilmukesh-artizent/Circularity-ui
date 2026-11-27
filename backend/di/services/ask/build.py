"""The three things the assistant may make, each a DRAFT (ai-tasks §4B D1, D5, D6; golden rule 10).

    tool                    runs (through the action pipeline, as the signed-in person, prepared by "ask")
    create_workflow         workflow.author {prompt}: plan -> model graph -> code checks (3 repairs) -> workflow.create,
                            a dry test run, workflow.draft.save. A draft workflow in Workflow Studio, never published.
    change_decision_flow    flow.propose {flow_id, text} (checked, simulated; saves nothing), and only when the proposal is a
                            rule or a step with a graph: flow.saveDraft {graph, source: "assistant"}. The order is in code:
                            nothing is saved that was not proposed, checked and simulated first; a change that weakens a
                            guardrail (kind "blocked") or is unclear saves nothing.
    describe_business       compose.start {org_unit_id, text}: the description is matched to a pack and a draft composition
                            is started.

Each is a fixed chain with model steps inside (a workflow, not an open agent): the model that answers picks the tool and
passes the person's sentence; code does the rest. Nothing here publishes, approves, submits, discards or changes access:
those actions are not in the table, and di.services.agents.forbidden refuses them in the pipeline whatever a model asks.
The person's permission decides (manageWorkflows, manageFlows): a refusal goes back to the model as data.

What goes back to the model: a short result ({status, id, ...}) without the graph. What the answer lists: `Created`, one per
draft, with the page to open it on.
"""

from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote_plus

from di.repositories import flows
from di.repositories.orgs import units
from di.services.actions import (
    compose,  # noqa: F401 - registers compose.start
    modeler,  # noqa: F401 - registers flow.propose, flow.saveDraft
    workflow_author,  # noqa: F401 - registers workflow.author
)
from di.services.actions.pipeline import CallContext, invoke
from di.services.agents.forbidden import forbidden


def _p(t: str, desc: str) -> dict:
    return {"type": t, "description": desc}


# name -> (description, properties, required)
BUILD_TOOLS: dict[str, tuple[str, dict, list[str]]] = {
    "create_workflow": (
        "Create a DRAFT integration workflow in Workflow Studio from the person's sentence (e.g. 'pull returns from the ERP "
        "every 5 minutes and drop records without a serial'). It is planned, checked, test run dry and saved as a draft; it "
        "is never published. Use it whenever the person asks to create, build, draft or set up a workflow, sync, ingest or "
        "pipeline. Pass their words unchanged in `description`. If the result has `questions`, ask the person those "
        "questions; do not guess the answers. Not for decision-flow rules (use change_decision_flow).",
        {"description": _p("string", "The person's request in their own words, with the system, schedule and steps they named")},
        ["description"],
    ),
    "change_decision_flow": (
        "Change a decision flow's DRAFT from a plain sentence (e.g. 'never send Customer C's motors to resale', 'add an "
        "inspection step before valuation'). The change is checked and simulated first, then saved as a draft for a person "
        "to submit and approve; it never publishes. A change that weakens a guardrail is refused and nothing is saved. One "
        "change per call: for a request with several changes, call it once per change. `flow_id` is the open flow's id when "
        "the page gives one; otherwise read it with get_decision_flow first.",
        {
            "change": _p("string", "One change, in the person's words"),
            "flow_id": _p("number", "The decision flow's id (omit to use the flow open on the page)"),
        },
        ["change"],
    ),
    "describe_business": (
        "Start a DRAFT composition from a description of a business (e.g. 'we take back used laptops and phones, wipe them, "
        "grade them, then resell or recycle'): the description is matched to a template pack and a draft change set is "
        "made. Use it when the person describes what their business does and wants it set up. Pass their words unchanged. "
        "`org_unit_id` is the org unit it is for (omit to use the page's); if none is known the tool lists the choices.",
        {
            "description": _p("string", "The person's description of the business, unchanged"),
            "org_unit_id": _p("string", "Org unit id, e.g. Customer A (omit to use the page's)"),
        },
        ["description"],
    ),
}
REACHED = ("workflow.author", "flow.propose", "flow.saveDraft", "compose.start")
# Who prepares each draft (ai-tasks §5.3: the assistant delegates to a specialist; D5 least privilege). Ask itself is
# registered read-only (agent_identity "ask", autonomy read) and stays so: a build tool runs as the registered specialist,
# under THAT agent's autonomy, kill switch and org scope (di.services.agents.limits). An agent set to "propose" (the
# Configuration agent, as seeded) has its write held for a person: the tool then answers `held` with the proposal's id, and
# the person accepts it under "Waiting for you". Admin changes an agent's autonomy in Agents; nothing here does.
AGENT_OF = {"create_workflow": "integrator", "change_decision_flow": "recover-config", "describe_business": "recover-config"}
assert not [a for a in REACHED if forbidden(a)], "a build tool may never reach an action an agent must not run"  # noqa: S101 - import-time check


@dataclass
class Created:
    """One draft the assistant made: what the answer links to."""

    kind: str  # workflow, flow, composition
    id: str
    label: str
    href: str  # the web app's route

    def json(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id, "label": self.label, "href": self.href}


class BuildError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def specs() -> list[dict]:
    return [
        {"name": n, "description": d, "parameters": {"type": "object", "properties": p, "required": r}}
        for n, (d, p, r) in BUILD_TOOLS.items()
    ]


def _do(action: str, i: dict[str, Any], ctx: CallContext) -> Any:
    r = invoke(action, i, ctx)
    if not r["ok"]:
        raise BuildError(r["error"]["code"], r["error"]["message"])
    return r["output"]


def _held(out: Any, what: str) -> tuple[dict, "Created"] | None:
    """The pipeline held the write for a person ({held: proposal id, reasons}): what the model and the answer are told."""
    if not (isinstance(out, dict) and "held" in out):
        return None
    pid = str(out["held"])
    why = "; ".join(str(r.get("detail") or r.get("reason") or r) for r in (out.get("reasons") or []))[:300]
    res = {
        "status": "held_for_a_person",
        "proposal_id": pid,
        "why": why,
        "say": f"Say that {what} is prepared and HELD for the person (proposal {pid}): nothing is saved until they accept it "
        'under "Waiting for you". Do not say it was created or saved.',
    }
    return res, Created("proposal", pid, f"Held for you · {what}", "/home")


def create_workflow(args: dict, ctx: CallContext, page: dict | None) -> tuple[dict, Created | None]:  # noqa: ARG001 - one signature
    o = _do("workflow.author", {"prompt": args["description"]}, ctx)
    if h := _held(o, "the workflow draft"):
        return h
    res: dict[str, Any] = {"status": o["status"], "notes": o.get("notes") or []}
    if o["status"] == "questions":
        res["questions"] = [{k: q.get(k) for k in ("id", "text", "question", "options") if q.get(k)} for q in o["questions"]]
        res["say"] = "Ask the person these questions; no draft was made yet."
        return res, None
    if o["status"] != "drafted" or not o.get("workflow_id"):
        res["errors"] = [e.get("message") for e in (o.get("errors") or [])][:5]
        res["say"] = "No draft was made. Tell the person why, from notes and errors."
        return res, None
    wid, name = str(o["workflow_id"]), str(o.get("name") or o["workflow_id"])
    nodes = (o.get("graph") or {}).get("nodes") or []
    res |= {
        "workflow_id": wid,
        "name": name,
        "state": "draft (not published)",
        "blocks": [str(n.get("kind") or n.get("type") or n.get("id")) for n in nodes][:12],
        "trigger": o.get("trigger"),
        "test_run": o.get("test_run"),
        "by_model": o.get("by_model"),
        "say": "Say it is a draft, name its id, blocks and trigger, the test run's result and any note. "
        "Publishing is the person's button.",
    }
    return res, Created("workflow", wid, f"Draft {wid} · {name}", f"/integration/studio/{wid}")


def change_decision_flow(args: dict, ctx: CallContext, page: dict | None) -> tuple[dict, Created | None]:
    fid = args.get("flow_id")
    obj = (page or {}).get("object") or {}
    if fid is None and obj.get("kind") == "flow" and str(obj.get("id", "")).isdigit():
        fid = int(obj["id"])
    if fid is None:
        raise BuildError(
            "validation_error",
            "Which decision flow? No flow is open on this page. Read one with get_decision_flow {template, org} and pass its "
            "id as flow_id, or ask the person which flow they mean.",
        )
    p = _do("flow.propose", {"flow_id": int(fid), "text": args["change"]}, ctx)
    failing = [c for c in (p.get("checks") or []) if c.get("level") == "fail"]  # modeler.validate.Check: ok, warn, fail
    res: dict[str, Any] = {"flow_id": int(fid), "kind": p["kind"], "message": p.get("msg"), "guardrail": p.get("guard")}
    if p["kind"] in ("blocked", "unclear") or not p.get("graph"):
        res |= {"status": "not_saved", "say": "Nothing was saved. Tell the person why, from message; do not try another wording."}
        return res, None
    o = _do("flow.saveDraft", {"flow_id": int(fid), "graph": p["graph"], "source": "assistant", "note": p.get("note") or ""}, ctx)
    sim = p.get("sim") or {}
    if h := _held(o, f"the flow change ({p.get('label') or args['change'][:60]})"):
        return h[0] | {"kind": p["kind"], "message": p.get("msg")}, h[1]
    res |= {
        "status": "draft_saved",
        "label": p.get("label"),
        "rule_id": p.get("rid"),
        # modeler_sim.sim_json: n cases on the open queue, the cases whose route flips, the value difference
        "simulation": {
            "cases": sim.get("n"),
            "flips": len(sim.get("flips") or []),
            "dv": sim.get("dv"),
            "examples": (sim.get("flips") or [])[:3],
        }
        if sim
        else None,
        "checks_failing": [c.get("msg") for c in failing][:5],
        "say": "Say the change is saved in the flow's draft, what the simulation showed, "
        "and that a person submits and approves it.",
    }
    f = flows.get_flow(ctx.session, int(fid))  # the Modeler opens a flow by its template and org unit
    href = f"/modeler?template={quote_plus(f.template_key)}&org={quote_plus(f.org_unit_id)}" if f else "/modeler"
    label = p.get("label") or args["change"][:60]
    return res, Created("flow", str(o.get("id", fid)), f"Flow draft · {label}", href)


def describe_business(args: dict, ctx: CallContext, page: dict | None) -> tuple[dict, Created | None]:
    org = args.get("org_unit_id") or (page or {}).get("org")
    known = list(units(ctx.session))
    if not org or org not in known:
        raise BuildError(
            "validation_error",
            f"Which org unit is this for? Ask the person to pick one of: {', '.join(known[:10])}.",
        )
    o = _do("compose.start", {"org_unit_id": org, "text": args["description"]}, ctx)
    if h := _held(o, f"the composition for {org}"):
        return h
    reading = o.get("reading") if isinstance(o.get("reading"), dict) else {}
    cs = o.get("change_set") if isinstance(o.get("change_set"), dict) else {}
    cid, pack = str(o["id"]), str(o.get("pack_key") or "")
    res = {
        "status": "draft_started",
        "composition_id": cid,
        "pack": pack,
        "org_unit_id": org,
        "state": o.get("status"),
        "systems_named": reading.get("systems") or [],
        "changes": len(cs.get("ops") or []),  # config_agent.ChangeSet: ops, blocked, question
        "blocked": len(cs.get("blocked") or []),
        "question": cs.get("question"),
        "by_model": reading.get("by_model"),
        "say": "Say which pack the description matched, that a draft composition was started, "
        "and ask the pack's question if there is one.",
    }
    href = f"/modeler?template={quote_plus(pack)}&org={quote_plus(org)}&tab=setup&compose={cid}"
    return res, Created("composition", cid, f"Draft composition {cid} · {pack}", href)


RUNNERS = {
    "create_workflow": create_workflow,
    "change_decision_flow": change_decision_flow,
    "describe_business": describe_business,
}


def run(name: str, args: dict, ctx: CallContext, page: dict | None) -> tuple[dict, Created | None]:
    """One build tool, prepared by its specialist agent (AGENT_OF) for the signed-in person."""
    return RUNNERS[name](args, replace(ctx, preparer=AGENT_OF[name]), page)
