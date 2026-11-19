"""The live cases as the engine evaluates them, until di holds cases itself (B11 moves them into the database).

Each case's inputs come from the golden cases: its facts, and its route drafts (the terms as valued). The engine
then computes the gates, nets, ranges, ranks and recommendation; nothing computed is copied from the golden file.
The demo's hand-modelled cases (the heroes and their pool partners) keep their hand-set exclusions; every other
case runs the gate rules.
"""

import copy
from functools import cache

from di import golden
from di.engine.evaluate import draft_of, evaluate

HAND_MODELLED_PARTNERS = {"RT-1062", "RT-1044"}  # hand-written in the demo but not flagged as heroes


def hand_modelled(c: dict) -> bool:
    return bool(c.get("hero")) or c["id"] in HAND_MODELLED_PARTNERS


def inputs_of(c: dict) -> tuple[dict, list[dict], bool]:
    """A golden case split into the engine's inputs: the case facts, the route drafts, and whether the rules run."""
    hand = hand_modelled(c)
    facts = {k: copy.deepcopy(v) for k, v in c.items() if k not in ("routes", "recommendation", "poolResult")}
    # The recycler's requirement for a hazardous-waste route is a source fact; the demo drew it at random.
    facts["hazardousMaterial"] = any(r["id"] == "material" and r.get("failGate") == 5 for r in c["routes"])
    return facts, [draft_of(r, keep_exclusion=hand) for r in c["routes"]], not hand


def evaluated(c: dict) -> dict:
    facts, drafts, rules = inputs_of(c)
    routes, rec = evaluate(facts, drafts, rules)
    return facts | {"routes": routes, "recommendation": rec}


@cache
def _book() -> dict[str, dict]:
    return {c["id"]: evaluated(c) for c in golden.load("cases")}


def get(case_id: str) -> dict | None:
    return _book().get(case_id)
