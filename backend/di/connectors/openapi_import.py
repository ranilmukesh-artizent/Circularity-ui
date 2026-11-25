"""An OpenAPI 3.x document to a connector spec (plan 9, P9-8.6; registry entry I-18; story: enabler, D 1.2 importer 1).

    import_openapi(doc, base_url=None) -> ImportResult(spec, resources, auth_methods, notes, unsupported)

Written in-house from the OpenAPI 3.1 sections "Paths Object", "Parameter Object", "Response Object" (with its
`headers`), "Components Object" (`schemas`, `parameters`, `responses`, `securitySchemes`), "Reference Object" (local
`#/...` pointers only), "Server Object" and "Security Scheme Object". The document is data the person gave; nothing in
it is fetched or run. It walks `paths` for GET operations that list records and emits what
di.connectors.configured can read, in that adapter's own vocabulary:
- `resources`: {name, path, id_field, data_selector} (+ `include_from_parent` for `/parents/{id}/children`). The records are
  the array at the 200 response's schema (a dotted `data_selector`, "$" for a top-level array); the id field is `id`,
  `<singular>_id`, the one `*_id` field, or a required one;
- `paging`: one per connection, inferred from the query parameters and the response: header_link (a `Link` response
  header), json_link (a next URL in the body), cursor, page_number, offset, else single_page;
- `auth_kind` and `auth_params` from `securitySchemes`: apiKey in a header -> api_key + its header, http bearer -> bearer,
  http basic -> basic, oauth2 clientCredentials -> oauth_cc + token_path. Never a value: a credential is entered when a
  connection is made.
Paths are relative to the connection's base URL: a path that starts with the base URL's own path is shortened.
Everything else (writes, XML-only or empty responses, other auth schemes, paging that differs from the first list's, a
required query parameter nobody can fill) goes to `unsupported` as "<operationId>: <reason>"; reads by id are noted.
Owns: the translation. Never does: fetch the document or any URL, save an entry, or hold a secret.
"""
# ruff: noqa: E501 - long lines in the vocabulary tables and the reasons

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

Json = dict[str, Any]
_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_PARAM = re.compile(r"\{([^}/]+)\}")
_LIMIT = ("limit", "per_page", "perpage", "page_size", "pagesize", "size", "count", "top", "max_results", "maxresults", "$top")
_OFFSET = ("offset", "skip", "start", "startat", "$skip")
_PAGE = ("page", "page_number", "pagenumber")
_CURSOR = ("cursor", "page_token", "pagetoken", "after", "starting_after", "next_token", "continuation", "continuation_token")
_RECORD_KEYS = ("items", "data", "results", "records", "value", "content", "rows", "list")
_LINK_KEYS = ("next_url", "nexturl", "next_page_url", "nextpageurl", "next_link", "nextlink", "@odata.nextlink", "next_href")
_CURSOR_KEYS = ("next_cursor", "nextcursor", "next_page_token", "nextpagetoken", "next_token", "nexttoken", "cursor")
_TOTAL_KEYS = ("total", "total_count", "totalcount", "total_results", "totalresults", "total_items")
_CONTAINERS = ("meta", "links", "_links", "pagination", "paging", "page")
_LINK_SAFE = ("single_page", "header_link", "json_link", "cursor", "header_cursor")  # types that end on a missing next


@dataclass
class ImportResult:
    spec: dict[str, Any]
    resources: list[dict[str, Any]] = field(default_factory=list)
    auth_methods: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


class _Skip(Exception):
    """An operation or scheme that cannot be imported; the message is the reason listed under `unsupported`."""


@dataclass
class _Op:
    op_id: str
    path: str
    rel: str  # the path relative to the connection's base URL
    params: list[Json]
    selector: str
    item: Json
    paging: Json
    parent: str | None = None  # the doc path of the parent list, for /parents/{id}/children


