"""The tool fleet case panel's read (plan 9, P9-3.5, story TF-03; later tasks add gates, life, paths, plan, approval).

GET /api/screens/toolfleet/{case_id}
    {case_id, pack_version, flow, grade, gates, life, paths, plan, approval, followThrough}. `grade` is the grade the
    case is valued on and where it came from: `{grade, source: "workbench" | "estimate", ref, at, age_hours}` (the repair
    log's graded record with its test result, else the valuer's own estimate; `tool_inputs.grade_of`). The other fields
    are empty until the tasks that fill them (`life` null, `paths` [], `plan` null, `approval` null, `followThrough`
    null). `gates` (P9-3.6) is one row for each gate that applies to the case, as its gate step left it: `{id, name,
    passed, reason, guardrail, owner, kind, stage, stageLabel, hold, locked}`; a failed GR-07 (G-CON-2) says the term it
    failed on ("Theft recovered: claim CLM-7781 is open"). GR-13 (G-TOOL-TEL, P9-3.8) also has `age_days` (whole days since the
    tool's telematics were last seen, null with none) and `max_age_days`: its freshness line.
    `life` (P9-3.9) is the tool's computed wear (`tool_life.LifeResult`, kept on the case when its valuation ran): `{wti,
    rul_tool, rul_tool_hours, weakest, per_component: [{name, used_hours, consumed_pct, rul_pct, source}], confidence (High,
    Medium, Low), range ([low, high] RUL_tool without telematics, else null), inputs, table_version, rule_version}`; null
    for a case with neither telematics hours nor months on contract (it keeps its own inputs).
    `paths` (P9-3.12) are the six valued paths in the pack's order, `{k, name, ok, net, gross, cost, hold, why, lines: [{type,
    label, basis, amt}], dest}` (`dest` the named order it fills: a fleet renewal, sales order, bid, pool request or repair
    orders), against the org's live named demand (`di.repositories.tool_demand`); `best` is the recommended path, `second`
    the next eligible by net, `standard` the default path of the tool's function and `uplift` best net minus standard net.
    `quarantine` (P9-3.7) is the recall quarantine of the tool, `{recall_id, remedy, blocked, affected_parts, released}`
    (`released`: `{by, at, note}` once Quality released a repair recall), or null when no active recall names its serial.
    `approval` (P9-3.15) is who approves the decision: `{kind: "policy" | "person", role, appRole, reasons, holds, confidence,
    policy: {id, ver, owner} | null, by, text}`; `text` is "Approved by policy SP-1 v1 (owner admin)" or "Waits for the Fleet
    manager: Repair $702 is over $600 (GR-14)". Null before the case is valued.

Refuses as `screens.case.case_page` does: 403 out_of_scope without the case pages, 404 not_found for an unknown case (or a
case of another template), 403 tenant_boundary outside the account's tenants or warehouse.

Facade (frontend/src/api/toolFleet.ts) -> this API
| export | served by |
|---|---|
| toolFleetView | GET /{case_id} |

Never writes. Every write goes through the action pipeline.
"""

import dataclasses
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core import clock
from di.core.auth import Principal
from di.repositories import standing_policies
from di.repositories.context import load_case
from di.repositories.packs import active_pack
from di.services.cases import intake, regrade
from di.services.modeler import gates as gate_catalogue
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import fleet_evidence, tool_fleet, tool_inputs

GATE_KEYS = ("id", "name", "passed", "reason", "guardrail", "owner", "kind", "stage", "stageLabel", "hold", "locked")


def _gate(row: dict[str, Any], now: datetime, params: dict[str, Any]) -> dict[str, Any]:
    """The part of a case's gate row the panel shows; GR-13 (G-TOOL-TEL) adds the age of the telematics and its limit."""
    out = {k: row.get(k) for k in GATE_KEYS}
    if row.get("id") == fleet_evidence.TEL_GATE:
        seen = next(
            (e["value"].get("lastSeen") for e in row.get("evidence") or [] if e["type"] == fleet_evidence.TELEMATICS), None
        )
        out |= {
            "age_days": fleet_evidence.age_days(seen, now),
            "max_age_days": params.get("max_age_days", fleet_evidence.MAX_AGE_DAYS),
        }
    return out


