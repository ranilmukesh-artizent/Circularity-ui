"""The actions no agent may ever run (hard rules: no approving, overriding or declining a decision, no access,
publishing or connection changes, no confirming outcomes on a person's behalf).

Checked three ways: at import against every tool table that lets an agent reach actions (di.mcp.policy, the playbooks
of di.services.agents.runtime, Ask's tools), in the tool catalogue (`agent_allowed`), and in the action pipeline for
every agent-prepared call (di.services.actions.pipeline step 6; audit F4), whichever way the call arrives.
Prefixes: an entry ending in "." covers the whole family.
HELD_FOR_PERSON and NO_AGENT_READS (plan 9 P9-0.4) are the two milder lists beside it; the tool catalogue shows each
action's mode ("yes", "held", "no") from all three (di.services.agents.catalog.agent_mode).
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
    "overlay.approve", "overlay.reject",  # plan 9 P9-1.3: a person decides which customer changes to a pack take effect
    "pack.approve", "pack.reject",  # plan 9 P9-1.6: a person decides which pack version is in force
    "credentials.rotate",  # plan 9 P9-0.4: a new secret is a person's, never an agent's (review focus 6)
    "llm.",  # plan 9 P9-2.3: which language models run, and their limits, are a person's (llm.models, llm.setModel)
    "work.resolve", "work.assign",  # plan 9 P9-1.7: only a person resolves or hands on an exception, approval or question
)  # fmt: skip

# Writes an agent may prepare but never run, whatever its autonomy: the pipeline (step 9b) holds them for a person.
# P9-2.4 folds this tuple into HoldReason.destructive (I-10).
HELD_FOR_PERSON = ("mapping.revert", "tables.update", "mapping.save")

# Reads no agent may call: they handle a secret (step 6 of the pipeline refuses them).
NO_AGENT_READS = ("source.test", "source.sandboxKey")


def forbidden(action_id: str) -> bool:
    return action_id.startswith(FORBIDDEN_ACTIONS)


def held_for_person(action_id: str) -> bool:
    return action_id in HELD_FOR_PERSON