def import_openapi(doc: Mapping[str, Any], base_url: str | None = None) -> ImportResult:
    if not str(doc.get("openapi", "")).startswith("3."):
        raise ValueError("This is not an OpenAPI 3 document: it has no 'openapi: 3.x' field.")
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("The document has no paths to import.")
    out = ImportResult(spec={})
    server = _server(doc)
    base = base_url or server
    if server and base_url and urlparse(server).hostname != urlparse(base_url).hostname:
        out.notes.append(f"The document names the server {server}; the connection uses {base_url}.")
    elif server:
        out.notes.append(f"The document names the server {server}: use it, or a test copy, as the connection's base URL.")
    prefix = urlparse(base_url).path.rstrip("/") if base_url else ""
    lists, children = _operations(doc, paths, prefix, out)
    chosen = _choose_paging(lists, out)
    resources = _resources(lists, children, chosen, out)
    kind, params, methods = _auth(doc, base, out)
    out.auth_methods = methods
    out.resources = resources
    out.spec = {"resources": resources, "auth_kind": kind} | ({"auth_params": params} if params else {})
    if resources:
        out.spec["paging"] = chosen
    else:
        out.notes.append("No list operation could be imported.")
    return out


# ---------------------------------------------------------------- walking the paths
def _server(doc: Mapping[str, Any]) -> str:
    servers = doc.get("servers")
    first = servers[0] if isinstance(servers, list) and servers and isinstance(servers[0], dict) else {}
    url = str(first.get("url") or "")
    for name, v in (first.get("variables") or {}).items():
        url = url.replace("{" + str(name) + "}", str((v or {}).get("default", "")))
    return url.rstrip("/")


def _operations(doc: Mapping[str, Any], paths: Json, prefix: str, out: ImportResult) -> tuple[list[_Op], list[_Op]]:
    lists: list[_Op] = []
    children: list[_Op] = []
    by_id = 0
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in (m for m in item if m in _METHODS):
            op = item[method]
            op_id = (
                str(op.get("operationId") or f"{method.upper()} {path}") if isinstance(op, dict) else f"{method.upper()} {path}"
            )
            if method != "get" or not isinstance(op, dict):
                out.unsupported.append(f"{op_id}: {method.upper()} {path} is not a read, so it is not imported")
                continue
            try:
                found = _list_operation(doc, str(path), item, op, op_id, prefix)
            except _Skip as e:
                out.unsupported.append(f"{op_id}: {e}")
                continue
            if found is None:
                by_id += 1
            elif found.parent:
                children.append(found)
            else:
                lists.append(found)
    if by_id:
        out.notes.append(f"{by_id} read-by-id operation(s) were skipped: a connection reads whole lists.")
    return lists, children


def _list_operation(doc: Mapping[str, Any], path: str, item: Json, op: Json, op_id: str, prefix: str) -> _Op | None:
    """The list this GET reads, None for a read by id, _Skip (with the reason) when it cannot be imported."""
    tail = _PARAM.findall(path)
    if tail and path.rstrip("/").endswith("}"):
        return None
    params = [_resolve(doc, p) for p in [*(item.get("parameters") or []), *(op.get("parameters") or [])]]
    schema, headers = _response(doc, op)
    records = _records(doc, schema)
    if records is None:
        raise _Skip(f"GET {path} does not return a list of records")
    selector, item_schema = records
    for p in params:
        if p.get("required") and p.get("in") == "query" and not _known_query(str(p.get("name"))):
            raise _Skip(f"GET {path} needs the query parameter {p.get('name')}, which a connection cannot fill")
    parent = None
    if len(tail) > 1:
        raise _Skip(f"GET {path} has more than one path parameter")
    if tail:
        parent = path[: path.index("{")].rstrip("/")
    rel = path[len(prefix) :] if prefix and path.startswith(prefix + "/") else path
    paging = _paging(params, headers, schema and _resolve(doc, schema), doc)
    return _Op(op_id, path, rel, params, selector or "$", item_schema, paging, parent)


