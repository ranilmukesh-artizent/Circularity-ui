"""AWS IoT Core API mock (docs/backend-steps.md, B5c). See the package docstring for documentation and assumptions.

Control plane (the iot endpoint, SigV4 service "iot"), under /aws-iot/iot:
    GET  /things                                   ListThings  ?maxResults (1-250) &nextToken &attributeName
                                                   &attributeValue &usePrefixAttributeValue &thingTypeName
    GET  /things/{thingName}                       DescribeThing
    GET  /thing-groups                             ListThingGroups ?parentGroup &namePrefixFilter &recursive
    GET  /thing-groups/{thingGroupName}            DescribeThingGroup
    GET  /thing-groups/{thingGroupName}/things     ListThingsInThingGroup ?recursive
    GET  /jobs                                     ListJobs ?status &targetSelection &thingGroupName
    GET  /jobs/{jobId}                             DescribeJob
    GET  /rules                                    ListTopicRules ?topic &ruleDisabled
    GET  /rules/{ruleName}                         GetTopicRule
    POST /rules/{ruleName}/enable | /disable       EnableTopicRule, DisableTopicRule (the seeded rules start disabled)
Data plane (the ATS data endpoint, SigV4 service "iotdata"), under /aws-iot/data:
    GET|POST|DELETE /things/{thingName}/shadow     Get | Update | DeleteThingShadow ?name= (named shadow)
    GET  /api/things/shadow/ListNamedShadowsForThing/{thingName}   ?nextToken &pageSize
    POST /topics/{topic}                           Publish ?qos (0|1) &retain (true|false), body = the payload
    GET  /retainedMessage                          ListRetainedMessages ?maxResults (1-200) &nextToken
    GET  /retainedMessage/{topic}                  GetRetainedMessage (topic URL-encoded)
Every list pages with maxResults + an opaque nextToken (absent on the last page).
Errors: HTTP status, header x-amzn-ErrorType: <Code>, body {"message": "..."}; every response has x-amzn-RequestId.
"""

import base64
import binascii
import json
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from sim import clock, faults
from sim.db import engine
from sim.vendors.aws_iot import fleet
from sim.vendors.aws_iot import tables as t
from sim.vendors.aws_iot.seed import REGION
from sim.vendors.aws_iot.sigv4 import SigError, verify

router = APIRouter(prefix="/aws-iot")

ACCOUNT_USER = "arn:aws:iam::123456789012:user/"
# demo IAM users (access key -> secret, user, allowed actions); "*" allows every action
CREDENTIALS: dict[str, dict[str, Any]] = {
    "AKIACIRCULARITYDEMO1": {
        "secret": "circularity-demo/aws-iot/K7MDENG+bPxRfiCYDI",
        "user": "circularity-di-connector",
        "actions": {"*"},
    },
    "AKIACIRCULARITYRDONL": {
        "secret": "circularity-demo/aws-iot/readonly+R3AD0NLY",
        "user": "circularity-fleet-viewer",
        "actions": {
            "iot:ListThings",
            "iot:DescribeThing",
            "iot:ListThingGroups",
            "iot:DescribeThingGroup",
            "iot:ListThingsInThingGroup",
        },
    },  # fmt: skip
}
MAX_PAYLOAD = 128 * 1024


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"message": message}, status_code=status, headers={"x-amzn-ErrorType": code, "x-amzn-RequestId": str(uuid.uuid4())}
    )


def ok(body: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"x-amzn-RequestId": str(uuid.uuid4())})


def _fault(kind: str, status: int, message: str) -> Response:
    """The shared fault injection (sim/faults.py), answered the way AWS answers."""
    if kind == "token_expired":
        return error(403, "ExpiredTokenException", "The security token included in the request is expired")
    if kind == "unavailable" or status == 503:
        return error(503, "ServiceUnavailableException", "Service Unavailable")
    if status == 429:
        return error(429, "ThrottlingException", "Rate exceeded")
    if status >= 500:
        return error(status, "InternalFailureException", "An internal error occurred. (simulated)")
    return error(status, "InvalidRequestException", message)


faults.SHAPES["iot"] = _fault


