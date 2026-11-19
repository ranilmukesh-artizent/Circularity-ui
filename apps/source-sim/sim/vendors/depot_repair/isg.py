"""Oracle E-Business Suite Integrated SOA Gateway (ISG) REST conventions, shared by the Depot Repair and Lease mocks.

URL           <host>/webservices/rest/<service alias>/<method name>/        (PL/SQL API methods)
Auth          HTTP Basic with an EBS user, or token-based: GET|POST /webservices/rest/login with Basic auth →
              {"data": {"accessTokenName", "accessToken", "ebsVersion"}}; the token is sent back as the cookie
              <accessTokenName>=<accessToken>. POST /webservices/rest/logout ends it.
Request       POST {"<METHOD>_Input": {"RESTHeader": {Responsibility, RespApplication, SecurityGroup,
              NLSLanguage, Org_Id}, "InputParameters": {"P_...": ...}}}; GET methods take the IN parameters as
              query parameters (ctx_responsibility, ctx_respapplication, ctx_securitygroup, ctx_nlslanguage,
              ctx_orgid carry the header).
Response      {"OutputParameters": {"@xmlns:xsi", "@xmlns", "X_RETURN_STATUS": "S" | "E" | "U", "X_MSG_COUNT",
              "X_MSG_DATA", other OUT parameters}}; a PL/SQL table OUT parameter is {"<NAME>_ITEM": [records]}.
              Business validation errors are not HTTP errors: the API answers 200 with X_RETURN_STATUS "E" and
              the message in X_MSG_DATA, as an EBS public API does.
Faults        {"ISGServiceFault": {"Code", "Message", "Resolution", "ServiceDetails": {"ServiceName",
              "OperationName", "InstanceId"}}} with an HTTP 4xx/5xx status.
"""

import base64
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

IST = timezone(timedelta(hours=5, minutes=30))  # ASSUMPTION: the EBS database time zone is Asia/Kolkata
EBS_VERSION = "12.2.13"


class IsgFault(Exception):
    def __init__(self, status: int, code: str, message: str, resolution: str = "", service: str = "", operation: str = ""):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.resolution, self.service, self.operation = resolution, service, operation

    @property
    def response(self) -> JSONResponse:
        return fault(self.status, self.code, self.message, self.resolution, self.service, self.operation)


def fault(status: int, code: str, message: str, resolution: str = "", service: str = "", operation: str = "") -> JSONResponse:
    body = {
        "ISGServiceFault": {
            "Code": code,
            "Message": message,
            "Resolution": resolution or "Correct the request and try again.",
            "ServiceDetails": {"ServiceName": service, "OperationName": operation, "InstanceId": "0"},
        }
    }
    return JSONResponse(body, status)


@dataclass
class Gateway:
    """One EBS instance's ISG endpoint: its users and issued access tokens."""

    host: str  # e.g. /depot-repair
    users: dict[str, str]
    token_name: str
    tokens: dict[str, tuple[str, float]] = field(default_factory=dict)  # token → (user, expiry)
    ttl: int = 3600

    @property
    def rest(self) -> str:
        return self.host + "/webservices/rest"

    def routes(self, router) -> None:
        async def login(request: Request):
            user = self._basic(request)
            if not user:
                return fault(
                    401, "ISG_USER_AUTHENTICATION_FAILED", "User authentication failed.", "Check the user name and password."
                )
            tok = secrets.token_urlsafe(24)
            self.tokens[tok] = (user, time.time() + self.ttl)
            resp = JSONResponse({"data": {"accessTokenName": self.token_name, "accessToken": tok, "ebsVersion": EBS_VERSION}})
            resp.set_cookie(self.token_name, tok, httponly=True)
            return resp

        async def logout(request: Request):
            tok = request.cookies.get(self.token_name)
            self.tokens.pop(tok or "", None)
            return JSONResponse({"data": {"message": "Logged out"}})

        router.add_api_route(self.rest + "/login", login, methods=["GET", "POST"])
        router.add_api_route(self.rest + "/logout", logout, methods=["GET", "POST"])

    def _basic(self, request: Request) -> str | None:
        h = request.headers.get("authorization", "")
        if not h.lower().startswith("basic "):
            return None
        try:
            user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            return None
        return user.upper() if self.users.get(user.upper()) == pw else None

    def user(self, request: Request) -> str:
        """The authenticated EBS user, or IsgFault 401."""
        if request.headers.get("authorization", "").lower().startswith("basic "):
            if user := self._basic(request):
                return user
            raise IsgFault(
                401, "ISG_USER_AUTHENTICATION_FAILED", "User authentication failed.", "Check the user name and password."
            )
        tok = request.cookies.get(self.token_name)
        if tok and (entry := self.tokens.get(tok)) and entry[1] >= time.time():
            return entry[0]
        if tok:
            raise IsgFault(401, "ISG_INVALID_ACCESS_TOKEN", "The access token is invalid or has expired.", "Log in again.")
        raise IsgFault(
            401, "ISG_USER_AUTHENTICATION_FAILED", "Authentication is required.", "Use HTTP Basic or log in for a token."
        )

    def expire_all_tokens(self) -> int:
        n = len(self.tokens)
        self.tokens.clear()
        return n