def _response(doc: Mapping[str, Any], op: Json) -> tuple[Json, Json]:
    responses = op.get("responses") or {}
    keys = [k for k in responses if str(k) == "200"] or sorted(str(k) for k in responses if str(k).startswith("2"))
    if not keys:
        raise _Skip("it has no 2xx response")
    r = _resolve(doc, responses.get(keys[0], responses.get(str(keys[0]))) or {})
    content = r.get("content")
    if not content:
        raise _Skip("its response has no body described")
    media = next((m for m in content if m == "application/json" or str(m).endswith("+json")), None)
    if media is None:
        raise _Skip(f"its response is {', '.join(str(m) for m in content)}; only JSON is read")
    return content[media].get("schema") or {}, {str(k).lower(): v for k, v in (r.get("headers") or {}).items()}


def _known_query(name: str) -> bool:
    return name.lower() in (*_LIMIT, *_OFFSET, *_PAGE, *_CURSOR)


# ---------------------------------------------------------------- schemas
def _resolve(doc: Mapping[str, Any], node: Any, depth: int = 0) -> Json:
    """A schema, parameter or response with its local $ref followed and allOf merged (properties and required)."""
    if not isinstance(node, dict):
        return {}
    if "$ref" in node:
        ref = str(node["$ref"])
        if not ref.startswith("#/") or depth > 20:
            raise _Skip(f"it refers to {ref}, which is not a local reference")
        target: Any = doc
        for step in ref[2:].split("/"):
            target = target.get(step.replace("~1", "/").replace("~0", "~")) if isinstance(target, dict) else None
        return _resolve(doc, target, depth + 1)
    if "allOf" in node:
        merged: Json = {k: v for k, v in node.items() if k != "allOf"}
        props: Json = dict(node.get("properties") or {})
        required: list[Any] = list(node.get("required") or [])
        for part in node["allOf"]:
            p = _resolve(doc, part, depth + 1)
            props |= p.get("properties") or {}
            required += p.get("required") or []
        return merged | {"type": "object", "properties": props, "required": required}
    return node


def _is(schema: Json, kind: str) -> bool:
    t = schema.get("type")
    return t == kind or (isinstance(t, list) and kind in t)


def _records(doc: Mapping[str, Any], schema: Json) -> tuple[str, Json] | None:
    """(data_selector, one record's schema) of the array in a response schema; an empty schema is read as {"items": [...]}."""
    s = _resolve(doc, schema)
    if not s:
        return "items", {}
    if _is(s, "array") or ("items" in s and not s.get("properties")):
        return "$", _resolve(doc, s.get("items"))
    found = _array_property(doc, s)
    if found:
        return found
    for name, sub in (s.get("properties") or {}).items():  # one level in: {"data": {"items": [...]}}
        inner = _resolve(doc, sub)
        if _is(inner, "object") and (nested := _array_property(doc, inner)):
            return f"{name}.{nested[0]}", nested[1]
    return None


def _array_property(doc: Mapping[str, Any], s: Json) -> tuple[str, Json] | None:
    props = {str(k): _resolve(doc, v) for k, v in (s.get("properties") or {}).items()}
    arrays = [k for k, v in props.items() if _is(v, "array")]
    pick = next((k for k in _RECORD_KEYS if k in arrays), arrays[0] if arrays else None)
    return (pick, _resolve(doc, props[pick].get("items"))) if pick else None


def _id_field(item: Json, name: str) -> str | None:
    props = [str(k) for k in (item.get("properties") or {})]
    required = [str(k) for k in item.get("required") or []]
    stem = name.rstrip("s").lower()
    idlike = [k for k in props if re.search(r"(_id|Id|ID)$", k)]
    for k in props:
        if k == "id" or k.lower() in (f"{stem}_id", f"{stem}id"):
            return k
    if len(idlike) == 1:
        return idlike[0]
    if ids_required := [k for k in required if k in idlike]:
        return ids_required[0]
    return required[0] if len(required) == 1 else None


