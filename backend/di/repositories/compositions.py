"""Compositions as read from `composition` (plan 9, P9-8.17; migration 0058). Reads, and the append of a version snapshot.

The actions (`di.services.actions.compose`) change the rows; this module reads them and appends `composition_version`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_COLS = (
    "id, org_unit_id, pack_key, base_version, text, reading, change_set, steps, status, version, created_by, editors, "
    "submitted_by, approved_by, published_by, created_at, updated_at"
)


def _plain(m: Any) -> dict[str, Any]:
    d = dict(m)
    for k in ("created_at", "updated_at"):
        d[k] = d[k].isoformat() if isinstance(d.get(k), datetime) else None
    d["editors"] = list(d["editors"])
    return d


def get(s: Session, cid: int, for_update: bool = False) -> dict[str, Any] | None:
    sql = f"SELECT {_COLS} FROM composition WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed columns
    r = s.execute(text(sql), {"i": cid}).mappings().first()
    return _plain(r) if r else None


def listing(s: Session, org_unit_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Newest first; `org_unit_ids` None is every org."""
    where = "WHERE org_unit_id = ANY(:o)" if org_unit_ids is not None else ""
    sql = f"SELECT {_COLS} FROM composition {where} ORDER BY id DESC"  # noqa: S608 - fixed columns and clause
    rows = s.execute(text(sql), {"o": org_unit_ids} if org_unit_ids is not None else {}).mappings()
    return [_plain(r) for r in rows]


_IN_FORCE = ("approved", "published")


def _settings(steps: Any) -> list[dict[str, Any]]:
    return list(((steps or {}).get("agents") or {}).get("settings") or [])


def approved_stage_settings(s: Session, pack_key: str, org_unit_id: str) -> list[dict[str, Any]]:
    """The stage-agent settings (`steps.agents.settings`) of the newest composition (highest id) that is approved or
    published for exactly this pack and org unit; empty when there is none, or when that one holds no settings. The stage
    chain runs with them (`di.services.agents.runtime`)."""
    steps = s.execute(
        text(
            "SELECT steps FROM composition WHERE pack_key = :p AND org_unit_id = :o AND status = ANY(:st) "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"p": pack_key, "o": org_unit_id, "st": list(_IN_FORCE)},
    ).scalar_one_or_none()
    return _settings(steps)


def setups(s: Session) -> list[dict[str, Any]]:
    """Every approved or published composition that holds stage settings, newest first:
    `{composition_id, org_unit_id, pack_key, status, settings}` (the Agents page shows them under their pack)."""
    rows = s.execute(
        text("SELECT id, org_unit_id, pack_key, status, steps FROM composition WHERE status = ANY(:st) ORDER BY id DESC"),
        {"st": list(_IN_FORCE)},
    ).mappings()
    return [
        {"composition_id": r["id"], "org_unit_id": r["org_unit_id"], "pack_key": r["pack_key"], "status": r["status"],
         "settings": _settings(r["steps"])}
        for r in rows
        if _settings(r["steps"])
    ]  # fmt: skip


def add_version(s: Session, cid: int, version: int, snapshot_json: str, status: str, by: str, at: datetime) -> None:
    s.execute(
        text(
            'INSERT INTO composition_version (composition_id, version, snapshot, status, "by", "at") '
            "VALUES (:c, :v, CAST(:s AS jsonb), :st, :by, :at)"
        ),
        {"c": cid, "v": version, "s": snapshot_json, "st": status, "by": by, "at": at},
    )