async def authorize(request: Request, service: str, action: str, resource: str) -> JSONResponse | None:
    """SigV4 (sigv4.py) and the caller's IAM permissions. None when allowed, else the AWS error response."""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        key = verify(
            request.method,
            request.scope["path"],
            request.url.query,
            headers,
            body,
            {k: v["secret"] for k, v in CREDENTIALS.items()},
            REGION,
            service,
        )
    except SigError as e:
        return error(403, e.code, e.message)
    user = CREDENTIALS[key]
    if "*" not in user["actions"] and action not in user["actions"]:
        return error(
            401,
            "UnauthorizedException",
            f"User: {ACCOUNT_USER}{user['user']} is not authorized to perform: {action} on resource: {resource}",
        )
    return None


# ---------------------------------------------------------------- paging
def _page_args(request: Request, default: int, maximum: int, size_param: str = "maxResults") -> tuple[int, int] | JSONResponse:
    q = request.query_params
    try:
        size = int(q.get(size_param, default))
    except ValueError:
        return error(400, "InvalidRequestException", f"{size_param} must be an integer")
    if not 1 <= size <= maximum:
        return error(400, "InvalidRequestException", f"{size_param} must be between 1 and {maximum}")
    tok = q.get("nextToken")
    offset = 0
    if tok:
        try:
            kind, _, n = base64.urlsafe_b64decode(tok.encode()).decode().partition(":")
            offset = int(n)
            if kind != "o" or offset < 0:
                raise ValueError
        except (ValueError, binascii.Error, UnicodeDecodeError):
            return error(400, "InvalidRequestException", "The pagination token is invalid.")
    return offset, size


def _token(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def _page(items: list, offset: int, size: int, key: str, extra: dict | None = None) -> JSONResponse:
    body: dict[str, Any] = {key: items[offset : offset + size]}
    if offset + size < len(items):
        body["nextToken"] = _token(offset + size)
    return ok(body | (extra or {}))


def _bool(v: str | None) -> bool | None:
    return None if v is None else v.lower() == "true"


# ---------------------------------------------------------------- control plane
@router.get("/iot/things")
async def list_things(request: Request):
    if denied := await authorize(request, "iot", "iot:ListThings", "*"):
        return denied
    pa = _page_args(request, 50, 250)
    if isinstance(pa, JSONResponse):
        return pa
    q = request.query_params
    name, value = q.get("attributeName"), q.get("attributeValue")
    if (name is None) != (value is None):
        return error(400, "InvalidRequestException", "attributeName and attributeValue must be given together")
    with engine.connect() as conn:
        docs = conn.execute(select(t.THING.c.doc).order_by(t.THING.c.thing_name)).scalars().all()
    out = []
    for d in docs:
        if q.get("thingTypeName") and d["thingTypeName"] != q["thingTypeName"]:
            continue
        if name is not None:
            got = d["attributes"].get(name)
            if got is None or (got != value if not _bool(q.get("usePrefixAttributeValue")) else not got.startswith(value)):
                continue
        out.append({k: d[k] for k in ("thingName", "thingTypeName", "thingArn", "attributes", "version")})
    return _page(out, *pa, "things")


@router.get("/iot/things/{thing_name}")
async def describe_thing(thing_name: str, request: Request):
    if denied := await authorize(request, "iot", "iot:DescribeThing", f"arn:aws:iot:{REGION}:123456789012:thing/{thing_name}"):
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(t.THING.c.doc).where(t.THING.c.thing_name == thing_name)).scalar()
    return ok(doc) if doc else error(404, "ResourceNotFoundException", f"Thing {thing_name} cannot be found.")


def _groups(conn: Connection) -> dict[str, Any]:
    return {r.group_name: r for r in conn.execute(select(t.THING_GROUP).order_by(t.THING_GROUP.c.group_name))}


def _descendants(groups: dict, name: str) -> list[str]:
    kids = [g for g, r in groups.items() if r.parent == name]
    return kids + [d for k in kids for d in _descendants(groups, k)]


