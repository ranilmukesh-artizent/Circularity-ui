"""Saved analytics views (plan 9, P9-9.19, story UC-20 "save the view, share it with a role and set an alert on days_in_stock").

    save(s, account, org, pack, question_id, name, params)   a view of one worked question for an org unit, owned by the account
    candidates(s, account_id, role)                          the views the account owns or that are shared with its role
    share(s, row, roles)                                     replace the roles it is shared with
    set_alert(s, row, alert, by) / clear_alert(s, row, by)   one `{measure, op, threshold}` alert (or none)
    evaluate_alerts(s, by)                                   the job: compute each alert's measure, raise work items on a crossing

A view is the question and its parameters, not its answer: opening it asks the question again over what the viewer may see
(`device.question`). The alert's measure is a registered one of the question (`analytics.register_measure`; `days_in_stock` for
the used-car questions) computed over the view's org unit subtree. When the measure crosses the threshold one My work
exception `AL-VIEW-ALERT` is opened for the owner and one for each shared role (the owner's own role once); the view then stays
`alert_active` and nothing more is raised until the measure is back across the line (the items close) and crosses again. A
change of threshold, of recipients or of the alert itself closes the open items and starts again. Each evaluation locks the
view row, so the action and the worker's tick never raise twice.

Never does: change who may see a customer's rows (a viewer's answer is always computed within their own tenants, R21),
approve or decide anything, or use a model: the measure is a computed number. Sharing a view changes who sees it, so
`view.share` is in FORBIDDEN_ACTIONS (no agent) and `view.setAlert` is held for a person. In the caller's transaction.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.orgs import subtree
from di.repositories import orgs
from di.services import questions  # noqa: F401  (registers the worked questions and their measures)
from di.services.cases import process
from di.services.device import analytics

ALERT_TYPE = "AL-VIEW-ALERT"
OPS = {">": lambda v, t: v > t, ">=": lambda v, t: v >= t, "<": lambda v, t: v < t, "<=": lambda v, t: v <= t}
Row = dict[str, Any]


def view_dict(r: Row, viewer: str | None = None) -> Row:
    return {
        "id": r["id"], "org_unit_id": r["org_unit_id"], "owner": r["owner"], "pack": r["pack"], "question_id": r["question_id"],
        "name": r["name"], "params": r["params"], "shared_with_roles": r["shared_with_roles"], "alert": r["alert"],
        "alert_active": r["alert_active"], "mine": viewer is None or r["owner"] == viewer,
        "question": analytics.REGISTRY[r["question_id"]].question if r["question_id"] in analytics.REGISTRY else r["question_id"],
        "measures": analytics.measures_of(r["question_id"]),  # what an alert may watch
    }  # fmt: skip


def get(s: Session, view_id: int, *, lock: bool = False) -> Row | None:
    sql = text("SELECT * FROM analytics_view WHERE id = :i FOR UPDATE" if lock else "SELECT * FROM analytics_view WHERE id = :i")
    row = s.execute(sql, {"i": view_id}).mappings().first()
    return dict(row) if row else None


def save(s: Session, *, owner: str, owner_role: str, org: str, pack: str, question_id: str, name: str, params: Row) -> Row:
    row = s.execute(
        text(
            "INSERT INTO analytics_view (org_unit_id, owner, owner_role, pack, question_id, name, params) "
            "VALUES (:o, :w, :r, :p, :q, :n, CAST(:x AS jsonb)) RETURNING *"
        ),
        {"o": org, "w": owner, "r": owner_role, "p": pack, "q": question_id, "n": name, "x": json.dumps(params)},
    ).mappings().one()  # fmt: skip
    return dict(row)


def candidates(s: Session, account_id: str, role: str) -> list[Row]:
    """The views the account owns or that are shared with its role, oldest first (the caller drops other tenants' views)."""
    rows = s.execute(
        text("SELECT * FROM analytics_view WHERE owner = :a OR shared_with_roles ? :r ORDER BY id"), {"a": account_id, "r": role}
    ).mappings()
    return [dict(r) for r in rows]


def share(s: Session, row: Row, roles: list[str], by: str) -> Row:
    out = _update(s, row["id"], "shared_with_roles = CAST(:v AS jsonb)", {"v": json.dumps(sorted(set(roles)))})
    return _restart(s, out, by)


def set_alert(s: Session, row: Row, alert: Row, by: str) -> Row:
    out = _update(s, row["id"], "alert = CAST(:v AS jsonb)", {"v": json.dumps(alert)})
    return _restart(s, out, by)


def clear_alert(s: Session, row: Row, by: str) -> Row:
    _close(s, row, "Alert removed", by)
    return _update(s, row["id"], "alert = NULL, alert_active = false, alert_items = '[]'::jsonb", {})


def _update(s: Session, view_id: int, sets: str, args: Row) -> Row:
    sql = f"UPDATE analytics_view SET {sets}, updated_at = now() WHERE id = :i RETURNING *"  # noqa: S608 - `sets` is code, never input
    r = s.execute(text(sql), {"i": view_id, **args})
    return dict(r.mappings().one())


def _close(s: Session, row: Row, outcome: str, by: str) -> None:
    for item in row["alert_items"]:
        process.close_item(s, int(item), outcome, by)


def _restart(s: Session, row: Row, by: str) -> Row:
    """A changed alert or audience starts over: close what the old crossing raised, then evaluate at once."""
    if row["alert_active"]:
        _close(s, row, "Alert changed", by)
        row = _update(s, row["id"], "alert_active = false, alert_items = '[]'::jsonb", {})
    return _evaluate_one(s, row, by)


def _measure(s: Session, row: Row) -> float | None:
    fn = analytics.MEASURES.get((row["question_id"], row["alert"]["measure"]))
    if fn is None:
        return None
    allowed = subtree(orgs.units(s), row["org_unit_id"])
    return fn(s, analytics.Scope(frozenset(allowed)))


def _g(x: float) -> str:
    return f"{x:g}"


def _evaluate_one(s: Session, row: Row, by: str) -> Row:
    a = row["alert"]
    if not a:
        return row
    value = _measure(s, row)
    crossed = value is not None and OPS[a["op"]](value, float(a["threshold"]))
    if crossed and value is not None and not row["alert_active"]:
        cause = f"{a['measure']} is {_g(value)}, which crosses the alert {a['measure']} {a['op']} {_g(float(a['threshold']))}"
        recipients = [(row["owner_role"], row["owner"]), *((r, None) for r in row["shared_with_roles"] if r != row["owner_role"])]
        ids = [
            process.open_item(
                s, kind="exception", case_id=None, org_unit_id=row["org_unit_id"], type=ALERT_TYPE,
                title=f"Alert: {row['name']}", cause=cause, action=None, owner_role=role, owner_account=account,
                due_hours=None, by=by,
            )
            for role, account in recipients
        ]  # fmt: skip
        return _update(s, row["id"], "alert_active = true, alert_items = CAST(:v AS jsonb)", {"v": json.dumps(ids)})
    if not crossed and row["alert_active"]:
        _close(s, row, f"{a['measure']} is back across the line", by)
        return _update(s, row["id"], "alert_active = false, alert_items = '[]'::jsonb", {})
    return row


def evaluate_alerts(s: Session, by: str) -> int:
    """Evaluate every view with an alert (each under its row lock); the number of crossings newly raised."""
    raised = 0
    for (view_id,) in s.execute(text("SELECT id FROM analytics_view WHERE alert IS NOT NULL ORDER BY id")).all():
        row = get(s, view_id, lock=True)
        if row is None or not row["alert"]:
            continue
        was = row["alert_active"]
        after = _evaluate_one(s, row, by)
        raised += int(after["alert_active"] and not was)
    return raised
