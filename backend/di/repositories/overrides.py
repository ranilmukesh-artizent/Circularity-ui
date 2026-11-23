"""The journaled decisions (plan 8, MVP-12.3): every `decision.approve` and `decision.override` in the action journal
that was not undone, oldest first, with the route the person approved as they named it (the route's `plan`; None when
an approve took the recommendation). `di.services.modeler.suggest` learns rule suggestions from them."""

from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session


class JournaledDecision(TypedDict):
    seq: int
    action: str
    case_id: str
    route: str | None


def journaled_decisions(s: Session) -> list[JournaledDecision]:
    rows = s.execute(
        text(
            "SELECT seq, action, case_id, input->>'route' AS route FROM action_journal "
            "WHERE action IN ('decision.approve', 'decision.override') AND NOT undone AND case_id IS NOT NULL "
            "ORDER BY seq"
        )
    ).mappings()
    return [{"seq": r["seq"], "action": r["action"], "case_id": r["case_id"], "route": r["route"]} for r in rows]