@router.get("/iot/thing-groups")
async def list_thing_groups(request: Request):
    if denied := await authorize(request, "iot", "iot:ListThingGroups", "*"):
        return denied
    pa = _page_args(request, 50, 250)
    if isinstance(pa, JSONResponse):
        return pa
    q = request.query_params
    with engine.connect() as conn:
        groups = _groups(conn)
    names = list(groups)
    if q.get("parentGroup"):
        if q["parentGroup"] not in groups:
            return error(404, "ResourceNotFoundException", f"Thing group {q['parentGroup']} cannot be found.")
        recursive = _bool(q.get("recursive"))
        names = (
            _descendants(groups, q["parentGroup"])
            if recursive is not False
            else [g for g, r in groups.items() if r.parent == q["parentGroup"]]
        )
    if q.get("namePrefixFilter"):
        names = [n for n in names if n.startswith(q["namePrefixFilter"])]
    items = [{"groupName": n, "groupArn": groups[n].doc["thingGroupArn"]} for n in sorted(names)]
    return _page(items, *pa, "thingGroups")


@router.get("/iot/thing-groups/{group_name}")
async def describe_thing_group(group_name: str, request: Request):
    if denied := await authorize(request, "iot", "iot:DescribeThingGroup", f"thinggroup/{group_name}"):
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(t.THING_GROUP.c.doc).where(t.THING_GROUP.c.group_name == group_name)).scalar()
    return ok(doc) if doc else error(404, "ResourceNotFoundException", f"Thing group {group_name} cannot be found.")


@router.get("/iot/thing-groups/{group_name}/things")
async def list_things_in_group(group_name: str, request: Request):
    if denied := await authorize(request, "iot", "iot:ListThingsInThingGroup", f"thinggroup/{group_name}"):
        return denied
    pa = _page_args(request, 25, 250)
    if isinstance(pa, JSONResponse):
        return pa
    with engine.connect() as conn:
        groups = _groups(conn)
        if group_name not in groups:
            return error(404, "ResourceNotFoundException", f"Thing group {group_name} cannot be found.")
        wanted = [group_name] + (_descendants(groups, group_name) if _bool(request.query_params.get("recursive")) else [])
        names = (
            conn.execute(
                select(t.GROUP_MEMBER.c.thing_name)
                .where(t.GROUP_MEMBER.c.group_name.in_(wanted))
                .distinct()
                .order_by(t.GROUP_MEMBER.c.thing_name)
            )
            .scalars()
            .all()
        )
    return _page(list(names), *pa, "things")


@router.get("/iot/jobs")
async def list_jobs(request: Request):
    if denied := await authorize(request, "iot", "iot:ListJobs", "*"):
        return denied
    pa = _page_args(request, 50, 250)
    if isinstance(pa, JSONResponse):
        return pa
    q = request.query_params
    with engine.connect() as conn:
        docs = conn.execute(select(t.JOB.c.doc).order_by(t.JOB.c.job_id)).scalars().all()
    out = []
    for d in docs:
        if q.get("status") and d["status"] != q["status"]:
            continue
        if q.get("targetSelection") and d["targetSelection"] != q["targetSelection"]:
            continue
        if q.get("thingGroupName") and not any(x.endswith("thinggroup/" + q["thingGroupName"]) for x in d["targets"]):
            continue
        keys = ("jobArn", "jobId", "thingGroupId", "targetSelection", "status", "createdAt", "lastUpdatedAt", "completedAt")
        out.append({k: d[k] for k in keys if k in d})
    return _page(out, *pa, "jobs")


@router.get("/iot/jobs/{job_id}")
async def describe_job(job_id: str, request: Request):
    if denied := await authorize(request, "iot", "iot:DescribeJob", f"job/{job_id}"):
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(t.JOB.c.doc).where(t.JOB.c.job_id == job_id)).scalar()
    if not doc:
        return error(404, "ResourceNotFoundException", f"Job {job_id} cannot be found.")
    job = {k: v for k, v in doc.items() if k not in ("documentSource", "thingGroupId")}
    return ok({"documentSource": doc["documentSource"], "job": job})


