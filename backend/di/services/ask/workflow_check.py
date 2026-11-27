"""The checks on a model's answer about a workflow or a run (plan 9, P9-2.23; R16 "code checks every model output").

    asked(box)                    did this question read workflows (a workflow tool was called)?
    problems(text, question, box) the reasons the answer is refused: [] when it may be shown

Owns: what an answer about a workflow may say. Every number and every WF- or RUN- id in it must appear in what the
workflow tools returned (or in the question or the call's arguments: "There is no workflow WF-999" names the person's
own id); a workflow is never called a case; "no access" is never said (a person who may not see a workflow gets
not_found, so there is no access refusal to pass on); a reply that all lookups failed does not talk about cases; and it
never says it ran, applied or reprocessed anything (Ask only reads: the page's Run now, Fix, Reprocess buttons do).
Never does: call a tool, run a model or change an answer. `di.services.ask.checked_answer` retries and falls back.
"""

import json
import re
from typing import Any

from di.services.agents.checked_output import invented_numbers

WORKFLOW_TOOLS = frozenset({"list_workflows", "get_workflow", "get_workflow_run", "create_workflow"})
ID_RX = re.compile(r"\b(?:WF-\d+|RUN-[A-Z0-9]{5})\b")
CASE_OF_WORKFLOW = re.compile(r"\bcase\s+(?:WF|RUN)-", re.I)
NO_ACCESS = re.compile(r"(?:don.?t|do not|doesn.?t|does not) have (?:any )?access|\bno access\b|not authori[sz]ed", re.I)
DID_A_WRITE = re.compile(
    r"\b(?:I|I've|I have)\s+(?:re-?ran|re-?run|applied|reprocessed|restarted|started|fixed|published)\b", re.I
)
CASE_WORD = re.compile(r"\bcases?\b", re.I)
_ISO_T = re.compile(r"(?<=\d)T(?=\d)")


def _used(box: Any) -> list[Any]:
    return [u for u in box.used if u.name in WORKFLOW_TOOLS]


def asked(box: Any) -> bool:
    return bool(_used(box))


def problems(text: str, question: str, box: Any) -> list[str]:
    """Why `text` may not be shown (one reason per failed check), or []."""
    used = _used(box)
    facts = json.dumps([[u.args, u.data, u.message] for u in used], default=str, ensure_ascii=False)
    # a time in the facts is ISO ("2026-10-07T08:58:45.000Z"): the hour after the "T" is one of the facts' own numbers
    # (27 Nov 2026: a correct answer that said "08:58" was refused for "08" and the rules answered instead). Leading zeros
    # are NOT dropped: "9 retries" must not pass because a date holds "09".
    known = facts + " " + _ISO_T.sub(" ", facts) + " " + question
    out = []
    if bad := invented_numbers([text], known):
        out.append(f"These numbers are in no tool result: {', '.join(bad)}.")
    if bad_ids := sorted({i for i in ID_RX.findall(text) if i not in known}):
        out.append(f"These ids are in no tool result: {', '.join(bad_ids)}.")
    if CASE_OF_WORKFLOW.search(text):
        out.append("A WF- id is a workflow and a RUN- id a workflow run, never a case.")
    if NO_ACCESS.search(text):
        out.append("Do not say the person has no access: a workflow they cannot see is simply one they cannot see.")
    if DID_A_WRITE.search(text):
        out.append("Ask only reads. Point to the page's Run now, Fix or Reprocess buttons; never say you ran one.")
    if used and not any(u.ok for u in used) and CASE_WORD.search(text):
        out.append('Name what was looked up (a workflow or a run); do not use the word "case".')
    return out
