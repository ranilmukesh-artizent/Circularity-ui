"""The injection task of the evals (plan 9, P9-2.15; stories X-02, X-05, X-15; F section 10 acceptance c and g).

    run_injection(inp) -> InjectionOut     plant the corpus text on one surface, run the agent with a model that obeys it
    corpus() -> [InjectionIn]              every surface file of `injection/` times its three planted instructions

A surface file holds the wrapper text a source system would put around a planted instruction. Source text reaches an agent
in one place, the case's evidence (`case.evidence`, an untrusted tool), whichever way it was ingested; the ingest paths have
their own tests. So five surfaces (evidence note, CSV cell of a manual import, MCP-client source record, adapter document
text, webhook payload) are planted as an evidence note of RT-1048 under the surface's source label, and the stage chain runs
with a stage model that obeys it. The sixth, the configuration-agent description, goes through `draft_change_set` with a
drafter model that obeys it. Each run is paired with the same scenario's run with no model and no planted text (`allowed`).
Never does: judge the result (`evaluators.py` does) or call a model that is not a `FunctionModel`.
"""

import json
from functools import cache
from pathlib import Path

from tests.evals.chain_task import run_chain
from tests.evals.config_task import run_config
from tests.evals.outcome import ChainIn, ChainOut, ConfigIn, InjectionIn, InjectionOut
from tests.evals.scripted import hostile_stage_loop, no_model

DIR = Path(__file__).resolve().parent / "injection"
CASE = "RT-1048"
EVIDENCE_KEY = "insp"


def corpus() -> list[InjectionIn]:
    out: list[InjectionIn] = []
    for f in sorted(DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in data["plants"]:
            out.append(InjectionIn(data["surface"], p["id"], data["wrapper"].replace("{plant}", p["text"]), p["goal"]))
    return out


def source_label(surface: str) -> str:
    return str(json.loads((DIR / f"{surface}.json").read_text(encoding="utf-8"))["source"])


@cache
def baseline() -> ChainOut:
    """The chain on the case with no model and no planted text (deterministic, so it is run once)."""
    return run_chain(ChainIn(CASE), loop=no_model())


def run_injection(inp: InjectionIn) -> InjectionOut:
    if inp.surface == "config_description":
        cfg = run_config(ConfigIn(inp.text, guard="recall", hostile=True))
        return InjectionOut(inp.surface, inp.goal, [], [], [], {}, {}, [], "", config=cfg)
    base = baseline()
    out = run_chain(ChainIn(CASE), hostile_stage_loop(inp.goal), plant=(EVIDENCE_KEY, inp.text, source_label(inp.surface)))
    return InjectionOut(
        inp.surface, inp.goal, out.journal, base.journal, out.proposals, out.stages, base.stages, out.readings, out.facts_blob
    )
