"""A renewal's outcome recorded on its refresh case (plan 9, P9-5.7, story CR-07). Arithmetic on the contract's own facts.

    record(s) -> [case id]   for each contract the fleet system moved to `renewed` or `lapsed`, write `renewalOutcome` on its
                             refresh case once (called after each sync of the fleet source: `FleetContractsAdapter.after_sync`)

`renewalOutcome` is `{renewed, status, recorded_on, had_proposal, fee_before, fee_after, swaps_accepted, predicted: {likelihood,
fee_month} | None}`:
- `renewed` and `status` come from the contract's `renewal_status`; `recorded_on` is the day of the sync;
- `fee_before` is the sent proposal's current fee a month, else the sum of the case's lines' fees; `fee_after` is the
  contract's own
  fee a month once renewed (None for a lapse or a contract that shows none);
- `swaps_accepted` is the number of swaps and upgrades of the proposal that was sent when the contract renewed (the
  customer renewed
  on the drafted lines), 0 for a lapse or when nothing was sent;
- `predicted` is what the proposal said: its renewal likelihood and its fee a month (None without a proposal).
The oldest case of the contract that has no outcome yet is the one written; a case is never changed again once it has one, so a
repeat sync records nothing. A status an earlier term already recorded is not the next term's: the later case takes it only when
the contract's end date has moved past that case's term (review M6), so a source that keeps `renewed` does not close the next
term's case on its first sync. The source is read only (P9-3.1): nothing is written to it. No model step (R16), and no
action: this is
the system noting a fact it was told, not a person's `outcome.confirm`, which is unchanged and forbidden to agents.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import unit_reservations
from di.services.cases import store

STATUSES = ("renewed", "lapsed")
SWAPS = ("swap", "upgrade")


def _proposal(c: dict[str, Any]) -> dict[str, Any] | None:
    """The proposal that was sent (the plan's), else the one priced for the decision."""
    return (c.get("exec") or {}).get("proposal") or (c.get("refreshProposal") or {}).get("proposal")


def _fee(x: Any) -> float | None:
    return None if x is None else float(x)


def outcome_of(c: dict[str, Any], status: str, contract_fee: Any, today: str) -> dict[str, Any]:
    """The `renewalOutcome` of a case whose contract moved to `status` (module docstring)."""
    sent = (c.get("exec") or {}).get("proposal")
    doc = _proposal(c)
    renewed = status == "renewed"
    lines = (c.get("refresh") or {}).get("lines") or []
    before = (doc or {}).get("fee_month_current")
    return {
        "renewed": renewed, "status": status, "recorded_on": today, "had_proposal": sent is not None,
        "fee_before": float(before) if before is not None else round(sum(float(x.get("fee") or 0) for x in lines), 2),
        "fee_after": _fee(contract_fee) if renewed else None,
        "swaps_accepted": sum(1 for x in (sent or {}).get("lines") or [] if x.get("action") in SWAPS) if renewed else 0,
        "predicted": None if doc is None else {
            "likelihood": doc.get("renewal_likelihood"), "fee_month": doc.get("fee_month_proposed")
        },
    }  # fmt: skip


def _case_of(s: Session, contract_id: str, data: dict[str, Any]) -> str | None:
    """The refresh case the contract's status belongs to (module docstring): the oldest of its cases without an outcome, unless an
    earlier term already recorded this status and the contract has not moved past the case's term."""
    rows = s.execute(
        text(
            "SELECT id, data -> 'refresh' ->> 'term_end' AS term_end, data -> 'renewalOutcome' ->> 'status' AS status "
            "FROM case_record WHERE data ->> 'flow' = 'contract_refresh' AND data -> 'refresh' ->> 'contract_id' = :c "
            "ORDER BY data -> 'refresh' ->> 'term_end', id"
        ),
        {"c": contract_id},
    ).all()
    open_ = [r for r in rows if r.status is None]
    if not open_:
        return None
    case, end = open_[0], str(data.get("end_date") or "")[:10]
    if any(r.status == data.get("renewal_status") and (r.term_end or "") < (case.term_end or "") for r in rows):
        return str(case.id) if end > (case.term_end or "") else None  # the same status again: only once the term has been passed
    return str(case.id)


def record(s: Session) -> list[str]:
    """Write the outcome on the refresh case of each renewed or lapsed contract that has one open; the case ids. In the caller's
    transaction."""
    today = clock.now().date().isoformat()
    contracts = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'contract' AND data ->> 'renewal_status' = ANY(:st) ORDER BY key"),
        {"st": list(STATUSES)},
    ).all()
    done: list[str] = []
    for r in contracts:
        cid = _case_of(s, r.key, r.data)
        if cid is None:
            continue
        c = store.get(s, cid, for_update=True)
        if c is None:
            continue
        c["renewalOutcome"] = outcome_of(c, r.data["renewal_status"], r.data.get("fee_month"), today)
        store.save(s, c)
        if r.data["renewal_status"] == "renewed":
            unit_reservations.consume(s, cid)  # the customer renewed on the swaps: the units are theirs
        else:
            unit_reservations.release(s, cid)  # a lapse frees the units for other contracts (review M2)
        done.append(cid)
    return done
