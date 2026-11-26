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
The latest case of the contract that has no outcome yet is the one written; a case is never changed again once it has one, so a
repeat sync records nothing. The source is read only (P9-3.1): nothing is written to it. No model step (R16), and no
action: this is
the system noting a fact it was told, not a person's `outcome.confirm`, which is unchanged and forbidden to agents.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
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
        cid = s.execute(
            text(
                "SELECT id FROM case_record WHERE data ->> 'flow' = 'contract_refresh' "
                "AND data -> 'refresh' ->> 'contract_id' = :c AND data -> 'renewalOutcome' IS NULL ORDER BY id DESC LIMIT 1"
            ),
            {"c": r.key},
        ).scalar()
        if cid is None:
            continue
        c = store.get(s, cid, for_update=True)
        if c is None:
            continue
        c["renewalOutcome"] = outcome_of(c, r.data["renewal_status"], r.data.get("fee_month"), today)
        store.save(s, c)
        done.append(cid)
    return done
