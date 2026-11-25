"""A model's answer about a workflow, held until it is checked (plan 9, P9-2.23; R16).

    answer_checked(model, request, box) -> Iterator[Event]   `model.answer`, with the workflow checks applied

Owns: the hold-check-retry-refuse loop around `AskModel.answer`. An answer that did not read workflows passes through
untouched, text as it arrives. When a workflow tool was called, the text is held until the model is done; if
`workflow_check.problems` finds nothing the text is released, else the model is asked once more with the reasons, and a
second refusal raises `ModelUnavailable("unchecked")`: the service then answers with the rules (`by_model` false). The
refused text is never shown.
Never does: write, run a tool itself, or edit the model's text.
"""

from collections.abc import Iterator
from typing import Any

from di.services.ask import workflow_check
from di.services.ask.model import AskModel, AskRequest, Done, Event, ModelUnavailable, TextDelta

TRIES = 2  # the first answer and one retry


def _retry(req: AskRequest, draft: str, reasons: list[str]) -> AskRequest:
    said = [{"role": "user", "content": req.question}, {"role": "assistant", "content": draft}]
    note = "Your answer was refused: " + " ".join(reasons) + " Answer again, using only ids and numbers from the tool results."
    return AskRequest(question=note, system=req.system, conversation=[*req.conversation, *said])


def answer_checked(model: AskModel, req: AskRequest, box: Any) -> Iterator[Event]:
    asked_question = req.question
    for attempt in range(TRIES):
        held: list[TextDelta] = []
        for ev in model.answer(req, box):
            if isinstance(ev, TextDelta) and workflow_check.asked(box):
                held.append(ev)
            elif isinstance(ev, Done) and workflow_check.asked(box):
                reasons = workflow_check.problems(ev.text, asked_question, box)
                if not reasons:
                    yield from held
                    yield ev
                    return
                if attempt + 1 == TRIES:
                    raise ModelUnavailable("unchecked", " ".join(reasons))
                req = _retry(req, ev.text, reasons)
                break
            else:
                yield ev
        else:
            return  # no workflow answer to hold (or no Done event): the caller treats what came as it always has
