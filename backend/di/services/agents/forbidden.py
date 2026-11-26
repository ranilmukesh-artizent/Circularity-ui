"""The actions no agent may ever run (hard rules: no approving, overriding or declining a decision, no access,
publishing or connection changes, no confirming outcomes on a person's behalf).

Checked three ways: at import against every tool table that lets an agent reach actions (di.mcp.policy, the playbooks
of di.services.agents.runtime, Ask's tools), in the tool catalogue (`agent_allowed`), and in the action pipeline for
every agent-prepared call (di.services.actions.pipeline step 6; audit F4), whichever way the call arrives.
Prefixes: an entry ending in "." covers the whole family.
HELD_FOR_PERSON and NO_AGENT_READS (plan 9 P9-0.4) are the two milder lists beside it; the tool catalogue shows each
action's mode ("yes", "held", "no") from all three (di.services.agents.catalog.agent_mode).
"""

import re
from collections.abc import Mapping
from typing import Any

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
    "standingPolicy.approve", "standingPolicy.retire",  # plan 9 P9-2.5: a person decides which policy approves (R7, R21)
    "fraud.release", "fraud.reject",  # plan 9 P9-2.11: only a person clears a fraud hold or declines the held return
    "work.resolve", "work.assign",  # plan 9 P9-1.7: only a person resolves or hands on an exception, approval or question
    # plan 9 P9-8.1: a connection and the system owner's approval of its production or write access are a person's (R21)
    "connection.", "registry.release",
    "mapping.answerOwner",  # plan 9 P9-8.4: only the system owner (a person) answers a mapping question
    "compose.sendBack", "compose.approve", "compose.publish",  # plan 9 P9-8.17: a person decides which composition takes effect
    "marketTable.approve", "marketTable.reject",  # plan 9 P9-4.2: a person decides which rates and tables price a repair (R21)
    "recall.release",  # plan 9 P9-3.7: only a person releases a recalled tool from quarantine (R21)
    # 25 Nov 2026, the person: agents create, read and update, never delete or approve. These were only held before.
    "flow.discard", "workflow.draft.discard", "mapping.revert", "scenario.delete", "task.cancel",
    "payout.decide",  # plan 9 P9-6.8: the payout a customer is paid, above the automatic limit, is decided by a person (R21)
    "rollout.",  # plan 9 P9-7.3: starting, widening, publishing and rolling back a canary are a person's (R21)
    "conflict.resolve",  # phase 2 review: choosing between two systems' values clears a hold; a person decides it
)  # fmt: skip

# Writes an agent may prepare but never run, whatever its autonomy: the pipeline (step 9b) holds them for a person.
# P9-2.4 folds this tuple into HoldReason.destructive (I-10).
HELD_FOR_PERSON = (
    "tables.update",
    "mapping.save",
    "mapping.decide",  # plan 9 P9-8.4: a choice on a suggested mapping is a person's
    "mapping.apply",  # plan 9 P9-8.4: saves the accepted rows as a mapping version
    "standingPolicy.save",
    "marketTable.save",  # P9-4.2: a rate card or table draft, and its submission, are a person's
    "marketTable.submit",
    "registry.saveEntry",  # plan 9 P9-8.7: an agent's connector draft is held for a person (the adapter author's one proposal)
    "serviceDesk.postFault",  # P9-4.7: the fault found on a draft line re-prices it and re-runs its options; a person posts it
    "nonReturnFee.post",  # P9-3.18: a fee posted to the billing system is a person's; an agent may prepare it
    "service.book",  # P9-11.7: a service order for a rental device is booked by a person
)  # a policy draft is a person's (P9-2.5)

# Writes that only add caution: never held for a person (phase 2 review). Holding them would let a model's own concern
# or a tainted read keep the computed hold off the case (R16: the model adds caution, never removes it).
CAUTION_ONLY = (
    "fraud.hold",  # P9-2.11: the intake stage holds a case whose fraud score reaches the pack's threshold
    "transit.flagDelay",  # P9-2.20: the transit stage marks a shipment as late
)


def caution_only(action_id: str) -> bool:
    return action_id in CAUTION_ONLY


# Reads no agent may call: they handle a secret (step 6 of the pipeline refuses them).
NO_AGENT_READS = ("source.test", "source.sandboxKey")
# An action whose name deletes, discards, reverts, cancels, resolves, waives or decides must be forbidden (check_person_only).
PERSON_ONLY_NAME = re.compile(
    r"\.(delete|remove|discard|revert|cancel|purge|approve|publish|reject|promote|override|decline|rollback|retire|release"
    r"|resolve|waive|clear|dismiss|accept)",
    re.IGNORECASE,
)


# Exceptions to a forbidden prefix: actions an agent may run although their prefix is a person's. Each only reads or creates
# (25 Nov 2026: agents create, read and update, never delete or approve). The secret stays server-side.
AGENT_EXEMPT = (
    "connection.discover",  # plan 9 P9-8.3: reads up to 500 sample records from the test connection into dry-run rows
)


def forbidden(action_id: str) -> bool:
    return action_id not in AGENT_EXEMPT and action_id.startswith(FORBIDDEN_ACTIONS)


def held_for_person(action_id: str) -> bool:
    return action_id in HELD_FOR_PERSON


def check_person_only(actions: Mapping[str, Any]) -> None:
    """Raise at start-up if a destructive or deciding action is reachable by an agent (agents never delete or approve).

    `actions` is the action registry (`di.services.actions.registry.ACTIONS`, id -> ActionDef); called by `di.main`."""
    bad = sorted(i for i, a in actions.items() if (PERSON_ONLY_NAME.search(i) or a.destructive) and not forbidden(i))
    if bad:
        raise RuntimeError(f"agents must never delete or approve; add to FORBIDDEN_ACTIONS: {', '.join(bad)}")
