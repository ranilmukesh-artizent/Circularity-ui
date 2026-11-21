"""The action registry (docs/backend-steps.md, B8): the demo's 76 named actions, declared once.

The declarations (id, title, risk, permission, scope, input schema, verb) come from the golden action catalog, so
the server and the demo agree. Behaviour is attached in code, one module per area (B10-B13):

    @implement("decision.submit", idem=lambda i, ctx: f"{i['case_id']}:submit")
    def submit(i, ctx): ...                       # returns the output dict, or raises ActionError

    @guard("decision.submit")
    def submit_guard(i, ctx): ...                 # returns ("conflict", "message") to refuse, or None
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from di import golden

if TYPE_CHECKING:
    from di.actions.pipeline import CallContext

Risk = Literal["read", "draft", "act", "commit", "system"]
Handler = Callable[[dict[str, Any], "CallContext"], dict[str, Any] | None]
Guard = Callable[
    [dict[str, Any], "CallContext"], tuple[str, str] | tuple[str, str, dict[str, Any]] | None
]  # (code, message[, extra])
IdemKey = Callable[[dict[str, Any], "CallContext"], str]
H = TypeVar("H", bound=Handler)
G = TypeVar("G", bound=Guard)
PERM_ALIAS = {"approve": "approve.decisions"}  # the demo's PERM_ALIAS


class ActionError(Exception):
    """A refusal with one of the demo's error codes (see pipeline.ERROR_STATUS)."""

    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


@dataclass
class ActionDef:
    id: str
    title: str
    desc: str
    risk: Risk
    perm: str | None
    scope: Literal["case", "none"]
    input: dict[str, dict[str, Any]]
    verb: str | None = None
    dup_text: str | None = None
    handler: Handler | None = None
    guard: Guard | None = None
    idem: IdemKey | None = None
    emits: list[str] = field(default_factory=list)
    # a write that is not journaled and emits no event: a person's own scratch state (an autosaved workflow draft),
    # which would otherwise fill the journal and the audit views every few seconds. Still a write for every gate.
    journaled: bool = True

    @property
    def permission(self) -> str | None:
        return PERM_ALIAS.get(self.perm, self.perm) if self.perm else None

    @property
    def changes_state(self) -> bool:
        return self.risk != "read"


def _load() -> dict[str, ActionDef]:
    out: dict[str, ActionDef] = {}
    for a in golden.load("actions_catalog"):
        spec = {k: (v if isinstance(v, dict) else {}) for k, v in (a.get("input") or {}).items()}
        out[a["id"]] = ActionDef(
            id=a["id"],
            title=a["title"],
            desc=a.get("desc", ""),
            risk=a["risk"],
            perm=a.get("perm"),
            scope=a.get("scope") or "none",
            input=spec,
            verb=a.get("verb"),
            dup_text=a.get("dup_text"),
        )
    return out


ACTIONS: dict[str, ActionDef] = _load()


def implement(action_id: str, idem: IdemKey | None = None, emits: list[str] | None = None) -> Callable[[H], H]:
    """Attach a handler; the decorated function keeps its own signature (read handlers are also called directly)."""

    def register(fn: H) -> H:
        a = ACTIONS[action_id]
        a.handler, a.idem, a.emits = fn, idem or a.idem, emits or a.emits
        return fn

    return register


def guard(action_id: str) -> Callable[[G], G]:
    def register(fn: G) -> G:
        ACTIONS[action_id].guard = fn
        return fn

    return register
