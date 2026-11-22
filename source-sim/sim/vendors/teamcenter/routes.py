"""Teamcenter Services over HTTP/JSON (JsonRestServices), as a Teamcenter 14 web tier answers them.

Every operation is `POST /teamcenter/tc/JsonRestServices/<Library>-<version>-<Port>/<operation>` with a JSON body
`{"header": {"state": {...}, "policy": {...}}, "body": {...input...}}`; the answer is the operation's response
structure tagged with ".QName", with a ServiceData (`plain`, `modelObjects`, `updated`, `partialErrors`).
A model object is `{"objectID", "uid", "className", "type", "props": {name: {"dbValues": [...], "uiValues": [...]}}}`.

    Core-2011-06-Session/login                    {"credentials": {"user", "password", "group", "role", "locale", "descrimator"}}
                                                  sets the JSESSIONID cookie
    Core-2006-03-Session/logout
    Core-2007-01-Session/getTCSessionInfo
    Query-2006-03-SavedQuery/getSavedQueries      -> {"queries": [{"query", "name", "description"}]}
    Query-2006-03-SavedQuery/describeSavedQueries {"queries": [ref]} -> {"fieldLists": [{"fields": [{"entryName", ...}]}]}
    Query-2008-06-SavedQuery/executeSavedQueries  {"input": [{"query", "entries", "values", "maxNumToReturn", ...}]}
                                                  -> {"arrayOfResults": [{"numOfObjects", "objectUIDS", "objects"}]}
    Core-2006-03-DataManagement/getProperties     {"objects": [ref], "attributes": [name]} -> ServiceData
    Core-2007-09-DataManagement/expandGRMRelationsForPrimary
                                                  {"primaryObjects": [ref], "pref": {"expItemRev", "returnRelations",
                                                   "info": [{"relationTypeName", "otherSideObjectTypes"}]}}
    Core-2007-01-DataManagement/getItemFromId     {"infos": [{"itemId", "revIds"}], "nRev", "pref"}
    Core-2010-09-DataManagement/setProperties     {"info": [{"object", "timestamp", "vecNameVal": [{"name", "values"}]}],
                                                   "options": []}

Failures are SOA exceptions in the body (InvalidUserException without a session, InvalidCredentialsException on a
bad login, ServiceException on a malformed request) or partialErrors in the ServiceData, as the Teamcenter web tier
returns them. Writes stamp last_mod_date with the simulated clock and record an event in the outbox (source "plm").
"""

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.teamcenter import auth
from sim.vendors.teamcenter.seed import POM, SAVED_QUERIES, iso

router = APIRouter(prefix="/teamcenter/tc")
SOURCE = "plm"
NS = "http://teamcenter.com/Schemas"
# properties a client may set (setProperties); everything else is read-only or system-maintained
WRITABLE = {
    "Nf0CompatCheck": {
        "nf0ConfigStatus",
        "nf0AltApproved",
        "nf0Compatibility",
        "nf0CompatibleItems",
        "nf0TargetUse",
        "object_desc",
    },
    "Item": {"object_desc", "object_name", "nf0Manufacturers"},
    "ItemRevision": {"object_desc", "object_name", "nf0BomRef", "nf0ConfigProps", "nf0Variants"},
    "Nf0AltApproval": {"nf0Approved", "nf0Reason"},
}
LOVS = {
    "nf0ConfigStatus": {"VERIFIED", "MISMATCH", "PENDING"},
    "nf0AltApproved": {"Y", "N"},
    "nf0Approved": {"Y", "N"},
    "nf0Compatibility": {"COMPATIBLE", "UNDER_REVIEW", "INCOMPATIBLE"},
}
ARRAYS = {"nf0CompatibleItems", "nf0ConfigProps", "nf0Variants", "nf0Manufacturers"}
REFS = {"items_tag", "revision_list", "release_status_list", "nf0DesignRevision", "primary_object", "secondary_object"}
DATES = {"last_mod_date", "creation_date", "date_released", "nf0EffectiveDate", "nf0CheckedAt"}


