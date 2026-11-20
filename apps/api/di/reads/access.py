"""Access requests as the Access and MCP pages list them: each with whether the signed-in account may decide it."""

from sqlalchemy.orm import Session

from di.auth import Principal
from di.reads.common import REQ_SCOPE, requests


def can_decide(p: Principal, r: dict) -> bool:
    """The demo's canDecide: a pending request of a kind this account may decide (Admin, or a delegated Approver)."""
    return r["status"] == "pending" and p.can("approve." + REQ_SCOPE[r["kind"]])


def request_rows(s: Session, p: Principal, kind: str | None = None) -> list[dict]:
    """The requests, newest first (the demo's S.reqs), each with whether this account may decide it."""
    return [r | {"can_decide": can_decide(p, r)} for r in requests(s) if kind is None or r["kind"] == kind]
