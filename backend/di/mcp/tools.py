"""The tool table: the demo's ten tools (fixtures/golden/tools.json, TOOLS), each with the action(s) it runs and how
its answer is shaped (index.html, `runTool`, one `case` per tool).

    tool                      action(s), through di.services.actions.pipeline.invoke     answer
    get_case_evidence         case.evidence                                     evidence with source and freshness
    list_eligible_routes      case.routes                                       eligible routes, excluded with the gate
    predict_outcomes          case.routes                                       P10/P50/P90 of one eligible route
    optimize_pool             pool.optimize (pool_id is the pool's case)        greedy against pool-optimal
    find_demand               demand.find                                       demand per route
    get_model_validation      analytics.models                                  error, bias, coverage of a version
    request_missing_evidence  evidence.request                                  the request sent to the owner
    request_approval          decision.submit, then held for a person           held: the approval request
    send_instruction          (approval reference checked) instruction.resend   the approved instruction, deduplicated
    reconcile_outcome         none: reads the closed decision (the demo's ROWS)  predicted against actual

A tool runs the action first, so every refusal of the pipeline (permission, tenant boundary, warehouse lock, agent
gate, state guard, duplicate) comes back as the tool's refusal. Its answer is shaped from the action's output; a few
fields the demo's tool shows and the action's output does not carry (the asset id, the model version, the approval
record) are read from the case after the action allowed the call.

reconcile_outcome has no action to call: the closed decisions are reference data (the Analytics reads serve them
the same way) and the demo's tool only reads one. Its tenant check is done here, for the account and the tenant.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from di.core import policy
from di.repositories.common import AS_OF, fmt_dy, hash_id, to_fixed
from di.repositories.constants import AGENTS_BY_ID, HARD_RULES, TOOLS_BY_ID
from di.repositories.decisions import all_rows, model_stats
from di.services.actions.pipeline import CallContext, invoke

TOOLS: dict[str, dict] = TOOLS_BY_ID  # keyed by id (the tables below and di.mcp.policy look tools up by id)
AGENTS: dict[str, dict] = AGENTS_BY_ID
NO_APPROVAL_REF = HARD_RULES[2]  # "Nothing is sent to an enterprise system without an approval reference."

# the action(s) each tool may run; policy.py asserts none of them is one an agent must never reach
ACTIONS_OF: dict[str, tuple[str, ...]] = {
    "get_case_evidence": ("case.evidence",),
    "list_eligible_routes": ("case.routes",),
    "predict_outcomes": ("case.routes",),
    "optimize_pool": ("pool.optimize",),
    "find_demand": ("demand.find",),
    "get_model_validation": ("analytics.models",),
    "request_missing_evidence": ("evidence.request",),
    "request_approval": ("decision.submit",),
    "send_instruction": ("instruction.resend",),
    "reconcile_outcome": (),
}


class Refused(Exception):
    """A tool's refusal: the demo's code and message (and extra fields beside them). `step` is the detail of the
    failed "Run tool" step in the trace; None when the tool already wrote its own failed step."""

    def __init__(self, code: str, message: str, extra: dict | None = None, step: str | None = None):
        super().__init__(message)
        self.code, self.message, self.extra, self.step = code, message, extra or {}, step


@dataclass
class ToolCall:
    """One tool call after the checks: its arguments (only the declared ones), the case they name (or None), the
    tenant it acts for, and the pipeline context (the account, with the agent as preparer)."""

    tool: dict
    args: dict[str, Any]
    case: dict | None
    tenant: str | None
    ctx: CallContext
    step: Callable[[str, bool, str], bool]

    def act(self, action_id: str, i: dict[str, Any], ok_codes: tuple[str, ...] = ()) -> dict | None:
        """Run an action through the pipeline. A refusal becomes the tool's refusal, unless its code is in
        `ok_codes` (then None is returned: e.g. a duplicate submit means the request already stands)."""
        if action_id not in ACTIONS_OF[self.tool["id"]]:  # the tool table is the only way from a tool to an action
            raise RuntimeError(f"{self.tool['id']} may not run {action_id}")
        r = invoke(action_id, i, self.ctx)
        if r["ok"]:
            return r["output"]
        e = r["error"]
        if e["code"] in ok_codes:
            return None
        extra = {k: v for k, v in e.items() if k not in ("code", "message")}
        raise Refused(e["code"], e["message"], extra, step=f"{action_id}: {e['code']}")

    def run(self, action_id: str, i: dict[str, Any]) -> dict[str, Any]:
        """act() with no accepted refusal codes: a refusal raises, so there is always an output."""
        return cast(dict[str, Any], self.act(action_id, i))

    def need_case(self) -> dict:
        if self.case is None:
            raise Refused("not_found", f"No live case {self.args.get('case_id', '')}.", step="Unknown case")
        return self.case


def _defined(d: dict) -> dict:
    """Leave out what the demo leaves undefined (JSON drops undefined; the server's reads say null)."""
    return {k: v for k, v in d.items() if v is not None}


def _fixed3(x: float) -> float:
    """`+x.toFixed(3)`, for either sign."""
    return float(("-" if x < 0 else "") + to_fixed(abs(x), 3))


# ---------------------------------------------------------------- the tools, in the demo's order
def get_case_evidence(t: ToolCall) -> dict:
    out = t.run("case.evidence", {"case_id": t.args["case_id"]})
    c = t.need_case()
    items = out["items"]
    return {
        "case_id": c["id"],
        "asset_id": c["assetId"],
        "tenant": c["owner"],
        "readiness": f"{sum(1 for e in items if e['state'] == 'ready')}/{len(items)}",
        "evidence": [
            _defined({"item": e["label"], "state": e["state"], "source": e.get("source"), "freshness": e.get("fresh")})
            for e in items
        ],
    }


def list_eligible_routes(t: ToolCall) -> dict:
    out = t.run("case.routes", {"case_id": t.args["case_id"]})
    c = t.need_case()
    if c.get("blocked") and not c.get("recommendation"):
        b = c["blocked"]
        return {"case_id": c["id"], "withheld": True, "failed_gate": b["gateName"], "reason": b["reason"]}
    result = {
        "case_id": c["id"],
        "eligible": [
            _defined({"rank": r["rank"], "plan": r["plan"], "expected_net_usd": r["net"], "p10": r["p10"], "p90": r["p90"],
                      "demand": r["demand_status"]})
            for r in out["eligible"]
        ],
    }  # fmt: skip
    if t.args.get("include_excluded") is not False:
        result["excluded"] = [{"plan": r["plan"], "failed_gate": r["gate"], "reason": r["reason"]} for r in out["excluded"]]
    return result


def predict_outcomes(t: ToolCall) -> dict:
    t.act("case.routes", {"case_id": t.args["case_id"]})
    c = t.need_case()
    if not c.get("predictions") and not c.get("recommendation"):
        return {"case_id": c["id"], "withheld": True, "reason": "Insufficient evidence for a validated prediction"}
    want = t.args.get("route")
    # an excluded route failed a gate: it has no prediction an agent could act on (hard rule: no waiving a gate)
    r = next((x for x in c["routes"] if x["id"] == want and not x["excluded"]), None) if want else c.get("recommendation")
    if not r:
        raise Refused(
            "route_not_eligible",
            f'Route "{want if want else "undefined"}" is excluded or not evaluated for {c["id"]}.',
            step="Route not eligible",
        )
    return _defined({
        "case_id": c["id"], "route": r["id"], "plan": r["plan"], "expected_net_usd": r["net"], "p10": r["p10"],
        "p50": r["net"], "p90": r["p90"], "model_version": c.get("model"), "evidence_date": fmt_dy(AS_OF),
        "uncertainty": r.get("unc"),
    })  # fmt: skip


def optimize_pool(t: ToolCall) -> dict:
    pid = t.args["pool_id"]
    owner: Any = (t.case or {}).get("owner")
    if t.case is not None and t.tenant and owner != t.tenant:  # the pool's case: tenant consent, as for any case
        detail = f"{owner} pool requested on behalf of {t.tenant}"
        raise Refused("tenant_boundary", cross_tenant(pid, owner, t.tenant), step=detail)
    try:
        out = t.run("pool.optimize", {"case_id": pid})
    except Refused as e:
        if e.code != "not_found":
            raise
        raise Refused("pool_not_found", f"No pool for {pid}. Try RT-1048 or RT-1052.", step="No pool") from None
    return {
        "pool": pid,
        "per_asset_greedy_usd": out["greedy"],
        "pool_optimized_usd": out["optimal"],
        "uplift_usd": out["uplift"],
        "allocation": out["allocation"],
        "duplicate_allocation": False,
        "checked": "every unit and demand line allocated once",
    }


def find_demand(t: ToolCall) -> dict:
    out = t.run("demand.find", {"case_id": t.args["case_id"]})
    return {
        "case_id": out["case_id"],
        "demand": [
            _defined({"route": d["route"], "demand": d["demand"], "status": d["status"], "eligible": d["eligible"]})
            for d in out["demand"]
        ],
    }


def get_model_validation(t: ToolCall) -> dict:
    t.act("analytics.models", {})
    s = model_stats(t.args["version"])  # the statistics analytics.models reports, for one version
    if not s:
        raise Refused("unknown_version", "Unknown model version. Try v1.0 to v1.3.", step="Unknown version")
    return {
        "version": s["v"],
        "closed_cases": s["n"],
        "mape": _fixed3(s["mape"]),
        "bias": _fixed3(s["bias"]),
        "p10_p90_coverage": _fixed3(s["cov"]),
    }


def request_missing_evidence(t: ToolCall) -> dict:
    c = t.need_case()
    if not c.get("blocked") and all(e["state"] == "ready" for e in c.get("evidence") or []):
        raise Refused("nothing_to_request", f"{c['id']} has no missing evidence.", step="Nothing missing")
    out = t.run("evidence.request", {"case_id": c["id"]})
    return {"case_id": c["id"], "request_ref": out["ref"], "kind": t.args["kind"], "sent_to": out["to"], "status": "sent"}


def request_approval(t: ToolCall) -> dict:
    c = t.need_case()
    # the agent may submit; a submit already on file means the request stands
    t.act("decision.submit", {"case_id": c["id"]}, ok_codes=("duplicate",))
    # hard rule: a write tool stops at a human approval; only a person approves, in the approval card
    t.step("Hold for human approval", False, "Write tool: a person must approve")
    raise Refused(
        "held",
        "Held for human approval. Nothing is committed until an Approver accepts it in Product.",
        {"approval_request": "AQ-" + hash_id(c["id"] + t.args["rationale"])[:6], "case_url": "#/product/" + c["id"]},
    )


def send_instruction(t: ToolCall) -> dict:
    c = t.need_case()
    ref, appr = t.args["approval_ref"], c.get("approval")
    # hard rule: nothing is sent without the approval a person recorded on this case
    if not appr or appr["ref"] != ref:
        t.step("Verify approval reference", False, f"No approval {ref} on record for {c['id']}")
        raise Refused(
            "approval_required",
            f"No human approval {ref} is recorded for {c['id']}. Instructions cannot be sent without one.",
            {"hint": f"Recorded reference is {appr['ref']}" if appr else "Approve the case in Product first."},
        )
    t.step("Verify approval reference", True, appr["ref"])
    # the approval sent the instruction; this sends it again under the same idempotency key (a retry is a no-op)
    t.act("instruction.resend", {"case_id": c["id"]}, ok_codes=("duplicate",))
    x = c["exec"]
    return {
        "case_id": c["id"],
        "decision_id": x["decisionId"],
        "approval_ref": appr["ref"],
        "instruction_version": x["instruction"],
        "destination": x["steps"][0]["sys"],
        "idempotency_key": "idem-" + hash_id(c["id"] + x["ref"])[:6].lower(),
        "deduplicated": True,
        "note": "Instruction already delivered; repeated call created nothing new",
    }


def reconcile_outcome(t: ToolCall) -> dict:
    cid = t.args["case_id"]
    r = next((x for x in all_rows() if x["id"] == cid), None)
    if r is None:
        raise Refused("case_not_found", f"No closed case {cid}. Try CS-2041.", step="Unknown closed case")
    acct, pctx = t.ctx.actor.account, t.ctx.actor.ctx
    if (t.tenant and r["tenant"] != t.tenant) or (acct and not policy.tenant_ok(acct, r["tenant"], pctx)):
        raise Refused(
            "tenant_boundary",
            cross_tenant(cid, r["tenant"], t.tenant or (acct.label if acct else "")),
            step=f"{r['tenant']} decision",
        )
    if r["status"] == "pending":
        return {"case_id": cid, "status": "pending", "note": "Evidence incomplete. Pending cases are not treated as failures."}
    return {
        "case_id": cid,
        "status": r["status"],
        "route": r["route"],
        "predicted_p50": r["p50"],
        "actual": r["actual"],
        "variance": None if r["actual"] is None else r["actual"] - r["p50"],
        "model_version": r["model"],
        "evidence_snapshot": r["snapshot"],
        "linked": True,
    }


def cross_tenant(record: str, owner: str, tenant: str) -> str:
    """The demo's tenant-boundary message for a tool call."""
    return f"Case {record} belongs to {owner}. Cross-client access needs customer consent, which is not on file for {tenant}."


RUN: dict[str, Callable[[ToolCall], dict]] = {
    "get_case_evidence": get_case_evidence,
    "list_eligible_routes": list_eligible_routes,
    "predict_outcomes": predict_outcomes,
    "optimize_pool": optimize_pool,
    "find_demand": find_demand,
    "get_model_validation": get_model_validation,
    "request_missing_evidence": request_missing_evidence,
    "request_approval": request_approval,
    "send_instruction": send_instruction,
    "reconcile_outcome": reconcile_outcome,
}
assert set(RUN) == set(TOOLS) == set(ACTIONS_OF), "every tool in TOOLS needs a runner and an action mapping"  # noqa: S101 - import-time check of the tool tables


def schema(t: dict) -> dict:
    """The demo's schemaOf: a JSON Schema for the tool's input (types, required fields, an example value)."""
    props = {k: {"type": v["t"], **({"examples": [v["ex"]]} if "ex" in v else {})} for k, v in t["input"].items()}
    return {"type": "object", "properties": props, "required": [k for k, v in t["input"].items() if v.get("req")]}
