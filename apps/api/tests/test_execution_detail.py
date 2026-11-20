"""B13: the execution detail and cost trace give the demo's answers (fixtures/golden/execution.json).

For each case of the read fixture with routes, on the starting state: the plan (exPlan at the as-of time), the move
(exMove), the what-if guidance (exWhatIf) and the cost lines of every term of every eligible route (exTrace).

The dump writes Dates as ISO strings, rounds numbers to 1e-6 and drops functions (the move's day()); the port keeps
times as epoch milliseconds, so they are written the same way here before comparing.
"""

import pytest

from di import golden
from di.cases import store
from di.db import SessionLocal
from di.engine.jsmath import js_round
from di.execution import ex_move, ex_plan, ex_trace, ex_what_if
from di.reads.common import iso
from tests.helpers import strict

EXECUTION = golden.load("execution")
TIMES = {"d0", "eta", "etd", "need", "repairAt", "readyAt", "t0", "due", "due2"}  # the demo's Date fields


def plain(v, key: str | None = None):
    """The dump's plain(): times as ISO strings, numbers rounded to 1e-6, tuples as lists."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, int | float):
        return iso(v) if key in TIMES else js_round(v * 1e6) / 1e6
    if isinstance(v, dict):
        return {k: plain(x, k) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [plain(x) for x in v]
    return v


@pytest.fixture(scope="module")
def cases():
    store.reset()
    with SessionLocal() as s:
        yield {cid: store.get(s, cid) for cid in EXECUTION}


@pytest.mark.parametrize("case_id", list(EXECUTION))
def test_execution_detail(cases, case_id):
    exp, c = EXECUTION[case_id], cases[case_id]
    r = c.get("chosen") or c.get("recommendation")
    assert (r["plan"] if r else None) == exp["route"]
    assert strict(plain(ex_plan(c, r) if r else [])) == strict(exp["plan"]), "plan"
    assert strict(plain(ex_move(c, r) if r else None)) == strict(exp["move"]), "move"
    assert strict(plain(ex_what_if(c, r) if r else [])) == strict(exp["what_if"]), "what_if"
    traces = [{"plan": x["plan"], "terms": [ex_trace(c, x, t) for t in x["terms"]]} for x in c["routes"] if not x["excluded"]]
    assert len(traces) == len(exp["traces"])
    for got, want in zip(traces, exp["traces"], strict=True):
        assert got["plan"] == want["plan"]
        for k, (g, w) in enumerate(zip(got["terms"], want["terms"], strict=True)):
            assert strict(plain(g)) == strict(w), f"{want['plan']} term {k} ({w['label']})"


def test_step_tables_agree():
    """di.reads.common keeps each step's time limit and owner for the reads (it cannot import di.execution, which
    builds on it); both must say the same as the full step table."""
    from di.execution import EX_STEP
    from di.reads.common import EX_STEP as LIMITS

    assert {k: (d["lim"], d["owner"]) for k, d in EX_STEP.items()} == LIMITS
