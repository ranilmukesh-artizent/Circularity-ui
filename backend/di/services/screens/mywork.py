"""My work (plan 9, P9-1.7; registry entry I-20): the one list of what waits for the signed-in person.

    GET /api/screens/mywork
        items   [{id, kind, case_id, title, cause, action, owner, due, overdue, priority, go}] from
                `di.services.cases.process.items_for`: open work items for the account's role or assigned to it, Home's
                approvals and tasks, the agents' proposals it may decide and the conflicts that hold a decision, sorted by
                priority, then due time. `id` starts with where the row comes from (`w:` work item, `a:` approval or task,
                `p:` proposal, `c:` conflict); `go` is a route without `#/`
        counts  {exception, approval, needs_info, proposal, conflict, task}: the rows of each kind
        kpis    P9-1.13: one row per KPI of each pack the account's visible cases use ({pack, pack_name, id, label,
                definition, value, unit, trend, error}, see di.services.modeler.kpis); [] for the industrial demo, whose
                pack has none. An exception row's title, owner and action come from its pack's
                `runtime.exception_types`.

Access: every role (`policy.EXTRA_PAGES["mywork"]`); a person sees only the items of their tenants (and warehouse). The
facade is frontend/src/api/mywork.ts: useMyWork() reads this; resolveItem, assignItem and askForInfo are the actions
work.resolve, work.assign and case.needInfo (di.services.actions.work); an approval row opens the approval card and a
proposal row uses proposal.accept and proposal.reject, as Home does.
"""

from dataclasses import replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.auth import Principal
from di.repositories.context import call_ctx, visible_cases
from di.repositories.packs import active_pack
from di.services.cases import process
from di.services.modeler import kpis


def _from_pack(session: Session, views: list[process.WorkView]) -> list[process.WorkView]:
    """An exception row says what its pack says (`runtime.exception_types[type]`): label, owner role and action, read now,
    so a pack edit shows on open rows. An item handed to a person or escalated keeps its owner; a type the pack does not
    know keeps the row as written. The cause is the row's own."""
    ids = [int(v.id[2:]) for v in views if v.id.startswith("w:") and v.kind == "exception"]
    if not ids:
        return views
    rows = session.execute(
        text(
            "SELECT w.id, w.type, w.owner_account, w.escalated_at, c.data ->> 'template' AS template FROM work_item w "
            "LEFT JOIN case_record c ON c.id = w.case_id WHERE w.id = ANY(:i)"
        ),
        {"i": ids},
    ).mappings()
    meta = {f"w:{r['id']}": r for r in rows}
    out = []
    for v in views:
        m = meta.get(v.id)
        kind = None
        if m is not None:
            try:
                pack = active_pack(session, m["template"] or "industrial", None)
            except KeyError:  # the case's pack is no longer published: the row stays as written
                pack = None
            kind = next((t for t in pack.runtime.exception_types if t.id == m["type"]), None) if pack else None
        if kind is None or m is None:
            out.append(v)
            continue
        owner = v.owner if m["owner_account"] or m["escalated_at"] else process.role_of_owner(kind.owner_role)
        out.append(replace(v, title=kind.label, action=kind.action, owner=owner))
    return out


def _kpi_strip(p: Principal, session: Session) -> list[dict[str, Any]]:
    """The KPIs of the packs of the cases the account may see (the industrial demo's pack has none), one row per KPI with
    its pack."""
    ctx = call_ctx(p, session)
    cases = visible_cases(ctx)
    out: list[dict[str, Any]] = []
    for key in sorted({c.get("template") or "industrial" for c in cases}):
        try:
            pack = active_pack(session, key, None)
        except KeyError:  # a pack that is no longer published has no KPIs to show
            continue
        mine = [c for c in cases if (c.get("template") or "industrial") == key]
        out += [{"pack": key, "pack_name": pack.name, **k} for k in kpis.kpi_rows(pack, mine)]
    return out


def page(p: Principal, session: Session) -> dict[str, Any]:
    """GET /api/screens/mywork."""
    views = _from_pack(session, process.items_for(session, call_ctx(p, session)))
    items = [w.as_dict() for w in views]
    counts = {k: sum(1 for i in items if i["kind"] == k) for k in process.KINDS}
    return {"items": items, "counts": counts, "kpis": _kpi_strip(p, session)}
