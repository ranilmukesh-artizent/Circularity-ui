"""The renewal outcomes of the fleet's contracts, for the Analytics comparison (plan 9, P9-5.7, story CR-07). A read only.

    outcomes(s, org_unit_ids, since, until) -> [RenewalOutcome]   the ended contracts of the period in these org units
    history_org(s) -> str                                          the org unit the fleet's history belongs to

Two kinds of row, each a contract that renewed or lapsed:
- the fleet source's `history` (di.repositories.contract_history): ended in the period (`endedAt`). The history carries no
  owner, so it belongs to the org unit the fleet source is bound to (`history_org`: the workspace when it is bound to none), and
  no contract age, so its `age_band` is "unknown";
- a refresh case that has a `renewalOutcome` (di.services.refresh_outcome): recorded in the period. Its owner is the case's.

The size band is the one the renewal odds use (di.services.modeler.valuers.renewal_odds.size_band), so a segment here is the
segment the proposal's likelihood was read from. Nothing is written.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import contract_history
from di.services.modeler.valuers import renewal_odds

WORKSPACE = "workspace"


@dataclass(frozen=True)
class RenewalOutcome:
    contract_id: str
    market: str
    size_band: str
    age_band: str
    had_proposal: bool
    renewed: bool
    fee_before: float | None
    fee_after: float | None
    swaps_accepted: int
    org: str
    source: str  # "history" or "case"
    predicted_likelihood: float | None = None
    predicted_fee: float | None = None


def age_band(start: Any, end: Any) -> str:
    """The contract's age at the end of its term: under 2 years, 2 to 4, over 4 ("unknown" without both dates)."""
    try:
        years = (date.fromisoformat(str(end)[:10]) - date.fromisoformat(str(start)[:10])).days / 365.25
    except ValueError:
        return "unknown"
    return "under 2y" if years < 2 else "2 to 4y" if years < 4 else "over 4y"


def history_org(s: Session) -> str:
    """The org unit the fleet source is bound to (the first by id), else the workspace."""
    org = s.execute(
        text(
            "SELECT org_unit_id FROM source_system WHERE type = 'fleet' AND org_unit_id IS NOT NULL ORDER BY org_unit_id LIMIT 1"
        )
    ).scalar()
    return str(org or WORKSPACE)


def _opt(x: Any) -> float | None:
    return None if x is None else float(x)


def _history(s: Session, since: date, until: date) -> list[RenewalOutcome]:
    org = history_org(s)
    out = []
    for r in contract_history.rows(s):
        try:
            ended = datetime.fromisoformat(str(r.get("endedAt"))).date()
        except ValueError:
            continue
        if not since <= ended <= until or r.get("outcome") not in ("renewed", "lapsed"):
            continue
        out.append(
            RenewalOutcome(
                str(r["contractId"]), str(r.get("market")), renewal_odds.size_band(int(r.get("lines") or 0)), "unknown",
                bool(r.get("hadProposal")), r["outcome"] == "renewed", _opt(r.get("feeBefore")), _opt(r.get("feeAfter")), 0,
                org, "history",
            )
        )  # fmt: skip
    return out


def _cases(s: Session, org_unit_ids: list[str], since: date, until: date) -> list[RenewalOutcome]:
    rows = s.execute(
        text("SELECT owner, data FROM case_record WHERE owner = ANY(:o) AND data -> 'renewalOutcome' IS NOT NULL ORDER BY id"),
        {"o": org_unit_ids},
    )
    out = []
    for owner, d in rows:
        o, r = d["renewalOutcome"], d.get("refresh") or {}
        if not since <= date.fromisoformat(o["recorded_on"]) <= until:
            continue
        pred = o.get("predicted") or {}
        out.append(
            RenewalOutcome(
                str(r.get("contract_id") or d.get("contract_id")), str(r.get("market")),
                renewal_odds.size_band(len(r.get("lines") or [])), age_band(r.get("start_date"), r.get("term_end")),
                bool(o["had_proposal"]), bool(o["renewed"]), _opt(o.get("fee_before")), _opt(o.get("fee_after")),
                int(o.get("swaps_accepted") or 0), str(owner), "case", _opt(pred.get("likelihood")), _opt(pred.get("fee_month")),
            )
        )  # fmt: skip
    return out


def outcomes(s: Session, org_unit_ids: list[str] | tuple[str, ...], since: date, until: date) -> list[RenewalOutcome]:
    """The closed contracts of the period in these org units: the fleet's history (when its org unit is among them) and the
    refresh cases that recorded an outcome, in contract id order."""
    orgs = list(org_unit_ids)
    rows = _history(s, since, until) if history_org(s) in orgs else []
    return sorted(rows + _cases(s, orgs, since, until), key=lambda x: (x.contract_id, x.source))
