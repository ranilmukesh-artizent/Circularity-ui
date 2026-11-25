"""Pack versions as read from `pack_version` (plan 9, P9-1.6; migration 0032). Reads only; the actions
(di.services.actions.packs) write them.

The pack in force for an org (`active_pack`) is the newest published version of the key for the org or its nearest
ancestor (an org's own pack before the one of its parent), else the pack published for every org, else the pack file
(`load_pack`). A published version is always newer than the file's (the import refuses one that is not), so a published
shared pack and the file never compete.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.orgs import units
from di.repositories.overlays import OverlayRow
from di.services.modeler.pack import PACK_PARTS, Pack, PackError, load_pack, pack_keys, parse_pack

_OVERLAY_COLS = (
    "id, pack_key, org_unit_id, base_version, draft, draft_base_version, published, status, ver, maker, checker, "
    "conflicts, notes, updated_at"
)
_COLS = "id, key, version, org_unit_id, doc, status, maker, checker, note, impact, created_at, published_at"


@dataclass(frozen=True)
class PackRow:
    id: int
    key: str
    version: str
    org_unit_id: str | None
    doc: dict[str, Any]
    status: str  # draft, review, pub, retired
    maker: str | None
    checker: str | None
    note: str | None
    impact: dict[str, Any] | None
    created_at: datetime
    published_at: datetime | None


def semver(v: str) -> tuple[int, ...]:
    """A version as numbers, so 2.10.0 is newer than 2.9.0."""
    return tuple(int(p) for p in v.split("."))


def _row(r: Row[Any]) -> PackRow:
    return PackRow(*r)


def get(s: Session, pack_id: int, for_update: bool = False) -> PackRow | None:
    sql = f"SELECT {_COLS} FROM pack_version WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"i": pack_id}).first()
    return _row(r) if r else None


def rows(s: Session, key: str) -> list[PackRow]:
    """Every stored version of the key, newest first."""
    got = s.execute(text(f"SELECT {_COLS} FROM pack_version WHERE key = :k"), {"k": key}).all()  # noqa: S608 - fixed column list; values are bound
    return sorted((_row(r) for r in got), key=lambda r: (semver(r.version), r.id), reverse=True)


def parts_ok(doc: dict[str, Any]) -> dict[str, int]:
    """How many of the pack's 13 parts check out, in order: all of them for a document that parses."""
    try:
        parse_pack(doc)
    except PackError as e:
        return {"ok": max(e.part - 1, 0), "total": len(PACK_PARTS)}
    return {"ok": len(PACK_PARTS), "total": len(PACK_PARTS)}


def versions(s: Session, key: str) -> list[dict[str, Any]]:
    """The stored versions of the key, newest first, as the Modeler shows them (`parts`: the parts check)."""
    return [
        {"id": r.id, "key": r.key, "version": r.version, "org_unit_id": r.org_unit_id, "status": r.status,
         "maker": r.maker, "checker": r.checker, "note": r.note, "impact": r.impact,
         "parts": parts_ok(r.doc), "created_at": r.created_at.isoformat(),
         "published_at": r.published_at.isoformat() if r.published_at else None}
        for r in rows(s, key)
    ]  # fmt: skip


def stored_keys(s: Session) -> list[str]:
    """The pack keys that have a stored version, sorted."""
    return list(s.execute(text("SELECT DISTINCT key FROM pack_version ORDER BY key")).scalars())


def published_keys(s: Session) -> set[str]:
    """The keys with a published version: the imported packs a case may be opened with."""
    return set(s.execute(text("SELECT DISTINCT key FROM pack_version WHERE status = 'pub'")).scalars())


def newest_version(s: Session, key: str) -> str | None:
    """The newest version of the key, stored in any status or in the pack file."""
    found = [semver(r.version) for r in rows(s, key)]
    if key in pack_keys():
        found.append(semver(load_pack(key).version))
    return ".".join(str(n) for n in max(found)) if found else None


def published_pack(s: Session, key: str, org_unit_id: str | None) -> Pack | None:
    """The published version in force for the org (the nearest unit with one, then the shared one), else None."""
    pub = {r.org_unit_id: r for r in rows(s, key) if r.status == "pub"}
    if not pub:
        return None
    chain = orgs.ancestors(units(s), org_unit_id) if org_unit_id else []
    row = next((pub[u] for u in chain if u in pub), pub.get(None))
    return parse_pack(row.doc) if row else None


def active_pack(s: Session, key: str, org_unit_id: str | None) -> Pack:
    """The pack in force for the org (module docstring). KeyError for a key with neither a published version nor a file."""
    return published_pack(s, key, org_unit_id) or load_pack(key)


def pack_at(s: Session, key: str, version: str) -> Pack | None:
    """The pack of that version: the file's, else a stored one (the newest stored when two orgs hold it)."""
    if key in pack_keys() and load_pack(key).version == version:
        return load_pack(key)
    found = [r for r in rows(s, key) if r.version == version]
    return parse_pack(found[0].doc) if found else None


def overlays_of(s: Session, key: str) -> list[OverlayRow]:
    """Every customer overlay of the pack key, oldest first."""
    got = s.execute(text(f"SELECT {_OVERLAY_COLS} FROM customer_overlay WHERE pack_key = :k ORDER BY id"), {"k": key}).all()  # noqa: S608 - fixed column list; values are bound
    return [OverlayRow(*r) for r in got]
