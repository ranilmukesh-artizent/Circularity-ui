"""Decision-engine read actions (docs/BACKEND_STEPS.md, B10): what-if and pool optimisation.
Both are read-only: nothing is stored, and the approved decision is unchanged."""

from di.actions.registry import ActionError, guard, implement
from di.cases import store
from di.engine.pool import solve_pool
from di.engine.scenario import what_if


def _case(ctx, case_id: str) -> dict:
    c = store.get(ctx.session, case_id)
    if c is None:
        raise ActionError("not_found", f"No case {case_id}.")
    return c


@implement("case.whatIf")
def case_what_if(i, ctx):
    return what_if(_case(ctx, i["case_id"]), i)


@guard("pool.optimize")
def pool_guard(i, ctx):
    c = store.get(ctx.session, i["case_id"])
    return None if c is None or c.get("pool") else ("not_found", f"{i['case_id']} is not in a pool.")


@implement("pool.optimize")
def pool_optimize(i, ctx):
    c = _case(ctx, i["case_id"])
    p = solve_pool(c["pool"])
    return {
        "case_id": c["id"],
        "greedy": p["greedy"]["total"],
        "optimal": p["optimal"]["total"],
        "uplift": p["uplift"],
        "allocation": p["optimal"]["alloc"],
        "note": c["pool"].get("note") or "",
    }