# ---------------------------------------------------------------- paging
def _query(params: list[Json], names: tuple[str, ...]) -> str | None:
    return next((str(p["name"]) for p in params if p.get("in") == "query" and str(p.get("name", "")).lower() in names), None)


def _body_keys(doc: Mapping[str, Any], schema: Json) -> Json:
    """Where the body says what comes next: a next URL, a cursor, a next number and a total (dotted paths)."""
    found: Json = {}
    props = {str(k): _resolve(doc, v) for k, v in (schema.get("properties") or {}).items()}
    scopes: list[tuple[str, Json]] = [("", props)]
    for name, sub in props.items():
        if name.lower() in _CONTAINERS and _is(sub, "object"):
            scopes.append((name + ".", {str(k): _resolve(doc, v) for k, v in (sub.get("properties") or {}).items()}))
    for scope, members in scopes:
        for name, sub in members.items():
            low, path = name.lower(), scope + name
            uri = str(sub.get("format", "")).startswith("uri")
            if (
                low in _LINK_KEYS
                or (uri and "next" in low)
                or (low == "next" and scope.rstrip(".").lower() in ("links", "_links"))
            ):
                found.setdefault("link", path)
            elif low in _CURSOR_KEYS:
                found.setdefault("cursor", path)
            elif low == "next" and _is(sub, "string"):
                found.setdefault("bare", path)
            elif low.startswith("next") and not scope and (_is(sub, "integer") or _is(sub, "number")):
                found.setdefault("number", name)
            elif low in _TOTAL_KEYS and not scope:
                found.setdefault("total", name)
    return found


def _paging(params: list[Json], headers: Json, schema: Json, doc: Mapping[str, Any]) -> Json:
    body = _body_keys(doc, schema) if schema else {}
    limit, offset, page, cursor = (_query(params, n) for n in (_LIMIT, _OFFSET, _PAGE, _CURSOR))
    size = {"limit_param": limit} if limit else {}
    cap = next((p.get("schema", {}).get("maximum") for p in params if p.get("name") == limit), None)
    more = {"max_size": cap} if isinstance(cap, int) else {}
    if "link" in headers:
        return {"type": "header_link"} | size | more
    if "link" in body:
        return {"type": "json_link", "next_url_path": body["link"]} | size | more
    if cursor:
        return (
            {"type": "cursor", "cursor_param": cursor}
            | size
            | more
            | ({"cursor_path": body["cursor"]} if "cursor" in body else {})
        )
    if page:
        return {"type": "page_number", "page_param": page} | ({"size_param": limit} if limit else {}) | more | _numbers(body)
    if offset:
        return {"type": "offset", "offset_param": offset} | size | more | _numbers(body)
    if "bare" in body:
        return {"type": "json_link", "next_url_path": body["bare"]} | size | more
    return {"type": "single_page"}


def _numbers(body: Json) -> Json:
    return ({"next_key": body["number"]} if "number" in body else {}) | ({"total_key": body["total"]} if "total" in body else {})


def _choose_paging(lists: list[_Op], out: ImportResult) -> Json:
    """The connection's paging: the first list that has some. The others must read the same way, or are not imported."""
    chosen = next((o.paging for o in lists if o.paging["type"] != "single_page"), {"type": "single_page"})
    keep: list[_Op] = []
    for o in lists:
        if _compatible(o.paging, chosen):
            keep.append(o)
        else:
            out.unsupported.append(f"{o.op_id}: its paging ({o.paging['type']}) differs from the connection's ({chosen['type']})")
    lists[:] = keep
    return chosen


def _compatible(paging: Json, chosen: Json) -> bool:
    if paging["type"] == "single_page":
        return chosen["type"] in _LINK_SAFE
    keys = (
        "type",
        "limit_param",
        "offset_param",
        "page_param",
        "size_param",
        "cursor_param",
        "cursor_path",
        "next_url_path",
        "next_key",
        "total_key",
    )
    return all(paging.get(k) == chosen.get(k) for k in keys)


