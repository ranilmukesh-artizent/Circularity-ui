"""The eval suites (plan 9, P9-2.15): each dataset with its task, and the one way to run them.

    SUITES                       name -> (dataset factory, task); `LIVE` names the ones that make sense against a real model
    run_suite(name) -> report    `Dataset.evaluate_sync` one case at a time (the tasks reset and share the one database)

pydantic-evals 2.73: `Dataset.evaluate_sync(task, *, name=None, max_concurrency=None, progress=True, ...)` runs `task` on
every case's inputs and every evaluator on the outputs. `max_concurrency=1` because the tasks start from the demo's starting
state; `progress=False` keeps the output of a run quiet. Owns: the wiring. Never does: judge a report (`scoring.py`).
"""

from collections.abc import Callable
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from tests.evals import datasets
from tests.evals.chain_task import run_chain
from tests.evals.config_task import run_config
from tests.evals.injection_task import run_injection
from tests.evals.model_first_task import run_model_first

SUITES: dict[str, tuple[Callable[[], Dataset[Any, Any, Any]], Callable[[Any], Any]]] = {
    "chain_cases": (datasets.chain_cases, run_chain),
    "config_agent": (datasets.config_agent, run_config),
    "injection": (datasets.injection, run_injection),
    "model_first": (datasets.model_first, run_model_first),
    "toolsets": (datasets.toolsets, datasets.toolset_of),
}
# Against a real model: the scripted-model paths (model_first) and the toolset check say nothing about it.
LIVE = ("chain_cases", "config_agent", "injection")


def run_suite(name: str) -> EvaluationReport[Any, Any, Any]:
    make, task = SUITES[name]
    return make().evaluate_sync(task, name=name, max_concurrency=1, progress=False)
