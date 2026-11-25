"""SCIM 2.0 provisioning of directory users (plan 9 P9-8.11, story X-10), behind the routes in di.routes.scim.

Standards: RFC 7643 (core schemas: User 4.1, Group 4.2, ServiceProviderConfig 5, ResourceType 6, Schema 7) and RFC 7644
(protocol: filtering 3.4.2.2, pagination 3.4.2.4, PATCH 3.5.2, errors 3.12, bearer auth 2). The models are pydantic
classes written here, not the `scim2-models` package: it is not in the lock, and the spec's needs (User, Group, PatchOp,
ListResponse, Error, one `eq` filter) are a few small shapes.

Owns: the SCIM shapes, the bearer check, the filter, the mapping between SCIM resources and the directory users
(collection "idp_users") and groups (the group map), and the calls that write: every write is an action run through
`pipeline.invoke` as the system actor (access.scimUpsertUser, access.scimDeactivateUser, access.scimPatchGroup).
Never does: write state itself; give a role (the approved group map does, in the action); delete anything (DELETE and
`active=false` both deactivate); create or change a group (groups are the group map's rows, changed by people with
maker-checker); log or return the bearer token; accept a request without the token held for source `idp`.
"""

import hmac
import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from di.connectors import secrets
from di.core import policy, state
from di.core.auth import load_context
from di.services.actions.pipeline import SYSTEM, CallContext, invoke

SOURCE = "idp"
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
MAX_RESULTS = 200  # advertised in ServiceProviderConfig.filter.maxResults and applied to `count`
_CODES = {"not_found": (404, None), "conflict": (409, "mutability"), "validation_error": (400, "invalidValue")}


