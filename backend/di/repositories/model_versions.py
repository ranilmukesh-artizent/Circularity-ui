"""The calibration models (table `model_version`, plan 8 MVP-12.2) as read by the model actions, intake and the
orchestration screen. `factors` is stored as `[{route, cls, factor}]`; `as_factors` gives the calibration's keys."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.engine.calibration import Key

_COLS = (
    "id, template, factors, status, created_by, approved_by, metrics, created_at, kind, "
    "pack, trained_at, data_window, quality, drift, drift_status, cadence, next_due"
)


@dataclass(frozen=True)
class ModelRow:
    id: str
    template: str
    factors: list[dict[str, Any]]
    status: str
    created_by: str
    approved_by: str | None
    metrics: dict[str, Any]
    created_at: datetime
    kind: str = "calibration"  # calibration, rated_life ... (migration 0042)
    pack: str | None = None  # migration 0059 (P9-13.8): the registry fields
    trained_at: datetime | None = None
    data_window: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    drift: dict[str, Any] | None = None
    drift_status: str | None = None
    cadence: str | None = None
    next_due: datetime | None = None

    def as_factors(self) -> dict[Key, float]:
        return {(self.template, f["route"], f["cls"]): float(f["factor"]) for f in self.factors}


def _one(s: Session, where: str, p: dict[str, Any]) -> ModelRow | None:
    row = s.execute(text(f"SELECT {_COLS} FROM model_version WHERE {where}"), p).first()  # noqa: S608 - fixed clauses of this module; values are bound
    return ModelRow(*row) if row else None


def get(s: Session, model_id: str, for_update: bool = False) -> ModelRow | None:
    return _one(s, "id = :i" + (" FOR UPDATE" if for_update else ""), {"i": model_id})


def active(s: Session, template: str, kind: str = "calibration") -> ModelRow | None:
    return _one(s, "template = :t AND kind = :k AND status = 'active'", {"t": template, "k": kind})


def candidate(s: Session, template: str, kind: str = "calibration") -> ModelRow | None:
    """The newest candidate of the template, if any."""
    return _one(
        s,
        "template = :t AND kind = :k AND status = 'candidate' ORDER BY created_at DESC, id DESC LIMIT 1",
        {"t": template, "k": kind},
    )


def proposed(s: Session, template: str, kind: str = "calibration") -> ModelRow | None:
    """The newest candidate of the template that a person has proposed for promotion, if any."""
    return _one(
        s,
        "template = :t AND kind = :k AND status = 'candidate' AND metrics ? 'proposal' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        {"t": template, "k": kind},
    )


def of_template(s: Session, template: str) -> list[ModelRow]:
    """The template's models, the newest first (the read action model.list, U2)."""
    sql = f"SELECT {_COLS} FROM model_version WHERE template = :t ORDER BY created_at DESC, id DESC"  # noqa: S608 - fixed columns
    return [ModelRow(*r) for r in s.execute(text(sql), {"t": template})]


def next_id(s: Session) -> str:
    n = s.execute(text("SELECT coalesce(max(substring(id from 4)::int), 0) FROM model_version")).scalar_one()
    return f"MV-{n + 1:03d}"


def all_models(s: Session) -> list[ModelRow]:
    """Every model, the newest first (the drift check reads the active ones)."""
    sql = f"SELECT {_COLS} FROM model_version ORDER BY created_at DESC, id DESC"  # noqa: S608 - fixed columns
    return [ModelRow(*r) for r in s.execute(text(sql))]
