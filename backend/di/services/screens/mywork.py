"""My work (plan 9, P9-1.7; registry entry I-20): the one list of what waits for the signed-in person.

    GET /api/screens/mywork
        items   [{id, kind, case_id, title, cause, action, owner, due, overdue, priority, go}] from
                `di.services.cases.process.items_for`: open work items for the account's role or assigned to it, Home's
                approvals and tasks, the agents' proposals it may decide and the conflicts that hold a decision, sorted by
                priority, then due time. `id` starts with where the row comes from (`w:` work item, `a:` approval or task,
                `p:` proposal, `c:` conflict); `go` is a route without `#/`
        counts  {exception, approval, needs_info, proposal, conflict, task}: the rows of each kind
        kpis    [] (filled by P9-1.13)

Access: every role (`policy.EXTRA_PAGES["mywork"]`); a person sees only the items of their tenants (and warehouse). The
facade is frontend/src/api/mywork.ts: useMyWork() reads this; resolveItem, assignItem and askForInfo are the actions
work.resolve, work.assign and case.needInfo (di.services.actions.work); an approval row opens the approval card and a
proposal row uses proposal.accept and proposal.reject, as Home does.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.core.auth import Principal
from di.repositories.context import call_ctx
from di.services.cases import process


def page(p: Principal, session: Session) -> dict[str, Any]:
    """GET /api/screens/mywork."""
    items = [w.as_dict() for w in process.items_for(session, call_ctx(p, session))]
    return {"items": items, "counts": {k: sum(1 for i in items if i["kind"] == k) for k in process.KINDS}, "kpis": []}
