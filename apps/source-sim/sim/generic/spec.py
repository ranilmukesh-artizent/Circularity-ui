"""The spec a generic mock is built from (docs/backend-steps.md, B5).

    SPEC = Spec(
        source_id="wms", title="Manhattan Active Warehouse Management", schema="manhattan", base_path="/manhattan/wms/api",
        auth=Auth("oauth_cc"), paging=Paging("offset", items_key="data", next_key=None, total_key="totalCount"),
        resources=(Resource("inventory", "/inventory", id_field="inventoryId", filters=("itemId", "locationId")), ...),
        seed=lambda s: {"inventory": [...], ...},
    )

Paths are relative to `base_path`, and should be the demo's SOURCES[<id>].read / .write paths. Field names in the
seeded documents should read like the vendor's own API (camelCase, snake_case, vendor prefixes …).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sim.seed import Seed

AuthKind = Literal["api_key", "bearer", "basic", "oauth_cc"]


@dataclass(frozen=True)
class Auth:
    """How a client authenticates. Demo credentials are derived from the source id (see `credentials`)."""

    kind: AuthKind
    header: str = "Authorization"  # for api_key: the header that carries the key, e.g. "x-api-key"
    token_path: str = "/oauth/token"  # noqa: S105 - a URL path, not a secret (for oauth_cc: relative to base_path)


@dataclass(frozen=True)
class Paging:
    """How lists are paged and wrapped.

    offset:  ?{limit_param}=&{offset_param}=                 next = the next offset (or None)
    page:    ?{page_param}=&{size_param}=   (1-based)        next = the next page number (or None)
    cursor:  ?{limit_param}=&{cursor_param}=  (opaque)       next = the next cursor (or None)
    The body is {items_key: [...], next_key: next, total_key: total}; set a key to None to leave it out.
    """

    style: Literal["offset", "page", "cursor"] = "offset"
    limit_param: str = "limit"
    offset_param: str = "offset"
    page_param: str = "page"
    size_param: str = "page_size"
    cursor_param: str = "cursor"
    items_key: str = "items"
    next_key: str | None = "next"
    total_key: str | None = "total"
    default_size: int = 50
    max_size: int = 200


@dataclass(frozen=True)
class Resource:
    name: str  # "inventory"
    path: str  # "/inventory" (relative to base_path)
    id_field: str  # the document field that holds the id, e.g. "inventoryId"
    filters: tuple[str, ...] = ()  # document fields usable as ?field=value
    create: bool = False  # POST {path}
    update: bool = False  # PATCH {path}/{id}
    id_format: str = "{n:06d}"  # id for created documents, from a per-resource counter
    event: str | None = None  # outbox event type prefix, e.g. "manhattan.reservation" -> ".created", ".updated"


def _default_error(status: int, code: str, message: str) -> dict:  # noqa: ARG001 - same signature as the specs' error builders
    return {"error": {"code": code, "message": message}}


@dataclass(frozen=True)
class Spec:
    source_id: str  # the demo's SOURCES[].id (sim/registry.py)
    title: str
    schema: str  # Postgres schema, as in sim/registry.py
    base_path: str  # as in sim/registry.py
    auth: Auth
    paging: Paging
    resources: tuple[Resource, ...]
    seed: Callable[[Seed], dict[str, list[dict[str, Any]]]]
    updated_since_param: str = "updated_since"  # delta reads: ?updated_since=2026-10-07T09:00:00Z
    error: Callable[[int, str, str], dict] = field(default=_default_error)  # the vendor's error body


def credentials(spec: Spec) -> dict[str, str]:
    """Demo credentials for a generic mock (documented in apps/README.md)."""
    sid = spec.source_id
    return {
        "api_key": f"{sid}-demo-key",
        "user": "di-connector",
        "password": f"{sid}-demo",
        "client_id": "di-connector",
        "client_secret": f"{sid}-demo-secret",
    }