class ScimHttpError(Exception):
    """A refusal in the shape of RFC 7644 3.12: HTTP status, an optional `scimType` and a detail."""

    def __init__(self, status: int, detail: str, scim_type: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.scim_type = status, detail, scim_type

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schemas": [ERROR_SCHEMA], "status": str(self.status), "detail": self.detail}
        return out | ({"scimType": self.scim_type} if self.scim_type else {})


# ---------------------------------------------------------------- shapes (RFC 7643 4.1 and 4.2)
class _Shape(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Name(_Shape):
    formatted: str | None = None
    givenName: str | None = None
    familyName: str | None = None


class Email(_Shape):
    value: str
    type: str | None = None
    primary: bool | None = None


class Ref(_Shape):
    """A group of a user, or a member of a group: `value` is the id; `display` the readable name."""

    value: str | None = None
    display: str | None = None


class UserIn(_Shape):
    schemas: list[str] = Field(default_factory=list)
    externalId: str | None = None
    userName: str = Field(min_length=3)
    name: Name | None = None
    displayName: str | None = None
    emails: list[Email] = Field(default_factory=list)
    active: bool = True
    groups: list[Ref] = Field(default_factory=list)


class PatchOperation(_Shape):
    op: str
    path: str | None = None
    value: Any = None


class PatchOp(_Shape):
    schemas: list[str] = Field(default_factory=list)
    Operations: list[PatchOperation] = Field(min_length=1)


def parse[T: BaseModel](model: type[T], body: Any) -> T:
    """The body as `model`; anything else is 400 invalidSyntax (not an object) or invalidValue (a field is wrong)."""
    if not isinstance(body, dict):
        raise ScimHttpError(400, "The body must be a JSON object.", "invalidSyntax")
    try:
        return model.model_validate(body)
    except ValidationError as e:
        first = e.errors()[0]
        raise ScimHttpError(400, f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}", "invalidValue") from e


def listing(resources: list[dict[str, Any]], total: int, start: int, count: int) -> dict[str, Any]:
    """ListResponse (RFC 7644 3.4.2): the page, how many matched, where it starts (1-based) and how many it holds."""
    return {"schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": start, "itemsPerPage": count, "Resources": resources}


# ---------------------------------------------------------------- the bearer token (RFC 7644 2, RFC 6750)
def token_ok(s: Session, authorization: str | None) -> bool:
    """True when the header is `Bearer <the webhook secret of source idp>`, compared in constant time."""
    kind, _, given = (authorization or "").partition(" ")
    held = secrets.active_secret(s, SOURCE, "webhook")
    if kind.lower() != "bearer" or not given.strip() or not held:
        return False
    return hmac.compare_digest(given.strip().encode(), held.encode())


# ---------------------------------------------------------------- reading directory users
def groups_of(item: dict[str, Any]) -> list[str]:
    """The directory groups of a user: those stored by a sync or SCIM, else the demo's own group of an account."""
    stored = item.get("groups")
    if isinstance(stored, list):
        return [str(g) for g in stored]
    own = policy.IDP_GROUPS.get(str(item.get("acct") or ""))
    return [own] if own else []


def _active_json(item: dict[str, Any], base: str) -> dict[str, Any]:
    email = str(item["email"]).lower()
    name = item.get("name") or email.split("@")[0]
    return _user_json(item["id"], item.get("external_id"), email, name, True, groups_of(item), base)


def _user_json(uid: str, ext: str | None, email: str, name: str, active: bool, groups: list[str], base: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schemas": [USER_SCHEMA], "id": uid, "userName": email, "displayName": name, "name": {"formatted": name},
        "emails": [{"value": email, "primary": True}], "active": active,
        "groups": [{"value": g, "display": g, "$ref": f"{base}/Groups/{g}"} for g in groups],
        "meta": {"resourceType": "User", "location": f"{base}/Users/{uid}"},
    }  # fmt: skip
    return out | ({"externalId": ext} if ext else {})


def _inactive(s: Session) -> list[dict[str, Any]]:
    return [r for r in state.items(s, "account_revoked") if r.get("active") is False and r.get("email")]


def all_users(s: Session, base: str) -> list[dict[str, Any]]:
    """Every user as a SCIM User: the active ones (the directory users), then the deactivated ones."""
    active = [_active_json(u, base) for u in state.items(s, "idp_users")]
    gone = [
        _user_json(r["id"], r.get("external_id"), r["email"], r.get("name") or r["email"], False, [], base) for r in _inactive(s)
    ]  # fmt: skip
    return [*active, *gone]


def find_item(s: Session, key: str) -> dict[str, Any] | None:
    """The active directory user whose SCIM id (or external id) is `key`."""
    return next((u for u in state.items(s, "idp_users") if key in (u["id"], u.get("external_id"))), None)


def get_user(s: Session, uid: str, base: str) -> dict[str, Any]:
    found = next((u for u in all_users(s, base) if u["id"] == uid), None)
    if found is None:
        raise ScimHttpError(404, f"No user {uid}.")
    return found


# ---------------------------------------------------------------- the filter (RFC 7644 3.4.2.2): one `eq` comparison
_FILTER = re.compile(
    r'^\s*(?P<attr>userName|externalId|id|displayName|active|emails\.value|emails\[value eq "(?P<inner>[^"]*)"\])'
    r'(?:\s+eq\s+(?:"(?P<str>[^"]*)"|(?P<bool>true|false)))?\s*$',
    re.IGNORECASE,
)


def _match(user: dict[str, Any], flt: str) -> bool:
    m = _FILTER.match(flt)
    if m is None or (m["inner"] is None and m["str"] is None and m["bool"] is None):
        raise ScimHttpError(400, f"Unsupported filter: {flt!r}. Use one `attr eq value` comparison.", "invalidFilter")
    attr = m["attr"].lower()
    if m["inner"] is not None:  # emails[value eq "x"] is a complete filter on its own
        return any(e["value"].lower() == m["inner"].lower() for e in user["emails"])
    if attr == "active":
        return m["bool"] is not None and user["active"] is (m["bool"].lower() == "true")
    if m["str"] is None:
        raise ScimHttpError(400, f"Unsupported filter: {flt!r}.", "invalidFilter")
    want = m["str"].lower()
    if attr == "emails.value":
        return any(e["value"].lower() == want for e in user["emails"])
    if attr in ("username", "displayname"):  # userName is case-insensitive (RFC 7643 4.1.1)
        return str(user.get("userName" if attr == "username" else "displayName", "")).lower() == want
    return str(user.get("externalId" if attr == "externalid" else "id", "")) == m["str"]


def page(items: Iterable[dict[str, Any]], flt: str | None, start: int, count: int | None) -> dict[str, Any]:
    """Filter, then page (startIndex is 1-based; `count` is cut to MAX_RESULTS; count 0 returns no resources)."""
    rows = [x for x in items if _match(x, flt)] if flt else list(items)
    start = max(start, 1)
    n = MAX_RESULTS if count is None else max(0, min(count, MAX_RESULTS))
    out = rows[start - 1 : start - 1 + n]
    return listing(out, len(rows), start, len(out))


# ---------------------------------------------------------------- writing: every write is an action as the system actor
def _run(s: Session, action: str, i: dict[str, Any]) -> dict[str, Any]:
    out = invoke(action, i, CallContext(actor=SYSTEM, session=s))
    if not out["ok"]:
        status, kind = _CODES.get(out["error"]["code"], (500, None))
        raise ScimHttpError(status, out["error"]["message"], kind)
    s.commit()
    return dict(out["output"])


def _email_of(u: UserIn) -> str:
    primary = next((e.value for e in u.emails if e.primary), None) or (u.emails[0].value if u.emails else None)
    email = (primary or (u.userName if "@" in u.userName else "")).strip().lower()
    if "@" not in email:
        raise ScimHttpError(400, "A user needs an email: userName or emails.", "invalidValue")
    return email


def _group_ids(refs: list[Ref]) -> list[str]:
    return [g for r in refs if (g := r.display or r.value)]


def _upsert(s: Session, u: UserIn, email: str, existing_id: str | None) -> dict[str, Any]:
    name = u.displayName or (u.name.formatted if u.name and u.name.formatted else None) or email.split("@")[0]
    ext = u.externalId or existing_id or email
    groups = _group_ids(u.groups)
    return _run(
        s, "access.scimUpsertUser", {"external_id": ext, "email": email, "name": name, "active": u.active, "groups": groups}
    )


def create_user(s: Session, body: Any, base: str) -> dict[str, Any]:
    u = parse(UserIn, body)
    email = _email_of(u)
    if any(x["userName"] == email for x in all_users(s, base)) or (u.externalId and find_item(s, u.externalId)):
        raise ScimHttpError(409, f"{email} already exists.", "uniqueness")
    out = _upsert(s, u, email, None)
    return get_user(s, out["id"], base) if out.get("id") else _user_json(email, u.externalId, email, email, False, [], base)


def _apply(user: dict[str, Any], op: PatchOperation) -> None:
    """One PATCH operation (RFC 7644 3.5.2) on the user as a flat dict; `groups` is read-only and ignored."""
    verb = op.op.lower()
    if verb not in ("add", "replace", "remove"):
        raise ScimHttpError(400, f"Unknown op {op.op!r}.", "invalidSyntax")
    pairs = op.value.items() if op.path is None and isinstance(op.value, dict) else [(op.path, op.value)]
    for path, value in pairs:
        key = (path or "").split("[")[0].lower()
        if key == "active":
            user["active"] = _to_bool(value)
        elif key in ("username", "emails", "emails.value"):
            if verb != "remove":
                user["email"] = _first_email(value)
        elif key in ("displayname", "name.formatted", "name"):
            user["name"] = value.get("formatted") if isinstance(value, dict) else (value or user["name"])
        elif key == "externalid":
            user["external_id"] = value
        elif key not in ("groups", ""):
            raise ScimHttpError(400, f"Cannot change {path!r}.", "mutability")


def _to_bool(v: Any) -> bool:
    """Booleans arrive as JSON booleans, or as "True" / "False" text from some providers."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    raise ScimHttpError(400, "`active` must be true or false.", "invalidValue")


def _first_email(v: Any) -> str:
    if isinstance(v, list) and v and isinstance(v[0], dict):
        v = v[0].get("value")
    if isinstance(v, dict):
        v = v.get("value")
    if not isinstance(v, str) or "@" not in v:
        raise ScimHttpError(400, "A value must be an email address.", "invalidValue")
    return v.strip().lower()


def update_user(s: Session, uid: str, ops: list[PatchOperation] | None, put: UserIn | None, base: str) -> dict[str, Any]:
    """PATCH (`ops`) or PUT (`put`) a user: the attributes it names change; `active=false` deactivates."""
    current = get_user(s, uid, base)
    item = find_item(s, uid)
    user = {"active": current["active"], "email": current["userName"], "name": current["displayName"],
            "external_id": current.get("externalId") or uid, "groups": [g["display"] for g in current["groups"]]}  # fmt: skip
    if put is not None:
        user |= {"active": put.active, "email": _email_of(put), "external_id": put.externalId or user["external_id"],
                 "name": put.displayName or user["name"]}  # fmt: skip
    for op in ops or []:
        _apply(user, op)
    if item is None and user["active"]:
        return _reactivate(s, uid, user, base)
    if item is not None and not user["active"]:
        _run(s, "access.scimDeactivateUser", {"external_id": item.get("external_id") or item["id"]})
    elif item is not None:
        _run(s, "access.scimUpsertUser", {"external_id": user["external_id"], "email": user["email"], "name": user["name"],
                                          "active": True, "groups": user["groups"]})  # fmt: skip
    return get_user(s, uid, base)


def _reactivate(s: Session, uid: str, user: dict[str, Any], base: str) -> dict[str, Any]:
    gone = next((r for r in _inactive(s) if r["id"] == uid), None)
    groups = list(user["groups"]) or list(gone.get("groups", [])) if gone else list(user["groups"])
    _run(s, "access.scimUpsertUser", {"external_id": user["external_id"], "email": user["email"], "name": user["name"],
                                      "active": True, "groups": groups})  # fmt: skip
    return get_user(s, uid, base)


def deactivate_user(s: Session, uid: str, base: str) -> None:
    get_user(s, uid, base)
    item = find_item(s, uid)
    if item is not None:
        _run(s, "access.scimDeactivateUser", {"external_id": item.get("external_id") or item["id"]})


# ---------------------------------------------------------------- groups: the group map's rows and their members
def group_names(s: Session) -> list[str]:
    ctx = load_context(s)
    names = set(ctx.group_map or {})
    for u in state.items(s, "idp_users"):
        names.update(groups_of(u))
    return sorted(names)


def _members(s: Session, group: str) -> list[dict[str, str]]:
    return [{"value": u["id"], "display": str(u["email"]).lower()} for u in state.items(s, "idp_users") if group in groups_of(u)]


def _group_json(s: Session, group: str, base: str) -> dict[str, Any]:
    members = [m | {"$ref": f"{base}/Users/{m['value']}"} for m in _members(s, group)]
    return {"schemas": [GROUP_SCHEMA], "id": group, "displayName": group, "members": members,
            "meta": {"resourceType": "Group", "location": f"{base}/Groups/{group}"}}  # fmt: skip


def all_groups(s: Session, base: str) -> list[dict[str, Any]]:
    return [_group_json(s, g, base) for g in group_names(s)]


def get_group(s: Session, group: str, base: str) -> dict[str, Any]:
    if group not in group_names(s):
        raise ScimHttpError(404, f"No group {group}.")
    return _group_json(s, group, base)


def patch_group(s: Session, group: str, body: Any, base: str) -> dict[str, Any]:
    """Add or remove members (`add`, `remove`, `replace` on `members`); the group itself is the group map's, never changed."""
    get_group(s, group, base)
    patch = parse(PatchOp, body)
    now = {m["value"] for m in _members(s, group)}
    want = set(now)
    for op in patch.Operations:
        verb = op.op.lower()
        path = (op.path or "members").strip()
        if not path.lower().startswith("members") or verb not in ("add", "remove", "replace"):
            raise ScimHttpError(400, "Only members of a group can be changed.", "mutability")
        named = {str(v.get("value")) for v in (op.value if isinstance(op.value, list) else []) if isinstance(v, dict)}
        if m := re.search(r'value eq "([^"]*)"', path):
            named.add(m.group(1))
        want = want | named if verb == "add" else want - named if verb == "remove" else named if named or op.value == [] else want
    external = {k: (find_item(s, k) or {}).get("external_id") or k for k in want | now}
    for k in want | now:
        if find_item(s, k) is None:
            raise ScimHttpError(400, f"No user {k}.", "invalidValue")
    add, drop = sorted(want - now), sorted(now - want)
    _run(
        s, "access.scimPatchGroup", {"group_id": group, "add": [external[k] for k in add], "remove": [external[k] for k in drop]}
    )
    return _group_json(s, group, base)
