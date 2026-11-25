"""The SCIM 2.0 endpoints under /scim/v2 (plan 9 P9-8.11; RFC 7644), thin over di.services.scim.

    GET  /Users?filter&startIndex&count      POST /Users           GET, PUT, PATCH, DELETE /Users/{id}
    GET  /Groups                             GET /Groups/{id}      PATCH /Groups/{id}  (members only)
    GET  /ServiceProviderConfig, /Schemas, /ResourceTypes

Every call needs `Authorization: Bearer <the webhook secret of source idp>`; anything else is 401 with a SCIM error body.
Answers use `application/scim+json`, errors are RFC 7644 3.12 bodies (also for a bad body or query). DELETE deactivates (a
leaver is never deleted); POST, PUT and DELETE on /Groups answer 501 (groups are the group map's rows).
Owns: the HTTP shape. Never does: decide anything (di.services.scim and the access actions do).
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from di.core.deps import DbSession
from di.services import scim
from di.services.scim import ScimHttpError

MEDIA = "application/scim+json"


class ScimResponse(JSONResponse):
    media_type = MEDIA


def _fail(e: ScimHttpError) -> Response:
    headers = {"WWW-Authenticate": "Bearer"} if e.status == 401 else None
    return ScimResponse(e.body(), status_code=e.status, headers=headers)


class ScimRoute(APIRoute):
    """Turns a ScimHttpError, or a query FastAPI could not read, into the SCIM error body."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def run(request: Request) -> Response:
            try:
                return await handler(request)
            except ScimHttpError as e:
                return _fail(e)
            except RequestValidationError as e:
                return _fail(ScimHttpError(400, str(e.errors()[0]["msg"]), "invalidValue"))

        return run


def _token(request: Request, session: DbSession) -> None:
    if not scim.token_ok(session, request.headers.get("authorization")):
        raise ScimHttpError(401, "A valid bearer token is required.")


async def _body(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError as e:
        raise ScimHttpError(400, "The body is not valid JSON.", "invalidSyntax") from e


router = APIRouter(
    prefix="/scim/v2", tags=["SCIM"], route_class=ScimRoute, dependencies=[Depends(_token)], include_in_schema=True
)
Body = Annotated[Any, Depends(_body)]


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/scim/v2"


def _ok(body: dict[str, Any], status: int = 200, location: str | None = None) -> Response:
    return ScimResponse(body, status_code=status, headers={"Location": location} if location else None)


# ---------------------------------------------------------------- Users
@router.get("/Users")
def list_users(request: Request, session: DbSession, filter: str | None = None, startIndex: int = 1, count: int | None = None):
    return _ok(scim.page(scim.all_users(session, _base(request)), filter, startIndex, count))


@router.post("/Users")
def create_user(request: Request, session: DbSession, body: Body):
    user = scim.create_user(session, body, _base(request))
    return _ok(user, 201, user["meta"]["location"])


@router.get("/Users/{uid}")
def get_user(uid: str, request: Request, session: DbSession):
    return _ok(scim.get_user(session, uid, _base(request)))


@router.patch("/Users/{uid}")
def patch_user(uid: str, request: Request, session: DbSession, body: Body):
    ops = scim.parse(scim.PatchOp, body)
    return _ok(scim.update_user(session, uid, ops.Operations, None, _base(request)))


@router.put("/Users/{uid}")
def replace_user(uid: str, request: Request, session: DbSession, body: Body):
    return _ok(scim.update_user(session, uid, None, scim.parse(scim.UserIn, body), _base(request)))


@router.delete("/Users/{uid}", status_code=204)
def delete_user(uid: str, request: Request, session: DbSession):
    scim.deactivate_user(session, uid, _base(request))
    return Response(status_code=204)


# ---------------------------------------------------------------- Groups (the group map's rows; only members change)
@router.get("/Groups")
def list_groups(request: Request, session: DbSession, startIndex: int = 1, count: int | None = None):
    rows = scim.all_groups(session, _base(request))
    return _ok(scim.page(rows, None, startIndex, count))


@router.get("/Groups/{gid}")
def get_group(gid: str, request: Request, session: DbSession):
    return _ok(scim.get_group(session, gid, _base(request)))


@router.patch("/Groups/{gid}")
def patch_group(gid: str, request: Request, session: DbSession, body: Body):
    return _ok(scim.patch_group(session, gid, body, _base(request)))


@router.post("/Groups")
@router.put("/Groups/{gid}")
@router.delete("/Groups/{gid}")
def groups_are_the_maps(gid: str = ""):  # noqa: ARG001 - the path parameter of PUT and DELETE
    raise ScimHttpError(501, "Groups are the group map's rows: people change them in Access, with approval.")


# ---------------------------------------------------------------- discovery (RFC 7643 5, 6, 7)
CONFIG = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"


def _attr(name: str, type_: str = "string", **kw: Any) -> dict[str, Any]:
    return {"name": name, "type": type_, "multiValued": False, "required": False, "mutability": "readWrite", **kw}


SCHEMAS = [
    {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"], "id": scim.USER_SCHEMA, "name": "User",
     "description": "A person in the organisation's directory.",
     "attributes": [_attr("userName", required=True, uniqueness="server"), _attr("externalId"), _attr("displayName"),
                    _attr("name", "complex"), _attr("emails", "complex", multiValued=True), _attr("active", "boolean"),
                    _attr("groups", "complex", multiValued=True, mutability="readOnly")]},
    {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"], "id": scim.GROUP_SCHEMA, "name": "Group",
     "description": "A directory group; its role comes from the approved group map.",
     "attributes": [_attr("displayName", required=True, mutability="readOnly"),
                    _attr("members", "complex", multiValued=True)]},
]  # fmt: skip


@router.get("/ServiceProviderConfig")
def service_provider_config(request: Request):
    return _ok({
        "schemas": [CONFIG], "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": scim.MAX_RESULTS},
        "changePassword": {"supported": False}, "sort": {"supported": False}, "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token",
                                   "description": "The token held for the directory source.",
                                   "specUri": "https://www.rfc-editor.org/info/rfc6750", "primary": True}],
        "meta": {"resourceType": "ServiceProviderConfig", "location": _base(request) + "/ServiceProviderConfig"},
    })  # fmt: skip


@router.get("/Schemas")
def schemas():
    return _ok(scim.listing(SCHEMAS, len(SCHEMAS), 1, len(SCHEMAS)))


@router.get("/ResourceTypes")
def resource_types():
    types = [
        {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": name, "name": name,
         "endpoint": "/" + name + "s", "schema": schema}
        for name, schema in (("User", scim.USER_SCHEMA), ("Group", scim.GROUP_SCHEMA))
    ]  # fmt: skip
    return _ok(scim.listing(types, len(types), 1, len(types)))