@router.get("/iot/rules")
async def list_topic_rules(request: Request):
    if denied := await authorize(request, "iot", "iot:ListTopicRules", "*"):
        return denied
    pa = _page_args(request, 1000, 10000)
    if isinstance(pa, JSONResponse):
        return pa
    q = request.query_params
    with engine.connect() as conn:
        rows = conn.execute(select(t.RULE).order_by(t.RULE.c.rule_name)).all()
    out = []
    for r in rows:
        if q.get("topic") and q["topic"] != r.topic_filter:
            continue
        if _bool(q.get("ruleDisabled")) is not None and _bool(q.get("ruleDisabled")) != r.disabled:
            continue
        out.append(
            {
                "ruleArn": r.doc["ruleArn"],
                "ruleName": r.rule_name,
                "topicPattern": r.topic_filter,
                "createdAt": r.doc["rule"]["createdAt"],
                "ruleDisabled": r.disabled,
            }  # fmt: skip
        )
    return _page(out, *pa, "rules")


@router.get("/iot/rules/{rule_name}")
async def get_topic_rule(rule_name: str, request: Request):
    if denied := await authorize(request, "iot", "iot:GetTopicRule", f"rule/{rule_name}"):
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(t.RULE.c.doc).where(t.RULE.c.rule_name == rule_name)).scalar()
    # AWS answers a rule that does not exist with UnauthorizedException (401), not a 404
    return ok(doc) if doc else error(401, "UnauthorizedException", f"Rule {rule_name} does not exist")


async def _set_rule(rule_name: str, request: Request, disabled: bool) -> Response:
    """EnableTopicRule / DisableTopicRule: a disabled rule delivers nothing (the starting state: not provisioned)."""
    action = "iot:DisableTopicRule" if disabled else "iot:EnableTopicRule"
    if denied := await authorize(request, "iot", action, f"rule/{rule_name}"):
        return denied
    with engine.begin() as conn:
        doc = conn.execute(select(t.RULE.c.doc).where(t.RULE.c.rule_name == rule_name)).scalar()
        if not doc:
            return error(401, "UnauthorizedException", f"Rule {rule_name} does not exist")
        doc["rule"]["ruleDisabled"] = disabled
        conn.execute(t.RULE.update().where(t.RULE.c.rule_name == rule_name).values(disabled=disabled, doc=doc))
    return Response(status_code=200)


@router.post("/iot/rules/{rule_name}/enable")
async def enable_topic_rule(rule_name: str, request: Request):
    return await _set_rule(rule_name, request, False)


@router.post("/iot/rules/{rule_name}/disable")
async def disable_topic_rule(rule_name: str, request: Request):
    return await _set_rule(rule_name, request, True)


# ---------------------------------------------------------------- data plane: shadows
def _thing_exists(conn: Connection, name: str) -> bool:
    return conn.execute(select(t.THING.c.thing_name).where(t.THING.c.thing_name == name)).first() is not None


def _no_shadow(thing: str, name: str) -> JSONResponse:
    return error(404, "ResourceNotFoundException", f"No shadow exists with name: '{thing}{'~' + name if name else ''}'")


def _shadow_arn(thing: str, name: str) -> str:
    return f"arn:aws:iot:{REGION}:123456789012:thing/{thing}" + (f"/{name}" if name else "")


@router.get("/data/things/{thing_name}/shadow")
async def get_thing_shadow(thing_name: str, request: Request, name: str = ""):
    if denied := await authorize(request, "iotdata", "iot:GetThingShadow", _shadow_arn(thing_name, name)):
        return denied
    with engine.connect() as conn:
        doc = fleet.get_shadow(conn, thing_name, name)
    return ok(doc) if doc else _no_shadow(thing_name, name)


@router.post("/data/things/{thing_name}/shadow")
async def update_thing_shadow(thing_name: str, request: Request, name: str = ""):
    if denied := await authorize(request, "iotdata", "iot:UpdateThingShadow", _shadow_arn(thing_name, name)):
        return denied
    raw = await request.body()
    if len(raw) > 8 * 1024:
        return error(413, "RequestEntityTooLargeException", "The payload exceeds the maximum size allowed (8 KB).")
    try:
        doc = json.loads(raw)
    except ValueError:
        return error(400, "InvalidRequestException", "Payload contains invalid json")
    with engine.begin() as conn:
        if not _thing_exists(conn, thing_name):
            return error(404, "ResourceNotFoundException", f"Thing {thing_name} cannot be found.")
        try:
            return ok(fleet.update_shadow(conn, thing_name, name, doc))
        except fleet.ShadowError as e:
            return error(e.status, e.code, e.message)


