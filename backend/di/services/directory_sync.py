"""The pull sync from the directory source (plan 9 P9-8.11, story X-10): joiners and leavers without a push.

Reads the directory's users and groups through the connection of source `idp` (kind generic_rest, registered through
P9-8.1): `GET /api/users` and `/api/groups` (under `/directory`), paged with `offset` and `limit`, each answering
`{"data": [...], "next": offset | null}`. Then, for every user, runs `access.scimUpsertUser` (a joiner is provisioned
from the approved group map), and for every user it saw before and does not see now, `access.scimDeactivateUser`.
All writes are those two actions run through `pipeline.invoke` as the system actor, the same as the SCIM routes.

Owns: the reading (paging, the connection, the credential) and the joiner/leaver decision.
Never does: write state itself; give a role (the group map does, in the action); deactivate an Admin account, a user
this sync never saw (no `external_id` from the directory), or anyone when the directory could not be read in full
(a failed read raises `SourceError` before any write).
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.orm import Session

from di.connectors import connection, secrets
from di.connectors.http import Auth, SourceClient, SourceError, Static
from di.core import state
from di.core.auth import load_context
from di.services.actions.pipeline import SYSTEM, CallContext, invoke

SOURCE = "idp"
PAGE = 100
MAX_PAGES = 1000  # a directory that never ends is cut here, not followed forever
ORIGIN = "directory"
# tests set this to an httpx transport that stands in for the directory (no network)
HTTP_TRANSPORT: httpx.BaseTransport | None = None


@dataclass
class SyncResult:
    users: int
    joiners: list[str] = field(default_factory=list)
    leavers: list[str] = field(default_factory=list)
    mappings: int = 0


def connected(s: Session) -> bool:
    """A directory source is connected: source `idp` has a connection."""
    return connection.connection_for(s, SOURCE) is not None


def _client(s: Session) -> tuple[SourceClient, str]:
    conn = connection.connection_for(s, SOURCE)
    if conn is None:  # not reached: `connected` was checked
        raise SourceError("client", "The directory source is not connected.")
    connection.check_credential(s, SOURCE)
    secret = secrets.active_secret(s, SOURCE)
    auth: Auth = Static({"Authorization": "Bearer " + secret}) if secret and conn.auth_kind == "bearer" else Auth()
    client = SourceClient(SOURCE, conn.base_url, auth, s)
    if HTTP_TRANSPORT is not None:
        client.http = httpx.Client(transport=HTTP_TRANSPORT, timeout=20)
    prefix = "" if conn.base_url.rstrip("/").endswith("/directory") else "/directory"
    return client, prefix


def _pages(client: SourceClient, path: str) -> Iterator[dict[str, Any]]:
    offset = 0
    for _ in range(MAX_PAGES):
        body = client.get_json(path, params={"offset": offset, "limit": PAGE})
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise SourceError("client", f"The directory's answer for {path} has no data list.")
        yield from (row for row in data if isinstance(row, dict))
        nxt = body.get("next")
        if not isinstance(nxt, int) or nxt <= offset:
            return
        offset = nxt


def _read(s: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client, prefix = _client(s)
    try:
        return list(_pages(client, prefix + "/api/users")), list(_pages(client, prefix + "/api/groups"))
    finally:
        client.close()


def _memberships(groups: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for g in groups:
        for member in g.get("members") or []:
            out.setdefault(str(member), set()).add(str(g["id"]))
    return out


def pull(s: Session) -> SyncResult:
    """Read the directory in full, then upsert every user (joiners are provisioned) and deactivate every leaver."""
    users, groups = _read(s)  # a failed read raises here, before anything is written
    member_of = _memberships(groups)
    ctx = CallContext(actor=SYSTEM, session=s)
    out = SyncResult(users=0)
    seen: set[str] = set()
    for u in users:
        uid, email = str(u["id"]), str(u.get("email", "")).strip().lower()
        if not email:
            continue
        seen.add(uid)
        gs = sorted({*(str(g) for g in u.get("groups") or []), *member_of.get(uid, set())})
        name = str(u.get("name") or email.split("@")[0])
        r = invoke("access.scimUpsertUser", {"external_id": uid, "email": email, "name": name, "active": True, "groups": gs,
                                             "origin": ORIGIN}, ctx)  # fmt: skip
        if r["ok"] and r["output"].get("created_account"):
            out.joiners.append(email)
    for item in state.items(s, "idp_users"):
        if item.get("origin") == ORIGIN and item.get("external_id") not in seen:
            r = invoke("access.scimDeactivateUser", {"external_id": item["external_id"]}, ctx)
            if r["ok"]:
                out.leavers.append(str(item["email"]).lower())
    out.users = len(state.items(s, "idp_users"))
    out.mappings = len(load_context(s).group_map or {})
    return out