# ---------------------------------------------------------------- resources
def _resources(lists: list[_Op], children: list[_Op], chosen: Json, out: ImportResult) -> list[dict[str, Any]]:
    names: dict[str, str] = {}  # doc path -> resource name
    taken: set[str] = set()
    resources: list[dict[str, Any]] = []
    for o in lists:
        name = _name(o.path, taken)
        names[o.path] = name
        resources.append(_resource(o, name, o.rel))
        if "id_field" not in resources[-1]:
            out.notes.append(f"{name}: no id field was found; name it before releasing.")
    byname = {r["name"]: r for r in resources}
    for c in children:
        parent = names.get(c.parent or "")
        if parent is None or "id_field" not in byname[parent]:
            out.unsupported.append(f"{c.op_id}: its parent list {c.parent} is not imported, or has no id field")
            continue
        if not _compatible(c.paging, chosen):
            out.unsupported.append(f"{c.op_id}: its paging ({c.paging['type']}) differs from the connection's ({chosen['type']})")
            continue
        name = _name(c.path, taken)
        pid = byname[parent]["id_field"]
        rel = _PARAM.sub("{resources." + parent + "." + pid + "}", c.rel)
        resources.append(_resource(c, name, rel) | {"include_from_parent": [pid]})
        if "id_field" not in resources[-1]:
            out.notes.append(f"{name}: no id field was found; name it before releasing.")
    return resources


def _resource(o: _Op, name: str, rel: str) -> dict[str, Any]:
    id_field = _id_field(o.item, name)
    return {"name": name, "path": rel} | ({"id_field": id_field} if id_field else {}) | {"data_selector": o.selector}


def _name(path: str, taken: set[str]) -> str:
    segments = [re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") for s in path.split("/") if s and not s.startswith("{")]
    segments = [s for s in segments if s] or ["resource"]
    name = segments[-1]
    if name in taken:
        name = "_".join(segments)
    base, n = name, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    taken.add(name)
    return name


# ---------------------------------------------------------------- authentication
def _auth(doc: Mapping[str, Any], base: str, out: ImportResult) -> tuple[str, dict[str, Any], list[str]]:
    schemes = (doc.get("components") or {}).get("securitySchemes") or {}
    wanted = [str(n) for req in doc.get("security") or [] if isinstance(req, dict) for n in req] or [str(n) for n in schemes]
    found: list[tuple[str, dict[str, Any]]] = []
    for name in dict.fromkeys(wanted):
        try:
            found.append(_scheme(doc, schemes.get(name), base))
        except _Skip as e:
            out.unsupported.append(f"securityScheme {name}: {e}")
    kinds = list(dict.fromkeys(k for k, _ in found))
    return (found[0][0], found[0][1], kinds) if found else ("none", {}, ["none"])


def _scheme(doc: Mapping[str, Any], scheme: Any, base: str) -> tuple[str, dict[str, Any]]:
    s = _resolve(doc, scheme)
    kind, http = s.get("type"), str(s.get("scheme", "")).lower()
    if kind == "apiKey" and s.get("in") == "header" and s.get("name"):
        return "api_key", {"header": str(s["name"])}
    if kind == "http" and http in ("bearer", "basic"):
        return http, {}
    flow = (s.get("flows") or {}).get("clientCredentials")
    if kind == "oauth2" and isinstance(flow, dict) and flow.get("tokenUrl"):
        url = urlparse(str(flow["tokenUrl"]))
        if url.hostname and base and url.hostname != urlparse(base).hostname:
            raise _Skip(f"its token endpoint is on {url.hostname}, not the connection's host")
        path = (
            url.path[len(urlparse(base).path.rstrip("/")) :]
            if base and url.path.startswith(urlparse(base).path.rstrip("/") + "/")
            else url.path
        )
        return "oauth_cc", {"token_path": path}
    raise _Skip(f"{kind} {s.get('scheme') or s.get('in') or ''}".strip() + " sign-in is not supported")
