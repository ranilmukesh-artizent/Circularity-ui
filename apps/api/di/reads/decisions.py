"""The closed decisions (the demo's ROWS) and the model versions' accuracy over them (the demo's REC and modelStats).

Read by the Analytics, Data Checks and Command Center screens, the read actions and the MCP tools.
"""

from di import golden
from di.engine.jsmath import js_sum


def median(a: list[float]) -> float:
    """The demo's med."""
    if not a:
        return 0
    s, m = sorted(a), len(a) >> 1
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def all_rows() -> list[dict]:
    """The demo's ROWS: every closed decision, all tenants."""
    return golden.load("decisions")


def reconciled() -> list[dict]:
    """The demo's REC(): every reconciled closed decision (all tenants)."""
    return [r for r in all_rows() if r["status"] == "reconciled"]


def model_stats(v: str) -> dict | None:
    """The demo's modelStats(v): error, bias and P10-P90 coverage of a model version (exit routes and overrides out)."""
    r = [x for x in reconciled() if x["model"] == v and x["route"] != "exit" and not x.get("override")]
    n = len(r)
    if not n:
        return None
    mape = js_sum(abs(x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) for x in r) / n
    bias = js_sum((x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) for x in r) / n
    cov = sum(1 for x in r if x["p10"] <= x["actual"] <= x["p90"]) / n
    return {"v": v, "n": n, "mape": mape, "bias": bias, "cov": cov}


def metrics(rows: list[dict]) -> dict:
    """The demo's metrics, the totals the screens show."""
    rc = [r for r in rows if r["status"] == "reconciled"]
    base, act = js_sum(r["baseline"] for r in rc), js_sum(r["actual"] for r in rc)
    days = median([r["days"] for r in rc])
    return {"rc": rc, "base": base, "act": act, "uplift": act - base, "avoided": js_sum(r["avoided"] for r in rc), "days": days}
