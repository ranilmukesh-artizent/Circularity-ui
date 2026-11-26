"""The resource registry (plan 3 task 2): what `/api/v1/<name>` serves, declared once per resource.

Owns: the `Resource` dataclass and `register()`; `REGISTRY` maps a resource name to its declaration. The generic
router (`di.resources.router`) builds list/get/create/update/delete from it. Task 3 adds the real registrations,
one module per group, imported at the bottom of this file.

Never does: write a table. A resource names the action ids that implement create, update and delete; the router
calls `pipeline.invoke` with them, so permissions, tenant scope, guards, idempotency and the journal stay in the
pipeline (AGENTS.md rules 8-10). A verb without an action id answers 405 `not_supported` with `why_not[verb]`.

    register(Resource(name="notes", list=list_notes, get=get_note, create="note.add", update="note.edit", delete=None,
                      fields=("text",), why_not={"delete": "Notes are kept for the audit trail."}))

`list(ctx, query)` gets the filters named in `filters` (plus nothing else) and returns every row visible to the
caller, oldest first, as dicts; the router pages them (`limit`, `cursor`). It enforces access itself: it raises
`ApiError` (403, 404) or returns only the rows the account may see. `get(ctx, id)` returns the row or None (404).
`fields` lists the body keys create and update accept (empty: not checked, the action's own validation decides).

Three optional extras serve actions that name the row differently (task 3):
- `update_actions` maps a name to an action id: `PATCH /{id} {"action": "<name>", ...}` runs that action (a PATCH
  without `action` runs `update`). The body is checked against the chosen action's own inputs.
- `id_keys` maps an action id to the input key that carries the row id (default `id_field`; "" sends no id).
- `from_row` maps an input key to a key of the row `get` returned, for actions that also need another field of the
  row (a scenario's delete needs its case id).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from di.services.actions.pipeline import CallContext


@dataclass
class Resource:
    name: str
    list: Callable[[CallContext, dict[str, Any]], list[dict[str, Any]]]
    get: Callable[[CallContext, str], dict[str, Any] | None]
    create: str | None
    update: str | None
    delete: str | None
    id_field: str = "id"
    why_not: dict[str, str] = field(default_factory=dict)  # verb ("create", "update", "delete") -> why it is not supported
    fields: tuple[str, ...] = ()  # body keys create and update accept; empty: not checked here
    filters: tuple[str, ...] = ()  # query parameters list accepts besides limit and cursor
    update_actions: dict[str, str] = field(default_factory=dict)  # PATCH {"action": name} -> action id
    id_keys: dict[str, str] = field(default_factory=dict)  # action id -> input key of the row id ("": none)
    from_row: dict[str, str] = field(default_factory=dict)  # input key -> key of the row, added to update and delete


REGISTRY: dict[str, Resource] = {}


def register(r: Resource) -> None:
    REGISTRY[r.name] = r


# the real registrations (plan 3 task 3), one module per group; each calls register() at import
from di.resources import admin, cases, fabric, state_collections, workflows  # noqa: E402, F401