async def input_parameters(request: Request, method: str, service: str) -> dict:
    """The InputParameters of a POST body wrapped as {"<METHOD>_Input": {"RESTHeader", "InputParameters"}}."""
    try:
        body = await request.json()
    except ValueError as e:
        raise IsgFault(400, "ISG_INVALID_INPUT_PAYLOAD", "The request payload is not valid JSON.", "", service, method) from e
    wrapper = f"{method.upper()}_Input"
    if not isinstance(body, dict) or not isinstance(body.get(wrapper), dict):
        raise IsgFault(
            400, "ISG_INVALID_INPUT_PAYLOAD", f"The request payload must have the root element {wrapper}.", "", service, method
        )
    params = body[wrapper].get("InputParameters")
    if not isinstance(params, dict):
        raise IsgFault(400, "ISG_INVALID_INPUT_PAYLOAD", f"{wrapper}.InputParameters is missing.", "", service, method)
    return params


def output(product: str, alias: str, method: str, params: dict, status: str = "S", messages: list[str] | None = None) -> dict:
    msgs = messages or []
    return {
        "OutputParameters": {
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xmlns": f"http://xmlns.oracle.com/apps/{product}/rest/{alias}/{method}/",
            **params,
            "X_RETURN_STATUS": status,
            "X_MSG_COUNT": str(len(msgs)),
            "X_MSG_DATA": " ".join(msgs) if msgs else None,
        }
    }


def table(name: str, rows: list[dict]) -> dict:
    return {f"{name}_ITEM": rows}


def ebs_ts(d: datetime | str | None) -> str | None:
    """EBS ISG date-time: '2026-10-03T19:30:00.000+05:30'."""
    if d is None or d == "":
        return None
    if isinstance(d, str):
        d = datetime.fromisoformat(d.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(IST).isoformat(timespec="milliseconds")


def parse_ts(v: str | None, name: str, service: str, method: str) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise IsgFault(
            400, "ISG_INVALID_PARAMETER_VALUE", f"{name}: '{v}' is not a valid date.", "Use ISO 8601.", service, method
        ) from e
    return d if d.tzinfo else d.replace(tzinfo=IST)


def paging(params, service: str, method: str) -> tuple[int, int]:
    """P_START_INDEX (1-based, default 1) and P_MAX_RECORDS (default 100, at most 500)."""
    out = []
    for name, default, hi in (("P_START_INDEX", 1, 10**9), ("P_MAX_RECORDS", 100, 500)):
        v = params.get(name)
        try:
            n = int(v) if v not in (None, "") else default
        except ValueError:
            n = 0
        if not 1 <= n <= hi:
            raise IsgFault(
                400, "ISG_INVALID_PARAMETER_VALUE", f"{name} must be a whole number from 1 to {hi}.", "", service, method
            )
        out.append(n)
    return out[0], out[1]


def dispatch(gw: Gateway, request: Request, alias: str, method: str, services: dict[str, dict[str, tuple[str, Callable]]]):
    """Find the method of a service alias; returns (verb, handler) or raises the ISG fault."""
    if alias not in services:
        raise IsgFault(404, "ISG_SERVICE_NOT_FOUND", f"The service alias {alias} is not deployed.", "", alias, method)
    ops = services[alias]
    if method.lower() not in ops:
        raise IsgFault(404, "ISG_METHOD_NOT_FOUND", f"The method {method} is not deployed for {alias}.", "", alias, method)
    verb, fn = ops[method.lower()]
    if request.method != verb:
        raise IsgFault(
            405,
            "ISG_UNSUPPORTED_REST_VERB",
            f"System does not support the HTTP verb {request.method} for {alias}/{method}.",
            f"Use {verb}.",
            alias,
            method,
        )
    return fn