# ------------------------------------------------------------------ responses
def exception(kind: str, code: int, message: str, status: int = 200) -> JSONResponse:
    """A SOA exception as the JSON web tier serialises it."""
    return JSONResponse(
        {
            ".QName": f"{NS}/Soa/2006-03/Exceptions.{kind}",
            "code": code,
            "level": 3,
            "message": message,
            "messages": [{"code": code, "level": 3, "message": message}],
        },
        status_code=status,
    )


def not_logged_in() -> JSONResponse:
    return exception("InvalidUserException", 515117, "The user has not logged in, or the session has expired. Please log in.")


def _load(conn: Connection, uids: list[str] | None = None) -> dict[str, dict]:
    q = select(POM)
    if uids is not None:
        q = q.where(POM.c.uid.in_(uids))
    return {r.uid: {"uid": r.uid, "type": r.type, "class_name": r.class_name, "props": r.props} for r in conn.execute(q)}


def ref(o: dict) -> dict:
    return {"uid": o["uid"], "className": o["class_name"], "type": o["type"]}


def _ui_date(v: str) -> str:
    return datetime.fromisoformat(v).astimezone(UTC).strftime("%d-%b-%Y %H:%M")


def prop_value(name: str, value: Any, objs: dict[str, dict]) -> dict:
    vals = value if isinstance(value, list) else ([] if value is None else [value])
    if name in REFS:
        ui = [
            objs[u]["props"].get("object_string") or objs[u]["props"].get("object_name") or "" if u in objs else "" for u in vals
        ]
        return {"dbValues": vals, "uiValues": ui}
    if name in DATES:
        return {"dbValues": vals, "uiValues": [_ui_date(v) for v in vals]}
    return {"dbValues": [str(v) for v in vals], "uiValues": [str(v) for v in vals]}


def model_object(o: dict, attributes: list[str] | None, objs: dict[str, dict]) -> dict:
    out = {"objectID": o["uid"], "uid": o["uid"], "className": o["class_name"], "type": o["type"]}
    if attributes is not None:
        out["props"] = {a: prop_value(a, o["props"].get(a), objs) for a in attributes if a in o["props"] or a == "object_string"}
    return out


class ServiceData:
    def __init__(self, objs: dict[str, dict]):
        self.objs = objs
        self.plain: list[str] = []
        self.model: dict[str, dict] = {}
        self.updated: list[str] = []
        self.errors: list[dict] = []

    def add(self, o: dict, attributes: list[str] | None = None, plain: bool = True) -> None:
        mo = model_object(o, attributes, self.objs)
        cur = self.model.get(o["uid"])
        if cur and "props" in cur:
            mo["props"] = cur["props"] | mo.get("props", {})
        self.model[o["uid"]] = mo
        if plain and o["uid"] not in self.plain:
            self.plain.append(o["uid"])
        # referenced objects travel with the response (without properties), as the web tier sends them
        for a in attributes or []:
            if a in REFS:
                v = o["props"].get(a)
                for u in v if isinstance(v, list) else [v] if v else []:
                    if u in self.objs and u not in self.model:
                        self.model[u] = model_object(self.objs[u], None, self.objs)

    def error(self, uid: str | None, code: int, message: str, index: int = 0) -> None:
        e = {"clientIndex": index, "errorValues": [{"code": code, "level": 3, "message": message}]}
        if uid:
            e["uid"] = uid
        self.errors.append(e)

    def json(self) -> dict:
        out: dict = {".QName": f"{NS}/Soa/2006-03/Base.ServiceData"}
        if self.plain:
            out["plain"] = self.plain
        if self.model:
            out["modelObjects"] = self.model
        if self.updated:
            out["updated"] = self.updated
        if self.errors:
            out["partialErrors"] = self.errors
        return out


