"""Opening refresh cases (plan 9, P9-5.1, stories CR-01 and CR-08): one `contract_refresh` case per fleet contract whose
window has opened, once per term.

    scan(s, org_unit_id, today) -> [case id]   the canonical contracts that are due (refresh_window.due) and have no case
                                               for this term open one through `intake.open_case`
    run(s, today) -> {org: [case id]}          `scan` for each org unit with a registered fleet source (the job
                                               `refresh.scan`, which then queues itself for the next day)

- **Once per term.** The case's asset key is the contract id; its dedupe key is `<org>/<contractId>@<endDate>` (the org is in it:
  two orgs may each hold a case of one shared contract), so a renewed
  contract (a new end date) opens a new case and the same term never opens twice (`dedupe_as` of intake).
- **Facts.** `flow` `contract_refresh`, `contract_id`, `term_end`, `market`, the contract's customer, dates and status,
  the window (`window_opens`, `window_basis`) and the `lines` of canonical `contract_line` (serial, class, model, fee,
  months on contract). No route is valued yet: the later refresh tasks add tools, matching and pricing.
- **SLA.** Each case gets an exception item `refresh_late` due 5 working days after it opens (the pack's
  `valuer.params.contract_refresh.sla_working_days`, the process layer's `work.sla` timer): if no proposal closed it, it
  is escalated to the pack's `escalate_to`. The timer only asks someone else; it never decides anything.
No model step: the window, the due dates and the line facts are computed from canonical data. Never writes outside the
case store, the work items and the job queue; never approves anything.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.services.actions.registry import ActionError
from di.services.cases import intake, process, refresh_window
from di.services.modeler.pack import load_pack

REASON = "contract_refresh"
JOB = "refresh.scan"
EXCEPTION = "refresh_late"
PACK = "tool_fleet"


def settings() -> dict[str, Any]:
    """The tool-fleet pack's refresh settings (`valuer.params.contract_refresh`): window days, routes, stages, SLA."""
    return dict(load_pack(PACK).valuer.params["contract_refresh"])


# A record is the org's own when a source it came from is bound to the org or shared (no org unit). A record only another org's
# source gave is not: the tenant boundary of the scan (review H1). Each query spells the condition out (no formatted SQL).
def _contracts(s: Session, org_unit_id: str) -> list[dict[str, Any]]:
    rows = s.execute(
        text(
            "SELECT c.data FROM canonical c WHERE c.model = 'contract' AND EXISTS (SELECT 1 FROM provenance p "
            "LEFT JOIN source_system ss ON ss.id = p.source_id WHERE p.model = c.model AND p.key = c.key "
            "AND (ss.org_unit_id IS NULL OR ss.org_unit_id = :org)) ORDER BY c.key"
        ),
        {"org": org_unit_id},
    )
    return list(rows.scalars())


def _lines(s: Session, contract_id: str, org_unit_id: str) -> list[dict[str, Any]]:
    """The contract's tools from canonical `contract_line` of the org's own sources, by serial."""
    rows = s.execute(
        text(
            "SELECT c.key, c.data FROM canonical c WHERE c.model = 'contract_line' AND c.data ->> 'contract_id' = :c "
            "AND EXISTS (SELECT 1 FROM provenance p LEFT JOIN source_system ss ON ss.id = p.source_id "
            "WHERE p.model = c.model AND p.key = c.key AND (ss.org_unit_id IS NULL OR ss.org_unit_id = :org)) ORDER BY c.key"
        ),
        {"c": contract_id, "org": org_unit_id},
    )
    return [
        {"serial": r.key, "cls": r.data.get("tool_class"), "model": r.data.get("model"), "fee": r.data.get("fee_month"),
         "months": r.data.get("months_on_contract")}
        for r in rows
    ]  # fmt: skip


def _facts(s: Session, c: dict[str, Any], days: int, org_unit_id: str) -> dict[str, Any]:
    end = refresh_window.as_date(c["end_date"])
    notice = refresh_window.as_date(c.get("notice_date"))
    if end is None:  # not reached: due() only returns contracts with an end date
        raise ValueError(f"contract {c.get('contract_id')} has no end date")
    return {
        "flow": "contract_refresh", "contract_id": c["contract_id"], "term_end": end.isoformat(), "market": c.get("market"),
        "customer": c.get("customer"), "start_date": c.get("start_date"), "notice_date": notice.isoformat() if notice else None,
        "term_months": c.get("term_months"), "status": c.get("status"),
        "window_opens": refresh_window.window_opens(end, notice, days).isoformat(), "window_basis": refresh_window.basis(c),
        "lines": _lines(s, str(c["contract_id"]), org_unit_id),
    }  # fmt: skip


