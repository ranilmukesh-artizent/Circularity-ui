"""Checked model output with a retry budget (plan 9, P9-2.19; R16 "code checks every model output"; uses registry entry I-8).

    checked_type(base, check, retries=1) -> type    `base` with `check(output) -> [reason]` run as a validator
    invented_numbers(texts, *blobs) -> [str]        the numbers in `texts` that appear in none of `blobs`
    RetriesExhausted                                raised once the budget of refusals is spent

A refusal is a `ValueError` inside the output type's validator, so Pydantic AI sends the reasons back to the model as a retry
(https://pydantic.dev/docs/ai/core-concepts/output/). The loop's own budget is `PydanticAILoop`'s `TOOL_RETRIES`; a task whose
spec allows fewer rounds (P9-2.19: one) uses `checked_type`, whose validator raises `RetriesExhausted` (not a `ValueError`, so
the run ends instead of retrying) after `retries` refusals. The caller catches it with the loop's other failures and answers
from its deterministic path. One class per call: the budget is the class's own.
Never does: run a model, decide what a good output is (the caller's `check` does), or write anything.
"""

import re
from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, create_model, model_validator

NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


class RetriesExhausted(Exception):
    """The model's output failed its checks more often than the task allows."""


def checked_type[M: BaseModel](base: type[M], check: Callable[[M], list[str]], *, retries: int = 1) -> type[M]:
    """`base` whose instances must pass `check`: the first `retries` refusals go back to the model with the reasons, the next
    one raises `RetriesExhausted`."""
    refused = 0

    def _checks(self: Any) -> Any:
        nonlocal refused
        if errors := check(self):
            refused += 1
            if refused > retries:
                raise RetriesExhausted(" ".join(errors))
            raise ValueError(" ".join(errors))
        return self

    validator = cast(Any, model_validator(mode="after")(_checks))
    return create_model(base.__name__, __base__=base, __validators__={"_checks": validator})


def _norm(n: str) -> str:
    n = n.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else n


def numbers_of(blob: str) -> set[str]:
    return {_norm(m) for m in NUMBER.findall(blob)}


def invented_numbers(texts: list[str], *blobs: str) -> list[str]:
    """The numbers written in `texts` that none of `blobs` (the computed facts, as text) contains, sorted."""
    allowed: set[str] = set()
    for b in blobs:
        allowed |= numbers_of(b)
    return sorted({n for t in texts for n in numbers_of(t)} - allowed)
