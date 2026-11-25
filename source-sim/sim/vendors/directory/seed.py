"""Seed of the directory mock: one synthetic user per demo account, the two deputies and one joiner-to-be.

Owns: the user list and `ensure` / `reset` (the Mock contract). Never does: call di or import its code, so the table
below copies `backend/di/core/policy.py` (`starting_accounts` labels, `IDP_GROUPS`, `_idp_email`). The admin has no
group: Admin is never given through a group (story X-10).
"""

import re

from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.directory.models import STATE, User

# (account id, label as the demo's starting_accounts has it, directory group or None)
_ACCOUNTS: list[tuple[str, str, str | None]] = [
    ("planner-a", "Planner · Customer A", "circ-planners-customer-a"),
    ("planner-b", "Planner · Customer B", "circ-planners-customer-b"),
    ("planner-c", "Planner · Customer C", "circ-planners-customer-c"),
    ("approver", "Approver", "circ-approvers"),
    ("engineer", "Engineer", "circ-engineering"),
    ("finance", "Finance", "circ-finance"),
    ("developer", "Developer", "circ-integration-devs"),
    ("admin", "Admin", None),
    ("executive", "Executive", "circ-executives"),
    ("wm-1", "Warehouse Manager · Warehouse 1", "circ-warehouse-1"),
    ("wm-2", "Warehouse Manager · Warehouse 2", "circ-warehouse-2"),
]
JOINER_EMAIL = "joiner.one@example.com"


def idp_email(label: str) -> str:
    return re.sub(r"\s+", "-", label.lower().replace(" · ", ".")) + "@example.com"


def load() -> int:
    """Back to the seed; answers the number of active users."""
    STATE.users.clear()
    STATE.pending.clear()
    STATE.codes.clear()
    STATE.tokens.clear()
    for uid, label, group in _ACCOUNTS:
        STATE.users[uid] = User(uid, idp_email(label), label, [group] if group else [])
    STATE.users["dep-ap"] = User("dep-ap", "approver.deputy@example.com", "Approver deputy")
    STATE.users["dep-pl"] = User("dep-pl", "planner.deputy@example.com", "Planner deputy")
    STATE.pending[JOINER_EMAIL] = User("joiner-one", JOINER_EMAIL, "Joiner One")
    return len(STATE.users)


def ensure(_conn: Connection, _s: Seed) -> None:
    if not STATE.users:
        load()


def reset(_conn: Connection, _s: Seed) -> dict[str, int]:
    return {"users": load()}