def _open_proposal_item(s: Session, case: dict[str, Any], org_unit_id: str, working_days: int) -> None:
    """The `refresh_late` item: due `working_days` after the case opens, owned by the exception's role (the pack)."""
    exc = next(e for e in load_pack(PACK).runtime.exception_types if e.id == EXCEPTION)
    now = clock.now()
    due_at = datetime.combine(refresh_window.add_working_days(now.date(), working_days), now.timetz())
    process.open_item(
        s, kind="exception", case_id=case["id"], org_unit_id=org_unit_id, type=EXCEPTION,
        title=f"Refresh proposal for {case['contract_id']} is due {due_at.date().isoformat()}",
        cause=f"The contract term ends {case['refresh']['term_end']}; the proposal is due {working_days} working days after "
        "the case opens.",
        action=exc.action, owner_role=process.role_of_owner(exc.owner_role),
        due_hours=(due_at - now).total_seconds() / 3600, by="system",
    )  # fmt: skip


def scan(s: Session, org_unit_id: str, today: date) -> list[str]:
    """Open a case for each due contract that has none for this term; the ids of the cases opened. In the caller's
    transaction (one savepoint per contract, so a refused one leaves the others)."""
    cfg = settings()
    days = int(cfg["window_days"])
    contracts = _contracts(s, org_unit_id)
    by_id = {str(c["contract_id"]): c for c in contracts if c.get("contract_id")}
    opened = []
    for cid in refresh_window.due(contracts, today, days):
        facts = _facts(s, by_id[cid], days, org_unit_id)
        i = {"org_unit_id": org_unit_id, "template_key": PACK, "asset_key": cid, "reason": REASON, "facts": facts,
             "dedupe_as": f"{org_unit_id}/{cid}@{facts['term_end']}", "by": "refresh scan"}  # fmt: skip
        try:
            with s.begin_nested():
                case = intake.open_case(s, i, "system")
                _open_proposal_item(s, case, org_unit_id, int(cfg["sla_working_days"]))
        except ActionError as e:
            if e.code == "duplicate":
                continue
            raise
        opened.append(case["id"])
    return opened


def fleet_orgs(s: Session) -> list[str]:
    """The org units with a registered fleet source (a source of type `fleet` bound to an org unit)."""
    rows = s.execute(text("SELECT DISTINCT org_unit_id FROM source_system WHERE type = 'fleet' AND org_unit_id IS NOT NULL"))
    return sorted(rows.scalars())


def run(s: Session, today: date, orgs: list[str] | None = None) -> dict[str, list[str]]:
    """The job `refresh.scan`: `scan` for each org unit with a fleet source (or the `orgs` the job names: a fleet source
    that is shared belongs to no org unit), then the next day's scan queued (database clock, key per day so the running
    job's own key does not hold it back)."""
    out = {org: scan(s, org, today) for org in (orgs or fleet_orgs(s))}
    queue_next(s, today)
    return out


def queue_next(s: Session, today: date) -> None:
    """Queue the scan of the day after `today` (a day later on the database clock; one job per day)."""
    at = s.execute(text("SELECT now()")).scalar_one() + timedelta(days=1)
    jobs.enqueue(s, JOB, {}, priority=200, run_after=at, dedupe_key=f"{JOB}:{(today + timedelta(days=1)).isoformat()}")


def ensure_queued(s: Session, today: date) -> bool:
    """Queue today's scan when no `refresh.scan` job is queued or running (the worker's periodic step; once a job runs it
    queues its own successor). True when it queued one."""
    if s.execute(text("SELECT 1 FROM job WHERE kind = :k AND status IN ('queued', 'running') LIMIT 1"), {"k": JOB}).first():
        return False
    jobs.enqueue(s, JOB, {}, priority=200, dedupe_key=f"{JOB}:{today.isoformat()}")
    return True


def close_proposal_item(s: Session, case_id: str, by: str) -> int:
    """Close the case's open `refresh_late` item: the proposal was submitted in time, so the timer has nothing to escalate (review
    M3). The number of items closed. In the caller's transaction."""
    ids = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": case_id, "t": EXCEPTION}
    ).scalars()
    n = 0
    for i in list(ids):
        process.close_item(s, i, "proposal submitted", by)
        n += 1
    return n
