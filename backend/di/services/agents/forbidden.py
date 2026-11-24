"""The actions no agent may ever run (hard rules: no approving, overriding or declining a decision, no access,
publishing or connection changes, no confirming outcomes on a person's behalf).

Checked three ways: at import against every tool table that lets an agent reach actions (di.mcp.policy, the playbooks
of di.services.agents.runtime, Ask's tools), in the tool catalogue (`agent_allowed`), and in the action pipeline for
every agent-prepared call (di.services.actions.pipeline step 6; audit F4), whichever way the call arrives.
Prefixes: an entry ending in "." covers the whole family.
"""

FORBIDDEN_ACTIONS = (
    "decision.approve", "decision.override", "decision.decline", "outcome.confirm", "adapter.acknowledge",
    "access.", "agent.", "workflow.publish", "workflow.setStatus", "workflow.delete", "source.", "mcp.",
    "org.create", "org.update", "org.move",  # plan 8 MVP-1.3: the org tree decides who sees what (access)
    "org.setPilot",  # plan 8 MVP-10.3: whether a pilot org's instructions are sent (outbound sending)
    "org.importPack",  # plan 8 MVP-10.2: sets up another org's sources, workflows and flows
    "proposal.",  # plan 8 MVP-11.4: only a person accepts or rejects an agent's proposal
    "flow.approve", "flow.publish", "flow.reject", "flow.rollback",  # plan 8 MVP-3.2: a person decides the policy
    "model.promote",  # plan 8 MVP-12.2: a person decides which model values new cases
    "model.propose",  # plan 8 UI gaps: a person proposes a model for promotion
)  # fmt: skip


def forbidden(action_id: str) -> bool:
    return action_id.startswith(FORBIDDEN_ACTIONS)