def _approval(s: Session, c: dict[str, Any], pack: Pack) -> dict[str, Any] | None:
    """Who approves the decision (P9-3.15), as the decider left it on the case (`approvalRoute`, `approvalHolds`): `{kind
    "policy" | "person", role, appRole, reasons, holds, confidence, policy: {id, ver, owner} | null, by, text}`. `appRole` is
    the app role the role's approval item routes to (pack `roles`), `policy` the standing policy that approved it. Null
    before the case is valued."""
    r = c.get("approvalRoute")
    if not isinstance(r, dict):
        return None
    role = r.get("role")
    by = str((c.get("approval") or {}).get("by") or "")
    policy = None
    if by.startswith("policy "):
        pid, _, ver = by.removeprefix("policy ").partition(" v")
        row = standing_policies.get(s, pid)
        policy = {"id": pid, "ver": int(ver) if ver.isdigit() else None, "owner": row.owner if row else None}
        text = f"Approved by policy {pid} v{ver} (owner {policy['owner']})"
    elif by:
        text = f"Approved by {by}"
    elif r["kind"] == "person":
        text = f"Waits for the {role}: {r['reasons'][0]}"
    elif row := standing_policies.effective(s, pack.key, c["owner"]):
        text = f"Approved by policy {row.id} v{row.ver} (owner {row.owner}) when it is submitted"
    else:
        text = "Waits for a person: no standing policy is active"
    return {
        "kind": r["kind"], "role": role, "appRole": pack.roles.get(role) if role else None, "reasons": r["reasons"],
        "holds": c.get("approvalHolds") or [], "confidence": c.get("decisionConfidence"), "policy": policy, "by": by or None,
        "text": text,
    }  # fmt: skip


PATH_KEYS = ("k", "name", "ok", "net", "gross", "cost", "hold", "why", "lines", "dest")


def _paths(s: Session, c: dict[str, Any]) -> dict[str, Any]:
    """The six paths of the case (P9-3.12): the valuer's rows in the org's queue plan against the live named demand (the same
    plan the decision was made in), `ok` and `why` as the decision left them (a gate or a rule can exclude a path the valuer
    allows); `best` the recommended path, `second` the next eligible by net, `standard` the default path of the tool's
    function (`tool_fleet._default_path`) and `uplift` the best net over the standard's."""
    v = intake.valuer_input(c, "tool_fleet")
    if parts := fleet_evidence.blocked_parts(c):
        v["recallParts"] = sorted(parts)
    dec = intake.tool_plan(intake.tool_queue(s, c["owner"], v), intake.case_rules(s, c))["res"][v["id"]]
    routes = {r["id"]: r for r in c.get("routes") or []}
    rows: list[dict[str, Any]] = []
    for x in dec["all"]:
        r = routes.get(x["k"])
        row = {k: v for k, v in dict(x).items() if k in PATH_KEYS}
        row["name"] = r["plan"] if r else tool_fleet.PATHS[x["k"]]["name"]
        if r:
            row |= {"ok": not r["excluded"], "why": r["failReason"] if r["excluded"] else x["why"]}
        rows.append(row)
    best = (c.get("recommendation") or {}).get("id")
    eligible = sorted((r for r in rows if r["ok"] and r["k"] != best), key=lambda r: -r["net"])
    net = {r["k"]: r["net"] for r in rows}
    standard = dec["dk"]
    return {
        "paths": rows,
        "best": best,
        "second": eligible[0]["k"] if best and eligible else None,
        "standard": standard,
        "uplift": round(net[best] - net[standard], 2) if best else None,
    }


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one tool-fleet case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if c.get("template") != "tool_fleet":
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a tool fleet case."})
    valuer = c.get("valuer") or {}
    est = str(valuer.get("estGrade") or c.get("grade") or "C")
    pack = active_pack(s, "tool_fleet", c["owner"])
    params = next((g.params for g in gate_catalogue.pack_gates(pack) if g.id == fleet_evidence.TEL_GATE), {})
    now = clock.now()
    grade = tool_inputs.grade_of(regrade.workbench_evidence(s, c.get("serial") or c["assetId"]), est, now=now)
    return {
        "case_id": case_id,
        "pack_version": pack.version,
        "flow": c.get("flow") or "returns",
        "grade": dataclasses.asdict(grade),
        "quarantine": fleet_evidence.quarantine_of(c),
        "gates": [_gate(g, now, params) for g in c.get("gates") or []],
        "life": c.get("life"),
        **_paths(s, c),
        "plan": None,
        "approval": _approval(s, c, pack),
        "followThrough": None,
    }
