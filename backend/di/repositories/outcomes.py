"""The outcome dataset (plan 8, MVP-12.1): one row per case whose outcome Finance confirmed (`outcome.confirm`,
di/services/actions/execution.py), with the route that was executed (the chosen route, else the recommendation), its
predicted net and the confirmed actual net. `di.services.engine.calibration.fit` learns from these rows."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.cases import store
from di.services.engine.calibration import OutcomeRow


def _route(d: dict[str, Any]) -> dict[str, Any] | None:
    if d.get("chosen"):
        return dict(d["chosen"])
    i = d.get("rec_index")
    return dict(d["routes"][i]) if i is not None else None


def outcome_rows(s: Session) -> list[OutcomeRow]:
    """Every confirmed outcome, oldest confirmation first."""
    store.ensure(s)
    docs = s.execute(
        text("SELECT data FROM case_record WHERE jsonb_typeof(data->'outcome') = 'object' ORDER BY data->'outcome'->>'at', id")
    ).scalars()
    rows: list[OutcomeRow] = []
    for d in docs:
        r = _route(d)
        if r is None:
            continue
        rows.append(
            {
                "case_id": d["id"],
                "template": d.get("template") or "industrial",
                "cls": d["cls"],
                "route": r["id"],
                "predicted_net": r["net"],
                "actual_net": d["outcome"]["net"],
                "confirmed_at": d["outcome"]["at"],
            }
        )
    return rows