def _refs(items: Any) -> list[str]:
    if not isinstance(items, list):
        raise ValueError("expected a list of model object references")
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and isinstance(it.get("uid"), str):
            out.append(it["uid"])
        else:
            raise ValueError("a model object reference needs a uid")
    return out


# ------------------------------------------------------------------ saved queries
def _parse_tc_date(v: str) -> datetime:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(v.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError as e:
        raise ValueError(f"The date value '{v}' is not in the format dd-MMM-yyyy HH:mm") from e


def _wild(pattern: str) -> re.Pattern:
    return re.compile("^" + ".*".join(re.escape(p) for p in pattern.split("*")) + "$", re.I)


def _attr(o: dict, path: str, objs: dict[str, dict]) -> list[Any]:
    cur = [o]
    for part in path.split("."):
        nxt = []
        for c in cur:
            v = c["props"].get(part)
            for x in v if isinstance(v, list) else [v]:
                if x is None:
                    continue
                nxt.append(objs[x] if part in REFS and x in objs else x)
        cur = nxt
    return cur


def run_query(name: str, entries: list[str], values: list[str], objs: dict[str, dict]) -> list[dict]:
    desc, cls, defs = SAVED_QUERIES[name]
    by_entry = dict(defs)
    tests = []
    for e, v in zip(entries, values, strict=True):
        if e not in by_entry:
            raise KeyError(e)
        if v is None or str(v).strip() == "":
            continue
        attr = by_entry[e]
        if attr.endswith(">") or attr.endswith("<"):
            when, after = _parse_tc_date(str(v)), attr.endswith(">")
            a = attr[:-1]
            tests.append(
                lambda o, a=a, when=when, after=after: any(
                    (datetime.fromisoformat(x) > when) if after else (datetime.fromisoformat(x) < when) for x in _attr(o, a, objs)
                )
            )
        else:
            rx = _wild(str(v))
            tests.append(lambda o, a=attr, rx=rx: any(rx.match(str(x)) for x in _attr(o, a, objs)))
    hits = [o for o in objs.values() if o["type"] == cls and all(t(o) for t in tests)]
    key = "item_id" if cls in ("Item", "ItemRevision") else "object_name"
    return sorted(
        hits,
        key=lambda o: (str(o["props"].get(key) or o["props"].get("object_string")), o["props"].get("item_revision_id") or ""),
    )


# ------------------------------------------------------------------ operations
def op_login(body: dict, request: Request) -> JSONResponse:  # noqa: ARG001 - every operation takes (body, request)
    cred = body.get("credentials")
    if not isinstance(cred, dict):
        return exception("ServiceException", 214000, "The credentials input is missing.")
    sid = auth.login(
        cred.get("user") or "",
        cred.get("password") or "",
        cred.get("group") or "",
        cred.get("role") or "",
        cred.get("descrimator") or "",
    )
    if sid is None:
        return exception(
            "InvalidCredentialsException", 515143, "The login attempt failed: either the user ID or the password is invalid."
        )
    s = auth.SESSIONS[sid]
    resp = JSONResponse(
        {
            ".QName": f"{NS}/Core/2011-06/Session.LoginResponse",
            "serverInfo": {
                "DisplayVersion": "14.3.0.0 (tc14.3.0.0_20231024)",
                "HostName": "plm.northfield.example",
                "Locale": "en_US",
                "LogFile": f"/tmp/tcserver{sid[:6]}.syslog",  # noqa: S108 - a path the mock reports; nothing is written there
                "SiteLocale": "en_US",
                "TcServerID": f"tcserver{sid[:8]}",
                "UserID": s.user,
                "Version": "P14000.3.0.20231024.00",
            },
            "ServiceData": {".QName": f"{NS}/Soa/2006-03/Base.ServiceData"},
        }
    )
    resp.set_cookie("JSESSIONID", sid, httponly=True, path="/")
    return resp


def handle(service: str, operation: str, body: dict, user: str, sid: str) -> JSONResponse | dict:
    key = f"{service}/{operation}"
    with engine.begin() as conn:
        objs = _load(conn)
        if key == "Core-2006-03-Session/logout":
            auth.SESSIONS.pop(sid, None)
            return {".QName": f"{NS}/Soa/2006-03/Base.ServiceData"}
        if key == "Core-2007-01-Session/getTCSessionInfo":
            s = auth.SESSIONS[sid]
            return {
                ".QName": f"{NS}/Core/2007-01/Session.GetTCSessionInfoResponse",
                "serverVersion": "P14000.3.0",
                "transientVolRootDir": "/tmp/transientVolume",  # noqa: S108 - a path the mock reports; nothing is written there
                "isInV7Mode": False,
                "moduleNumber": 0,
                "bypass": False,
                "journaling": False,
                "appJournaling": False,
                "secJournaling": False,
                "admJournaling": False,
                "privileged": s.user == "infodba",
                "extraInfo": {
                    "TCServerHostName": "plm.northfield.example",
                    "UserID": s.user,
                    "GroupName": s.group,
                    "RoleName": s.role,
                    "SiteLocale": "en_US",
                    "syslogFile": "tcserver.syslog",
                },
                "ServiceData": {".QName": f"{NS}/Soa/2006-03/Base.ServiceData"},
            }
        if key == "Query-2006-03-SavedQuery/getSavedQueries":
            sd = ServiceData(objs)
            out = []
            for o in sorted((o for o in objs.values() if o["type"] == "ImanQuery"), key=lambda o: o["props"]["object_name"]):
                sd.add(o, ["object_name"], plain=False)
                out.append({"query": ref(o), "name": o["props"]["object_name"], "description": o["props"]["object_desc"]})
            return {".QName": f"{NS}/Query/2006-03/SavedQuery.GetSavedQueriesResponse", "queries": out, "serviceData": sd.json()}
        if key == "Query-2006-03-SavedQuery/describeSavedQueries":
            sd = ServiceData(objs)
            lists = []
            for i, u in enumerate(_refs(body.get("queries"))):
                q = objs.get(u)
                if not q or q["type"] != "ImanQuery":
                    sd.error(u, 214003, f"The object {u} is not a saved query.", i)
                    lists.append({"fields": []})
                    continue
                _, _, defs = SAVED_QUERIES[q["props"]["object_name"]]
                lists.append(
                    {
                        "fields": [
                            {
                                "entryName": e,
                                "attributeName": a.rstrip("<>"),
                                "attributeType": 2 if a.endswith(("<", ">")) else 8,
                                "logicalOperation": "AND",
                                "mathOperation": ">" if a.endswith(">") else "<" if a.endswith("<") else "=",
                                "value": "",
                                "lovValueType": 0,
                            }
                            for e, a in defs
                        ]
                    }
                )
            return {
                ".QName": f"{NS}/Query/2006-03/SavedQuery.DescribeSavedQueriesResponse",
                "fieldLists": lists,
                "serviceData": sd.json(),
            }
        if key == "Query-2008-06-SavedQuery/executeSavedQueries":
            sd = ServiceData(objs)
            results = []
            inputs = body.get("input")
            if not isinstance(inputs, list):
                return exception("ServiceException", 214000, "The input for executeSavedQueries is missing.")
            for i, inp in enumerate(inputs):
                u = (inp.get("query") or {}).get("uid") if isinstance(inp, dict) else None
                q = objs.get(u or "")
                if not q or q["type"] != "ImanQuery":
                    sd.error(u, 214003, f"The saved query {u} does not exist.", i)
                    results.append({"numOfObjects": 0, "objectUIDS": [], "objects": []})
                    continue
                entries, values = inp.get("entries") or [], inp.get("values") or []
                if len(entries) != len(values):
                    sd.error(u, 214004, "The number of query entries and values do not match.", i)
                    results.append({"numOfObjects": 0, "objectUIDS": [], "objects": []})
                    continue
                try:
                    hits = run_query(q["props"]["object_name"], entries, values, objs)
                except KeyError as e:
                    sd.error(u, 214005, f"The entry {e.args[0]} is not defined for the query {q['props']['object_name']}.", i)
                    hits = []
                except ValueError as e:
                    sd.error(u, 214006, str(e), i)
                    hits = []
                limit = int(inp.get("maxNumToReturn") or 0)
                if limit > 0:
                    hits = hits[:limit]
                results.append(
                    {"numOfObjects": len(hits), "objectUIDS": [h["uid"] for h in hits], "objects": [ref(h) for h in hits]}
                )
            return {
                ".QName": f"{NS}/Query/2008-06/SavedQuery.SavedQueriesResponse",
                "arrayOfResults": results,
                "serviceData": sd.json(),
            }
        if key == "Core-2006-03-DataManagement/getProperties":
            sd = ServiceData(objs)
            attrs = body.get("attributes")
            if not isinstance(attrs, list):
                return exception("ServiceException", 214000, "The attributes input is missing.")
            for i, u in enumerate(_refs(body.get("objects"))):
                o = objs.get(u)
                if o is None:
                    sd.error(u, 515001, f"The object with UID {u} does not exist or has been deleted.", i)
                    continue
                known = [a for a in attrs if a in o["props"] or a == "object_string"]
                for a in attrs:
                    if a not in known:
                        sd.error(u, 38015, f"The property {a} is not defined for the type {o['type']}.", i)
                sd.add(o, known)
            return sd.json()
        if key == "Core-2007-09-DataManagement/expandGRMRelationsForPrimary":
            sd = ServiceData(objs)
            pref = body.get("pref") or {}
            names = [x.get("relationTypeName") for x in pref.get("info") or [] if isinstance(x, dict)]
            ret_rel = bool(pref.get("returnRelations"))
            output = []
            for u in _refs(body.get("primaryObjects")):
                o = objs.get(u)
                if o is None:
                    sd.error(u, 515001, f"The object with UID {u} does not exist or has been deleted.")
                    continue
                data = []
                for rel in names or ["Nf0AltApproval"]:
                    rels = sorted(
                        (r for r in objs.values() if r["type"] == rel and r["props"].get("primary_object") == u),
                        key=lambda r: r["props"].get("object_string", ""),
                    )
                    ros = []
                    for r in rels:
                        other = objs[r["props"]["secondary_object"]]
                        sd.add(other, None, plain=False)
                        item = {"otherSideObject": ref(other)}
                        if ret_rel:
                            sd.add(r, None, plain=False)
                            item["relation"] = ref(r)
                        ros.append(item)
                    data.append({"relationName": rel, "relationshipObjects": ros})
                sd.add(o, None, plain=False)
                output.append({"inputObject": ref(o), "relationshipData": data})
            return {
                ".QName": f"{NS}/Core/2007-09/DataManagement.ExpandGRMRelationsResponse",
                "output": output,
                "serviceData": sd.json(),
            }
        if key == "Core-2007-01-DataManagement/getItemFromId":
            sd = ServiceData(objs)
            output = []
            for i, info in enumerate(body.get("infos") or []):
                iid = (info or {}).get("itemId")
                item = next((o for o in objs.values() if o["type"] == "Item" and o["props"].get("item_id") == iid), None)
                if item is None:
                    sd.error(None, 214101, f"No Item with the ID {iid} was found.", i)
                    continue
                revs = [objs[r] for r in item["props"]["revision_list"]]
                wanted = info.get("revIds") or []
                if wanted:
                    revs = [r for r in revs if r["props"]["item_revision_id"] in wanted]
                n = int(body.get("nRev") or 0)
                if not wanted and n > 0:
                    revs = revs[-n:]
                sd.add(item, ["item_id", "object_name"], plain=False)
                for r in revs:
                    sd.add(r, ["item_id", "item_revision_id", "object_name"], plain=False)
                output.append({"item": ref(item), "itemRevOutput": [{"itemRevision": ref(r), "datasetOutput": []} for r in revs]})
            return {
                ".QName": f"{NS}/Core/2007-01/DataManagement.GetItemFromIdResponse",
                "output": output,
                "serviceData": sd.json(),
            }
        if key == "Core-2010-09-DataManagement/setProperties":
            return set_properties(conn, body, objs, user)
    return JSONResponse({"error": f"The operation {key} is not available on this server."}, status_code=404)


def set_properties(conn: Connection, body: dict, objs: dict[str, dict], user: str) -> dict:
    sd = ServiceData(objs)
    now = clock.now(conn)
    for i, info in enumerate(body.get("info") or []):
        u = ((info or {}).get("object") or {}).get("uid")
        o = objs.get(u or "")
        if o is None:
            sd.error(u, 515001, f"The object with UID {u} does not exist or has been deleted.", i)
            continue
        if o["props"].get("release_status_list"):
            sd.error(u, 515034, f"The object {o['props'].get('object_string')} is released and cannot be modified.", i)
            continue
        ts = info.get("timestamp")
        if ts and ts != o["props"]["last_mod_date"]:  # optimistic locking: the client's copy is stale
            sd.error(u, 214016, f"The object {o['props'].get('object_string')} has been modified by another user; refresh it.", i)
            continue
        changes: dict[str, Any] = {}
        bad = False
        for nv in info.get("vecNameVal") or []:
            name, values = nv.get("name"), nv.get("values")
            if name not in o["props"] and name not in WRITABLE.get(o["type"], set()):
                sd.error(u, 38015, f"The property {name} is not defined for the type {o['type']}.", i)
                bad = True
                continue
            if name not in WRITABLE.get(o["type"], set()):
                sd.error(u, 515035, f"The property {name} of {o['type']} is not modifiable.", i)
                bad = True
                continue
            if not isinstance(values, list):
                sd.error(u, 214000, f"The values for {name} must be a list.", i)
                bad = True
                continue
            if name in LOVS and any(v not in LOVS[name] for v in values):
                sd.error(u, 54060, f"The value {values} is not a valid value of the list of values for {name}.", i)
                bad = True
                continue
            if name not in ARRAYS and len(values) > 1:
                sd.error(u, 214000, f"The property {name} takes a single value.", i)
                bad = True
                continue
            changes[name] = values if name in ARRAYS else (values[0] if values else None)
        if bad or not changes:
            continue
        props = o["props"] | changes | {"last_mod_date": iso(now), "last_mod_user": user}
        conn.execute(update(POM).where(POM.c.uid == u).values(props=props, last_mod_date=now))
        o["props"] = props
        sd.updated.append(u)
        sd.add(o, [*sorted(changes), "last_mod_date"], plain=False)
        events.emit(
            conn,
            SOURCE,
            f"com.siemens.teamcenter.{o['type']}.modified",
            o["props"].get("object_string") or u,
            {"uid": u, "type": o["type"], "changed": sorted(changes), "last_mod_date": props["last_mod_date"]},
            now,
        )
    return sd.json()


@router.post("/JsonRestServices/{service}/{operation}")
async def soa(service: str, operation: str, request: Request):
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("body", {}), dict):
        return exception("ServiceException", 214000, "The request is not a valid JSON service request (header and body).")
    body = payload.get("body") or {}
    if f"{service}/{operation}" in ("Core-2011-06-Session/login", "Core-2006-03-Session/login"):
        return op_login(body, request)
    sid = request.cookies.get("JSESSIONID") or ""
    user = auth.session_user(sid)
    if user is None:
        return not_logged_in()
    try:
        return handle(service, operation, body, user, sid)
    except ValueError as e:
        return exception("ServiceException", 214000, str(e))
