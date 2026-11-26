"""ChainModel: an AskModel that tries several models in order (plan 9, P9-0.5; feeds the router of I-9 in P9-2.3).

Owns: moving to the next model when one is rate limited, unavailable or too slow BEFORE it yielded anything.
Never: repeats a streamed answer (after the first event an error is re-raised), retries a `model_error`, or logs a key.
When every model failed it raises the last ModelUnavailable and Ask answers by rules as before.
"""

from collections.abc import Iterator, Sequence

from di.services.ask.model import AskModel, AskRequest, Event, ModelUnavailable, Toolbox

MOVE_ON = ("rate_limited", "unavailable", "timeout")


class ChainModel:
    name = "chain"

    def __init__(self, models: Sequence[AskModel]):
        self.models: list[AskModel] = list(models)  # a list the router may reorder
        self.model = self.models[0].model if self.models else ""
        # the provider Ask reports: "groq" for a chain of Groq models (26 Nov: migration 0063 made Ask's chain three Groq
        # models and the answer said "chain"); "chain" only when the providers differ
        names = {m.name for m in self.models}
        self.name = names.pop() if len(names) == 1 else "chain"

    def answer(self, request: AskRequest, tools: Toolbox) -> Iterator[Event]:
        last: ModelUnavailable | None = None
        for m in self.models:
            started = False
            try:
                for ev in m.answer(request, tools):
                    started = True
                    yield ev
                return
            except ModelUnavailable as e:
                if started or e.reason not in MOVE_ON:
                    raise
                last = e
        raise last or ModelUnavailable("unavailable", "empty chain")