@router.delete("/data/things/{thing_name}/shadow")
async def delete_thing_shadow(thing_name: str, request: Request, name: str = ""):
    if denied := await authorize(request, "iotdata", "iot:DeleteThingShadow", _shadow_arn(thing_name, name)):
        return denied
    with engine.begin() as conn:
        row = conn.execute(
            t.SHADOW.delete()
            .where(t.SHADOW.c.thing_name == thing_name, t.SHADOW.c.shadow_name == name)
            .returning(t.SHADOW.c.version)
        ).first()
        now = int(clock.now(conn).timestamp())
    return ok({"version": row.version, "timestamp": now}) if row else _no_shadow(thing_name, name)


@router.get("/data/api/things/shadow/ListNamedShadowsForThing/{thing_name}")
async def list_named_shadows(thing_name: str, request: Request):
    if denied := await authorize(request, "iotdata", "iot:ListNamedShadowsForThing", _shadow_arn(thing_name, "")):
        return denied
    pa = _page_args(request, 25, 100, "pageSize")
    if isinstance(pa, JSONResponse):
        return pa
    with engine.connect() as conn:
        names = (
            conn.execute(
                select(t.SHADOW.c.shadow_name)
                .where(t.SHADOW.c.thing_name == thing_name, t.SHADOW.c.shadow_name != "")
                .order_by(t.SHADOW.c.shadow_name)
            )
            .scalars()
            .all()
        )
        now = int(clock.now(conn).timestamp())
    return _page(list(names), *pa, "results", {"timestamp": now})


# ---------------------------------------------------------------- data plane: publish, retained messages
def _topic_arn(topic: str) -> str:
    return f"arn:aws:iot:{REGION}:123456789012:topic/{topic}"


@router.post("/data/topics/{topic:path}")
async def publish(topic: str, request: Request, qos: int = 0, retain: str = "false"):
    if denied := await authorize(request, "iotdata", "iot:Publish", _topic_arn(topic)):
        return denied
    if qos not in (0, 1):
        return error(400, "InvalidRequestException", "qos must be 0 or 1")
    if topic.startswith("$"):
        return error(403, "ForbiddenException", f"Publishing to the reserved topic {topic} is not allowed")
    if not topic or len(topic.encode()) > 256 or "+" in topic or "#" in topic:
        return error(400, "InvalidRequestException", "Invalid topic name")
    payload = await request.body()
    if len(payload) > MAX_PAYLOAD:
        return error(413, "RequestEntityTooLargeException", "The payload exceeds the maximum size allowed (128 KB).")
    with engine.begin() as conn:
        fleet.publish(conn, topic, payload, qos=qos, retain=retain.lower() == "true")
    return ok({})


@router.get("/data/retainedMessage")
async def list_retained(request: Request):
    if denied := await authorize(request, "iotdata", "iot:ListRetainedMessages", "*"):
        return denied
    pa = _page_args(request, 200, 200)
    if isinstance(pa, JSONResponse):
        return pa
    offset, size = pa
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(t.RETAINED)).scalar_one()
        rows = conn.execute(
            select(
                t.RETAINED.c.topic, func.length(t.RETAINED.c.payload).label("size"), t.RETAINED.c.qos, t.RETAINED.c.last_modified
            )
            .order_by(t.RETAINED.c.topic)
            .offset(offset)
            .limit(size)
        ).all()
    body: dict[str, Any] = {
        "retainedTopics": [
            {"topic": r.topic, "payloadSize": r.size, "qos": r.qos, "lastModifiedTime": r.last_modified} for r in rows
        ]
    }
    if offset + size < total:
        body["nextToken"] = _token(offset + size)
    return ok(body)


@router.get("/data/retainedMessage/{topic:path}")
async def get_retained(topic: str, request: Request):
    if denied := await authorize(request, "iotdata", "iot:GetRetainedMessage", _topic_arn(topic)):
        return denied
    with engine.connect() as conn:
        r = conn.execute(select(t.RETAINED).where(t.RETAINED.c.topic == topic)).first()
    if r is None:
        return error(404, "ResourceNotFoundException", f"No retained message exists for topic: {topic}")
    return ok(
        {"topic": r.topic, "payload": base64.b64encode(r.payload).decode(), "qos": r.qos, "lastModifiedTime": r.last_modified}
    )
