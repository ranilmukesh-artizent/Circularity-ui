"""Per-field notes for the tool catalogue's input schemas (plan 9, P9-2.12).

Owns: `NOTES`, a plain table `action id -> field -> {desc, enum?}` that `catalog.input_schema` merges into each
property as `description` and `enum`, so a model reads what a field is for and which values it may send.
Never does: edit the golden action catalogue or an `ActionDef` (the catalogue stays generated from the registry, "one
source of truth"), decide what an agent may call (`catalog.agent_mode`), or hold logic of any kind.

It covers every action a stage, a playbook or an MCP tool reaches. A note for a field the action does not declare is
ignored; a required field without a note is a gap `tests/test_tool_find.py` catches.
"""

Note = dict[str, object]

_CASE: Note = {"desc": "The case id, as shown on the case page, for example RT-1048."}
_FLOW: Note = {"desc": "The id of the decision flow (a number from flow.get)."}
_AUTONOMY: Note = {"desc": "How far the agent may go.", "enum": ["read", "propose", "act"]}

NOTES: dict[str, dict[str, Note]] = {
    "case.evidence": {"case_id": _CASE},
    "case.routes": {"case_id": _CASE},
    "case.reevaluate": {"case_id": _CASE},
    "evidence.request": {"case_id": _CASE},
    "decision.submit": {"case_id": {"desc": "The case whose recommended decision is submitted for approval."}},
    "instruction.resend": {"case_id": {"desc": "The case whose approved instruction is sent again to the system."}},
    "scenario.delete": {"case_id": _CASE, "id": {"desc": "The id of the scenario to delete (a person only)."}},
    "fraud.hold": {
        "case_id": {"desc": "The returned asset's case to hold for fraud review."},
        "score": {"desc": "The computed fraud score (sum of the fired signals' weights), never a model estimate."},
        "signals": {"desc": "The signals of the triage: each {id, fired, value, source, at}."},
        "rule_version": {"desc": "The version of the pack's fraud rule set that scored the case."},
    },
    "flow.get": {
        "flow_id": _FLOW,
        "template": {"desc": "The template pack key, for example industrial, when no flow id is given."},
        "org": {"desc": "The org unit whose own flow to read; empty for the shared one."},
    },
    "flow.propose": {
        "flow_id": _FLOW,
        "text": {"desc": "The change in plain words, for example: hold any case above $5,000 for a person."},
    },
    "flow.simulate": {
        "flow_id": _FLOW,
        "graph": {"desc": "A flow graph to simulate instead of the saved draft."},
        "params": {"desc": "Simulation settings, for example the number of cases."},
    },
    "flow.saveDraft": {
        "flow_id": _FLOW,
        "graph": {"desc": "The whole flow graph (nodes and edges) to save as the draft."},
        "source": {"desc": "Where the change came from, for example the assistant or the canvas."},
        "note": {"desc": "A short note for the history of the flow."},
    },
    "config.read": {
        "text": {"desc": "The description of the business in the customer's own words."},
        "org_unit_id": {"desc": "The org unit the description is for."},
    },
    "config.draft": {
        "text": {"desc": "The description of the business in the customer's own words."},
        "org_unit_id": {"desc": "The org unit the changes are drafted for."},
        "answer": {"desc": "The answer to the one question config.read asked, when there was one."},
    },
    "exception.explain": {"exception_id": {"desc": "The number of the exception item in My work."}},
    "tools.find": {
        "query": {"desc": "What you want to do, in a few words, for example: request missing evidence."},
        "limit": {"desc": "How many tools to return, 1 to 50; the ten best when omitted."},
    },
    "agent.register": {
        "id": {"desc": "The agent id: 2 to 64 lower-case letters, digits, dots, dashes or underscores."},
        "name": {"desc": "The name people see."},
        "kind": {"desc": "internal runs inside Circularity; external calls in over MCP.", "enum": ["internal", "external"]},
        "autonomy": _AUTONOMY,
    },
    "agent.update": {"id": {"desc": "The id of the registered agent."}, "autonomy": _AUTONOMY},
    "agent.startRun": {
        "agent": {"desc": "The id of the registered agent that runs the playbook."},
        "case_id": _CASE,
        "playbook": {"desc": "The playbook to run; case_autopilot when omitted.", "enum": ["case_autopilot", "stage_chain"]},
    },
}
