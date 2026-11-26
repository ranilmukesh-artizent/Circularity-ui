"""The battery assessment an EV waits for (plan 9, P9-9.14, story UC-14; diversion `DV-UC-EV` of a customer's overlay).

    waiting(case, diversions) -> Diversion | None   the matched step diversion `battery_assessment` while the result is missing
    hold(case, routes, d)                           no channel is valued: every route fails with the reason, the case is held
    holding(case) -> bool                           the case is held for the assessment
    request(s, case) -> int | None                  queue the `battery_assessment` instruction to the inspection app (uc_insp)

A customer adds the step with the overlay operation `add_step` (I-4): "EV with battery health under 80 percent". `decide_case`
(R19) finds it among the pack's matched diversions after the gates (R20) and, while `condition.battery_assessment_result` is not
on file, holds the case (`gateHold` with the gate id `battery_assessment`, no recommendation, stage `none`) and values nothing.
Intake then queues the one instruction (`request`): one row and one `instruction.send` job, idempotent on the case and the car's
VIN, so a second look never orders a second assessment. When the inspection app's adapter writes the result,
`canonical.store.apply` queues `case.gateRecheck`, which values the case again: with the result on file the hold clears and the
channels are priced on their own. NS-BAT-01 (P9-12.7) builds on this entry point.
Never does: read a clock other than the workspace's, call the inspection app (the writer does, `instructions.writers`), decide
which channel wins, or approve anything. The assessment's wording is product text; Kinective's Legal team reviews it before it
is relied on.
"""

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.core.config import get_settings
from di.services.engine.routes import POLICY, Route, fail
from di.services.modeler.pack import Diversion

STEP = "battery_assessment"  # the diversion's step, the instruction kind and the hold's gate id
RESULT = "condition.battery_assessment_result"
SYSTEM = "uc_insp"
REASON = "Waiting for the battery assessment before any channel is priced"


def _fact(case: Mapping[str, Any], path: str) -> Any:
    cur: Any = case
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return case.get(path)
        cur = cur[part]
    return cur


def waiting(case: Mapping[str, Any], diversions: Sequence[Diversion]) -> Diversion | None:
    """The first matched `battery_assessment` step while the assessment's result is not on file, else None."""
    if _fact(case, RESULT) not in (None, ""):
        return None
    return next((d for d in diversions if d.kind == "step" and d.step == STEP), None)


def hold(case: MutableMapping[str, Any], routes: list[Route], d: Diversion) -> None:
    """Value nothing: each route fails with `REASON` (naming the diversion), and the case is held with no recommendation, as a
    gate hold is (the time it has been held since stays)."""
    for r in routes:
        if not r["excluded"]:
            fail(r, POLICY, f"{REASON} ({d.op_id})")
    prior = case.get("gateHold") or {}
    case["gateHold"] = {"gates": [STEP], "since": prior.get("since") or clock.now().isoformat(), "batch": case.get("batchRef")}
    case["recommendation"] = None
    case["stage"] = "none"


def holding(case: Mapping[str, Any]) -> bool:
    gh = case.get("gateHold")
    return isinstance(gh, Mapping) and list(gh.get("gates") or []) == [STEP]


def _vin(case: Mapping[str, Any]) -> str:
    v = (case.get("vehicle") or {}).get("vin")
    return str(v or str(case.get("assetId") or "").rpartition(":")[2])


def enabled() -> bool:
    """Instructions are sent only when the service has them switched on (as `instructions.queue.enabled`, which the cases layer
    may not import)."""
    return get_settings().instructions


def request(s: Session, case: Mapping[str, Any]) -> int | None:
    """Queue the assessment (only when sending instructions is switched on): the key is `BATTERY.<case>.<VIN>`; a case already
    asked keeps its row, and a request already sent is never queued again. The step is outside an approval's plan, so its
    reference is the case's own. Returns the row id, None when nothing was queued."""
    vin = _vin(case)
    if not enabled() or not vin:
        return None
    ref, key = f"BATTERY-{case['id']}", f"BATTERY.{case['id']}.{vin}"
    iid = s.execute(
        text(
            "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
            "VALUES (:c, :r, 0, :k, :sys, :key, CAST(:refs AS jsonb), :at) ON CONFLICT DO NOTHING RETURNING id"
        ),
        {"c": case["id"], "r": ref, "k": STEP, "sys": SYSTEM, "key": key, "refs": f'["{key}"]', "at": clock.now()},
    ).scalar()
    if iid is not None:
        jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    return int(iid) if iid is not None else None
