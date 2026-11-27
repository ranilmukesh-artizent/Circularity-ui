"""Shared pieces of the SCIM and directory-sync tests (P9-8.11): the bearer token, cleanup and an in-process directory.

Owns: the `idp` webhook token, a `FakeDirectory` (an httpx MockTransport that answers `/directory/api/users` and
`/groups` the way the source-sim mock does, paged), and `clean()`, which puts back what these tests change. Never does:
call source-sim; the lead runs the same flows against the real mock after the merge.
"""

import httpx
from sqlalchemy import text

from di.connectors import connection, secrets
from di.core import policy, state
from di.core.db import SessionLocal
from di.services import directory_sync

TOKEN = "scim-test-token-0123456789"
BASE = "http://directory.test/directory"
JOINER = "joiner.one@example.com"
PLANNER_B = "circ-planners-customer-b"
PLANNER_C = "circ-planners-customer-c"
BEARER = {"Authorization": "Bearer " + TOKEN}
MINE = (
    "'access.scimUpsertUser', 'access.scimDeactivateUser', 'access.scimPatchGroup', 'access.provisionUser', "
    "'access.syncDirectory'"
)
EVENT_TYPES = (
    "('user.provisioned', 'user.deprovisioned', 'access.revoked', 'directory.synced', 'access.reassigned', 'identity.revoked', "
    "'identity.scim.ignored')"
)


def clean() -> None:
    state.reset(["accounts", "idp_users", "access_settings", "requests", "account_revoked"])
    with SessionLocal() as s:
        journal = f"SELECT seq FROM action_journal WHERE action IN ({MINE})"  # noqa: S608 - a constant
        s.execute(text(f"DELETE FROM domain_event WHERE seq IN ({journal})"))  # noqa: S608 - a constant
        s.execute(text(f"DELETE FROM action_journal WHERE action IN ({MINE})"))  # noqa: S608 - a constant
        s.execute(text(f"DELETE FROM state_item WHERE collection = 'events' AND data->>'type' IN {EVENT_TYPES}"))  # noqa: S608
        s.execute(text("DELETE FROM tenant_grant WHERE account_id LIKE 'sso-%'"))
        s.execute(text("DELETE FROM source_secret WHERE source_id = 'idp'"))
        s.execute(text("DELETE FROM source_connection WHERE source_id = 'idp'"))
        s.execute(text("DELETE FROM fetch_log WHERE source_id = 'idp'"))
        s.execute(text("DELETE FROM oidc_login"))
        s.commit()


def set_token() -> None:
    with SessionLocal() as s:
        secrets.put_secret(s, "idp", "webhook", TOKEN, None, "test")
        s.commit()


class FakeDirectory:
    """The directory's users and groups over `httpx.MockTransport`, two to a page so paging is exercised."""

    PAGE = 2

    def __init__(self) -> None:
        self.users: list[dict] = [
            {"id": u["id"], "email": u["email"], "name": u["email"].split("@")[0],
             "groups": [policy.IDP_GROUPS[u["id"]]] if u["id"] in policy.IDP_GROUPS else []}
            for u in policy.starting_idp_users()
        ]  # fmt: skip
        self.paths: list[str] = []

    def add(self, email: str, groups: list[str], uid: str = "u-joiner-one") -> None:
        self.users.append({"id": uid, "email": email, "name": "Joiner One", "groups": groups})

    def remove(self, uid: str) -> None:
        self.users = [u for u in self.users if u["id"] != uid]

    def _page(self, items: list[dict], offset: int) -> dict:
        end = offset + self.PAGE
        return {"data": items[offset:end], "next": end if end < len(items) else None}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        offset = int(request.url.params.get("offset", "0"))
        if request.url.path == "/directory/api/users":
            return httpx.Response(200, json=self._page(self.users, offset))
        if request.url.path == "/directory/api/groups":
            groups: dict[str, list[str]] = {}
            for u in self.users:
                for g in u["groups"]:
                    groups.setdefault(g, []).append(u["id"])
            rows = [{"id": g, "name": g, "members": m} for g, m in sorted(groups.items())]
            return httpx.Response(200, json=self._page(rows, offset))
        return httpx.Response(404)

    def connect(self, monkeypatch) -> None:
        """Register the directory as source `idp` and send the sync's calls to this fake."""
        with SessionLocal() as s:
            connection.save_connection(s, "idp", "test", base_url=BASE, protocol="rest", auth_kind="none")
            s.commit()
        monkeypatch.setattr(directory_sync, "HTTP_TRANSPORT", httpx.MockTransport(self.handle))
