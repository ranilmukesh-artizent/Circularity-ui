"""Access requests as the Access and MCP pages list them: each with whether the signed-in account may decide it."""

from sqlalchemy.orm import Session

from di.core.auth import Principal
from di.repositories.common import REQ_SCOPE, requests


def own(account_id: str, r: dict) -> bool:
    """Maker-checker: the account made this request or proposal, so another person must decide it."""
    return r.get("byId") == account_id


def can_decide(p: Principal, r: dict) -> bool:
    """The demo's canDecide: a pending request of a kind this account may decide (Admin, or a delegated Approver),
    and not one it made itself (maker-checker; the demo's seeded requests are never their decider's own)."""
    return r["status"] == "pending" and p.can("approve." + REQ_SCOPE[r["kind"]]) and not own(p.account.id, r)


def request_rows(s: Session, p: Principal, kind: str | None = None) -> list[dict]:
    """The requests, newest first (the demo's S.reqs), each with whether this account may decide it."""
    return [r | {"can_decide": can_decide(p, r)} for r in requests(s) if kind is None or r["kind"] == kind]
