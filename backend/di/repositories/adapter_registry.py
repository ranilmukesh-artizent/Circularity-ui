"""Reads of the adapter registry and of the system owner's approvals (plan 9 P9-8.1; registry entry I-18).

    entries(s, org_unit_id)              the entries a person at that org unit can start a connection from
    entry(s, org_unit_id, id, version)   one of them, or None
    approvals_of(s, source_id)           a source's approval requests, newest first
    approved(s, source_id, environment, access)   the source has an approved request for exactly that

Owns: the queries over `adapter_registry` and `connection_approval`, and the mapping of a row to `RegistryEntry`.
Never does: write, decide who may see what (the actions check the org unit) or return a secret.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors.registry import RegistryEntry, catalogue_entries

_KIND_ORDER = {"catalogue": 0, "generic_rest": 1, "from_spec": 2}


def _row(r: Any) -> RegistryEntry:
    return RegistryEntry(
        id=r.id, version=r.version, kind=r.kind, system_type=r.system_type, vendor_family=r.vendor_family,
        auth_methods=tuple(r.auth_methods or ()), resources=tuple(r.resources or ()),
        canonical_entities=tuple(r.canonical_entities or ()), write_actions=tuple(r.write_actions or ()), status=r.status,
        maintainer=r.maintainer or "", source_licence=r.source_licence, spec=dict(r.spec or {}), org_unit_id=r.org_unit_id,
    )  # fmt: skip


def entries(s: Session, org_unit_id: str | None) -> list[RegistryEntry]:
    """The catalogue's entries, the released rows, and the org's own draft and tested rows (its `org_unit_id`; a row with
    none belongs to the person who saved it, whatever org they work in), ordered by kind, system type and id."""
    rows = s.execute(
        text(
            "SELECT * FROM adapter_registry WHERE status = 'released' "
            "OR (status IN ('draft','tested') AND org_unit_id IS NOT DISTINCT FROM CAST(:o AS text))"
        ),
        {"o": org_unit_id},
    ).all()
    out = [*catalogue_entries(), *(_row(r) for r in rows)]
    return sorted(out, key=lambda e: (_KIND_ORDER[e.kind], e.system_type, e.id, e.version))


def entry(s: Session, org_unit_id: str | None, entry_id: str, version: int) -> RegistryEntry | None:
    return next((e for e in entries(s, org_unit_id) if e.id == entry_id and e.version == version), None)


def row(s: Session, entry_id: str, version: int, for_update: bool = False) -> Any:
    """The raw saved row (status, who made and released it), or None."""
    sql = (
        "SELECT * FROM adapter_registry WHERE id = :i AND version = :v FOR UPDATE"
        if for_update
        else "SELECT * FROM adapter_registry WHERE id = :i AND version = :v"
    )
    return s.execute(text(sql), {"i": entry_id, "v": version}).first()


def next_version(s: Session, entry_id: str) -> int:
    return int(
        s.execute(text("SELECT coalesce(max(version), 0) + 1 FROM adapter_registry WHERE id = :i"), {"i": entry_id}).scalar_one()
    )


def approvals_of(s: Session, source_id: str) -> list[dict[str, Any]]:
    rows = s.execute(text("SELECT * FROM connection_approval WHERE source_id = :i ORDER BY id DESC"), {"i": source_id}).mappings()
    return [
        {
            "id": r["id"], "source_id": r["source_id"], "environment": r["environment"], "access": r["access"],
            "requested_by": r["requested_by"], "owner": r["owner"], "status": r["status"], "reason": r["reason"],
            "decided_by": r["decided_by"], "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
        }
        for r in rows
    ]  # fmt: skip


def approval(s: Session, approval_id: int, for_update: bool = False) -> dict[str, Any] | None:
    sql = (
        "SELECT * FROM connection_approval WHERE id = :i FOR UPDATE"
        if for_update
        else "SELECT * FROM connection_approval WHERE id = :i"
    )
    r = s.execute(text(sql), {"i": int(approval_id)}).mappings().first()
    return dict(r) if r else None


def _has(s: Session, source_id: str, environment: str, access: str, status: str) -> bool:
    found = s.execute(
        text("SELECT 1 FROM connection_approval " "WHERE source_id = :i AND environment = :e AND access = :a AND status = :st"),
        {"i": source_id, "e": environment, "a": access, "st": status},
    ).first()
    return found is not None


def pending_like(s: Session, source_id: str, environment: str, access: str) -> bool:
    return _has(s, source_id, environment, access, "pending")


def approved(s: Session, source_id: str, environment: str, access: str) -> bool:
    return _has(s, source_id, environment, access, "approved")


def live_system(s: Session, system_type: str, org_unit_id: str | None) -> bool:
    """A connection of this system type runs in production for the org unit (or is shared) and is not deleted: a connection
    in the test environment is not live (P9-9.13, UC-04). A source whose own id is the system type counts as well."""
    from di.connectors import lifecycle

    gone = lifecycle.deleted(s)
    rows = s.execute(
        text(
            "SELECT ss.id FROM source_connection sc JOIN source_system ss ON ss.id = sc.source_id "
            "LEFT JOIN adapter_registry ar ON ar.id = sc.registry_id AND ar.version = sc.registry_version "
            "WHERE sc.environment = 'production' AND (ss.org_unit_id IS NULL OR ss.org_unit_id = :o) "
            "AND (ar.system_type = :t OR ss.id = :t)"
        ),
        {"o": org_unit_id, "t": system_type},
    ).scalars()
    return any(sid not in gone for sid in rows)
