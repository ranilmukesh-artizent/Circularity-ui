"""A model's answer about a workflow, held until it is checked (plan 9, P9-2.23, P9-2.24; R16).

    answer_checked(model, request, box) -> Iterator[Event]   `model.answer`, with the workflow checks applied
    workflow_shaped(question) -> bool                        does the question name a workflow or a run?

Owns: the hold-check-retry-refuse loop around `AskModel.answer`. An answer that did not read workflows passes through
untouched, text as it arrives. Text is held, from its first token, once the question is a workflow question (it names a
WF- or RUN- id or says "workflow") or a workflow tool has been called; the held text is released only if
`workflow_check.problems` finds nothing. Else the model is asked once more with the reasons, and a second refusal raises
`ModelUnavailable("unchecked")`: the service then answers with the rules (`by_model` false). The refused text is never shown.
A question that did not look like a workflow question may already have streamed text before its first workflow tool call: a
refusal then cannot be retried (the retry could not take back what is on screen), so it raises at once and the service sends
its reset event before the rules answer.
Never does: write, run a tool itself, or edit the model's text.
"""

import re
from collections.abc import Iterator
from typing import Any

from di.services.ask import workflow_check
from di.services.ask.model import AskModel, AskRequest, Done, Event, ModelUnavailable, TextDelta

TRIES = 2  # the first answer and one retry
WORKFLOW_WORD = re.compile(r"\bworkflows?\b", re.I)


def workflow_shaped(question: str) -> bool:
    """True when the question names a workflow (WF-n), a run (RUN-xxxxx) or says "workflow"."""
    return bool(workflow_check.ID_RX.search(question) or WORKFLOW_WORD.search(question))


def _retry(req: AskRequest, draft: str, reasons: list[str]) -> AskRequest:
    said = [{"role": "user", "content": req.question}, {"role": "assistant", "content": draft}]
    note = "Your answer was refused: " + " ".join(reasons) + " Answer again, using only ids and numbers from the tool results."
    return AskRequest(question=note, system=req.system, conversation=[*req.conversation, *said])


def answer_checked(model: AskModel, req: AskRequest, box: Any) -> Iterator[Event]:
    asked_question = req.question
    held_from_start = workflow_shaped(asked_question)
    shown_early = False  # text already on the person's screen before a workflow tool was called
    for attempt in range(TRIES):
        held: list[TextDelta] = []
        for ev in model.answer(req, box):
            hold = held_from_start or workflow_check.asked(box)
            if isinstance(ev, TextDelta) and hold:
                held.append(ev)
            elif isinstance(ev, TextDelta):
                shown_early = True
                yield ev
            elif isinstance(ev, Done) and workflow_check.asked(box):
                reasons = workflow_check.problems(ev.text, asked_question, box)
                if not reasons:
                    yield from held
                    yield ev
                    return
                if attempt + 1 == TRIES or shown_early:
                    raise ModelUnavailable("unchecked", " ".join(reasons))
                req = _retry(req, ev.text, reasons)
                break
            elif isinstance(ev, Done):  # a workflow-shaped question that read no workflow: nothing to check, release the text
                yield from held
                yield ev
            else:
                yield ev
        else:
            return  # no workflow answer to hold (or no Done event): the caller treats what came as it always has
