"""The Connection Fabric's source lifecycle (B17): save or create a connection, connect one from the catalogue, delete,
reconnect, rotate credentials, pause, resume, disconnect, and test a connection.

Ports of the demo's handlers (index.html: defAction('source.update' | 'source.reconnect' | 'credentials.rotate' |
'source.delete'), and the near-real flows ACT.frSrcPause, frDiscOk, frCxDone, frCxFinish, frTestRun, sdTest), with the
demo's rules and texts. What a person changes about a source is kept by di.connectors.lifecycle (the workspace
collection "source_config" over the demo's reference record); the connector state (live, paused, disconnected,
unavailable, manual) is source_system.status, which the scheduler and the sync runner obey.

**Actions the catalog does not name.** The demo ran pause, resume, disconnect and the connection test in the browser
without an action. Here every write goes through the pipeline, so they are declared beside the catalog's 76 with the
other source actions' permission (manageIntegrations; the demo adds them to PERM_ACTS.manageIntegrations):
    source.pause        act     scheduled syncs stop; queued syncs are dropped
    source.resume       act     back to the status it had (live, stale, manual ...); the scheduler picks it up again
    source.disconnect   commit  Circularity stops reading; settings are kept; `confirm` must be the vendor's name
    source.test         read    the five checks (DNS, TLS, Auth, Permissions, Sample read), or the drawer's one-line
                                test of a draft (`draft`), probed against the source's connection (di.connectors.probe)
Reconnecting after a disconnect is source.reconnect, as in the demo. Connecting from the catalogue is source.update with
mode "catalog" (d = {catalog, auth, scopes}, maps = the accepted rows): it creates the source, as mode "new" does.
Mode "mcp" (plan 8 MVP-11.7; d = {url, tool, arguments, resource_key, id_field?}) reads an existing source through an
MCP server from then on (di.connectors.mcp_client), with its field mapping kept.

**Sources without a Python adapter** (plan 6 A3). A source connected from the catalogue gets a connection from its
template (di.connectors.catalog: source-sim's synthetic mock of that system) and a stored credential; one set up by
hand is read from the endpoint entered, its read operations ("GET /path") being its resources. Both are read by the
configured adapter (di.connectors.configured), and their first sync is queued: it really reads. A catalogue system's
first mapping version is its template's rows that the person accepted (the read mapping.catalogSuggest offers them
with a sample read from the system; the demo's mapping.suggest, a draft on a source, is another action), on keys of
their own; a system with no rows keeps its records raw. The connection test
probes every step for real (di.connectors.probe, plan 6 A5).

**Not ported.** The demo's Source Map activity lines (smLogAdd; the map's activity is the real sync runs), the draft
ingest workflow the demo adds for a new source (wfAddForSource; Workflow Studio's list is its own), and the connection
test's `source.tested` event (a read action changes nothing).
"""

import copy
import math
import re
import socket
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from di.connectors import catalog, connection, extra, lifecycle, mapping, mcp_client, registry, secrets, sync
from di.connectors.probe import probe
from di.connectors.registry import ADAPTERS
from di.core import golden, policy
from di.repositories import mapping_decisions
from di.repositories.common import fmt_dy, hash_id, iso, ms
from di.repositories.constants import MAPPINGS, SRC_TYPES
from di.repositories.fabric import SCREEN_STATUS, type_of
from di.repositories.reference import lists
from di.repositories.workflows import all_workflows, wf_using
from di.services.actions.decisions import push_event
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement, mark_destructive

_L = lists()
CONN_METHODS: dict[str, dict] = _L["CONN_METHODS"]
FR_AUTH: list[list[str]] = _L["FR_AUTH"]
CATALOG: dict[str, dict] = {c["id"]: c for c in _L["CATALOG"]}
REF: dict[str, dict] = {s["id"]: s for s in golden.load("sources")["sources"]}
SRC_SEED: dict[str, dict] = {}
for _s in REF.values():  # the demo's SRC_SEED: what a new source of a type inherits from the first one of that type
    SRC_SEED.setdefault(_s["type"], {"inputs": _s["inputs"], "authority": list(_s["authority"]), "step": list(_s["step"])})
DESC = (
    "name", "short", "cat", "vendor", "ver", "env", "url", "mode", "auth", "rw", "inputs", "read", "write", "step",
    "authority", "method", "cfg", "cfgVer", "credAt", "credDays", "audit", "owner", "interval", "updatedBy",
    "frConnectedAt", "records",
)  # fmt: skip
ACCEPTED = "Accepted from the agent’s suggestion"


# ---------------------------------------------------------------- actions the demo's catalog does not name
def _declare(action_id: str, title: str, verb: str, desc: str, risk: Any, inp: dict[str, dict[str, Any]], perm: Any) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_SRC = {"source_id": {"req": True, "t": "string"}}
_MGR = "manageIntegrations"
_declare(
    "source.pause", "Pause a source", "pause sources", "Stop a source's scheduled syncs until it is resumed.", "act", _SRC, _MGR
)
_declare("source.resume", "Resume a source", "resume sources", "Restart a paused source's scheduled syncs.", "act", _SRC, _MGR)
_declare(
    "source.disconnect", "Disconnect a source", "disconnect sources",
    "Stop reading from a source; its settings are kept so it can be reconnected.", "commit",
    _SRC | {"confirm": {"req": True, "t": "string"}}, _MGR,
)  # fmt: skip
_declare(
    "source.test", "Test a connection", "test connections",
    "Probe a source's connection: DNS, TLS, authentication, permissions and a sample read. Changes nothing.", "read",
    {"source_id": {"req": False, "t": "string"}, "reauth": {"req": False, "t": "boolean"},
     "auth": {"req": False, "t": "string"}, "draft": {"req": False, "t": "object"},
     "secret": {"req": False, "t": "string"}}, None,
)  # fmt: skip
_declare(
    "source.sandboxKey", "Sandbox key of a catalogue system", "read sandbox keys",
    "The synthetic key the simulated system of a catalogue entry accepts (the Connect dialog prefills it). "
    "Changes nothing.", "read", {"catalog_id": {"req": True, "t": "string"}}, _MGR,
)  # fmt: skip
# the secret, when a caller sends it, is only checked (never stored); reauth: the Re-authenticate dialog's renewal
ACTIONS["credentials.rotate"].input |= {"secret": {"req": False, "t": "string"}, "reauth": {"req": False, "t": "boolean"}}
# plan 6 A2: the connection itself (base_url, auth_kind, auth_params, resources, paging) and the secret to sign in with;
# the secret is stored encrypted (di.connectors.secrets) and, like every input named secret, never journaled
ACTIONS["source.update"].input |= {"conn": {"req": False, "t": "object"}, "secret": {"req": False, "t": "string"}}
# plan 8 MVP-1.4: the org unit the source belongs to (null: shared by every org); sent only to set it
ACTIONS["source.update"].input |= {"org_unit_id": {"req": False, "t": "string"}}


# ---------------------------------------------------------------- the source as the screens show it
def _now_ms(ctx: CallContext) -> int:
    return ms(ctx.now.isoformat())


def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


def _current(ctx: CallContext, sid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The source (the demo's reference overlaid with what was saved here, the connector's status) and its saved item.
    Refuses a source that does not exist or is deleted, with the demo's srcGuard text."""
    s = ctx.session
    row = s.execute(text("SELECT * FROM source_system WHERE id = :i"), {"i": sid}).mappings().first()
    if row is None or lifecycle.is_deleted(s, sid):
        raise ActionError("not_found", f"No source {sid}.")
    cfg = lifecycle.config(s, sid)
    ref = REF.get(sid) or {}
    t = type_of(row["type"])
    cur: dict[str, Any] = {
        "name": t["label"], "short": t["short"], "cat": t.get("cat", "internal"), "ver": "", "env": "Production", "url": "",
        "mode": "", "auth": "", "rw": "Read", "inputs": "", "read": [], "write": [], "step": [], "authority": [],
        "method": "api", "cfg": {}, "cfgVer": "1.0", "credAt": None, "credDays": None, "audit": [],
    }  # fmt: skip
    cur |= {k: copy.deepcopy(ref[k]) for k in DESC if k in ref}
    cur |= {"vendor": row["vendor"], "interval": row["interval_min"], "owner": row["owner"] or ref.get("owner") or ""}
    cur |= {k: copy.deepcopy(v) for k, v in cfg.items() if k in DESC}
    st = row["status"]
    shown = (cfg.get("prev") or "live") if st == "paused" else st  # a paused source shows the status it had
    cur |= {"id": sid, "type": row["type"], "db": st, "status": SCREEN_STATUS.get(shown, shown)}
    cur["maps"] = copy.deepcopy(cfg["maps"]) if "maps" in cfg else copy.deepcopy(MAPPINGS.get(sid, []))
    return cur, cfg


def _bump(ctx: CallContext, cur: dict, cfg: dict, change: str) -> str:
    """A new configuration version (1.5 -> 1.6) with its audit entry at the top, as the demo's handlers write it."""
    a, b = [*str(cur.get("cfgVer") or "1.0").split("."), "0"][:2]
    ver = f"{a}.{int(b) + 1}"
    entry = {"ver": ver, "who": _by(ctx), "ts": _now_ms(ctx), "change": change, "prep": ctx.preparer}
    cfg["cfgVer"], cfg["audit"] = ver, [entry, *(cur.get("audit") or [])]
    cur["cfgVer"], cur["audit"] = cfg["cfgVer"], cfg["audit"]
    return ver


def _event(ctx: CallContext, cur: dict, type_: str, ack: str, note: str) -> None:
    """The demo's srcEvent: an inbound entry in the event stream, about the source."""
    key = "cfg-" + hash_id(cur["id"] + type_ + str(_now_ms(ctx)) + str(ctx.idem_key or "")).lower()[:6]
    push_event(
        ctx,
        {"dir": "in", "type": type_, "caseId": None, "decisionId": None, "approval": None, "ver": None,
         "dest": f"{cur['name']} · {cur['vendor']}", "ack": ack, "key": key, "note": note, "ts": iso(_now_ms(ctx)),
         "sim": True},
        None,
    )  # fmt: skip


# ---------------------------------------------------------------- source.update
def _build_url(d: dict) -> str:
    """The demo's buildUrl."""
    c = d.get("cfg") or {}
    m = d.get("method")
    if m == "jdbc":
        drv = re.sub(r"\s+", "", str(c.get("driver") or "").lower())
        return f"jdbc:{drv}://{c.get('host')}:{c.get('port')}/{c.get('database')}"
    if m == "delta":
        return str(c.get("endpoint") or "")
    if m == "file":
        return str(c.get("path") or "") if c.get("delivery") == "SFTP drop" else ""
    return str(d.get("url") or "").strip()


def method_mode(m: str, iv: int) -> str:
    """The demo's methodMode."""
    if m == "native":
        return f"Native connector · Polling · {iv} min"
    if m == "jdbc":
        return f"JDBC · Polling · {iv} min"
    if m == "api":
        return f"API extractor · Polling · {iv} min" if iv else "API extractor · API + events"
    if m == "event":
        return "Event API · Events"
    if m == "delta":
        return "Delta Sharing · API read (live)"
    return "Flat file · CSV import"


def cfg_defaults(m: str) -> dict[str, Any]:
    return {f["k"]: f["def"] for f in CONN_METHODS[m]["fields"]}


def _js_str(v: Any) -> str:
    """String(v) as JavaScript writes it (the demo compares fields that way)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list):
        return ",".join(_js_str(x) for x in v)
    return str(v)


AUTH_KIND_OF = (  # the auth label a person picked → how the connector signs in (first match wins)
    ("client credentials", "oauth_cc"), ("oauth", "oauth_cc"), ("service principal", "oauth_cc"), ("api key", "api_key"),
    ("bearer", "bearer"), ("password", "basic"), ("basic", "basic"),
)  # fmt: skip


def auth_kind_of(label: str) -> str:
    low = (label or "").lower()
    return next((k for word, k in AUTH_KIND_OF if word in low), "none")


def _resources_of(read: list[str]) -> list[dict]:
    """A hand-made source's read operations ("GET /records") as configured resources (name, path, id_field id)."""
    out = []
    for op in read:
        m = re.match(r"^(?:GET\s+)?(/\S*)$", op.strip(), re.I)
        if m and "{" not in m.group(1):
            path = m.group(1).split("?")[0]
            out.append({"name": path.strip("/").replace("/", "_") or "records", "path": path, "id_field": "id"})
    return out


def _is_http(url: str) -> bool:
    return bool(re.match(r"^https?://[^/\s]+", url or ""))


def _save_connection(ctx: CallContext, sid: str, i: dict, new_url: str, url_changed: bool, made: dict | None) -> list[str]:
    """source.update's connection part (plan 6 A2): the URL the connector calls, how it signs in, and the secret.

    A demo source keeps source-sim as its URL while the endpoint shown is the demo's (its reference `url`); a person who
    enters another http(s) endpoint points the connector there, and entering the demo's endpoint again puts it back on
    source-sim. A source made here (`made`: its auth label and read operations) is read from the endpoint entered.
    `conn` (from the API) sets the connection's fields directly. Returns what changed, for the audit."""
    s, ch = ctx.session, []
    raw_conn = i.get("conn")
    conn_in: dict = raw_conn if isinstance(raw_conn, dict) else {}
    if any(w in k.lower() for k in (conn_in.get("auth_params") or {}) for w in ("secret", "password", "token")):
        raise ActionError("validation_error", "Send the secret as `secret`; it is stored encrypted, never in the settings.")
    fields = {k: conn_in[k] for k in ("base_url", "protocol", "auth_kind", "auth_params", "resources", "paging") if k in conn_in}
    if "auth_kind" in fields and fields["auth_kind"] not in connection.AUTH_KINDS:
        raise ActionError("validation_error", f"No authentication kind {fields['auth_kind']}.")
    if "base_url" not in fields and url_changed:
        if sid in ADAPTERS and new_url == (REF.get(sid) or {}).get("url"):
            connection.restore_default(s, sid)
        elif _is_http(new_url):
            fields["base_url"] = new_url
    if made is not None:  # a new source: a stale row left by an earlier one of this id is replaced
        if "base_url" not in fields and _is_http(new_url):
            fields["base_url"] = new_url
        fields.setdefault("auth_kind", auth_kind_of(made["auth"]))
        fields.setdefault("resources", _resources_of(made["read"]))
        fields.setdefault("paging", {"style": "offset"})
    if fields and (fields.get("base_url") or connection.connection_for(s, sid) is not None):
        try:
            connection.save_connection(s, sid, _by(ctx), **fields)
        except ValueError as e:
            raise ActionError("validation_error", str(e)) from e
    if conn_in:  # an endpoint change is already in the audit as "endpoint"
        ch.append("connection settings")
    if i.get("secret"):
        if len(str(i["secret"])) < 8:
            raise ActionError("validation_error", "Enter at least 8 characters.")
        secrets.put_secret(s, sid, "auth", str(i["secret"]), 180, _by(ctx), ctx.now)
        ch.append("credential")
    return ch


def _interval(d: dict, cm: dict) -> int:
    if not cm.get("sched"):
        return 0
    try:
        v = float(d.get("interval") or 0)
    except (TypeError, ValueError):
        v = 0
    return int(v) if math.isfinite(v) else 0


def _check_org(i: dict[str, Any], ctx: CallContext) -> None:
    """plan 8 MVP-1.4: `org_unit_id`, when sent, is an org unit the actor may see (Admin and unscoped roles: any)."""
    org = i.get("org_unit_id")
    if org is None:
        return
    if ctx.session.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": org}).first() is None:
        raise ActionError("validation_error", f"No org unit {org}.")
    a = ctx.actor.account
    if a is not None and policy.policy(a).get("tenantScoped") and not policy.tenant_ok(a, org, ctx.actor.ctx):
        raise ActionError("tenant_boundary", f"{org} is an org unit you cannot see. Request tenant access first.")


def _bind_org(ctx: CallContext, sid: str, i: dict[str, Any]) -> list[str]:
    """Bind the source to the org unit sent (null: shared by every org); what changed, for the audit."""
    if "org_unit_id" not in i:
        return []
    r = ctx.session.execute(
        text(
            "UPDATE source_system SET org_unit_id = CAST(:o AS text) "
            "WHERE id = :i AND org_unit_id IS DISTINCT FROM CAST(:o AS text) RETURNING id"
        ),
        {"o": i["org_unit_id"], "i": sid},
    )
    return ["org unit"] if r.first() else []


def _bound(ctx: CallContext, out: dict[str, Any], i: dict[str, Any]) -> dict[str, Any]:
    _bind_org(ctx, out["source_id"], i)
    return out


def _connect_mcp(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """plan 8 MVP-11.7: an existing source is read through an MCP server from now on (di.connectors.mcp_client).
    d = {url, tool, arguments?, resource_key, id_field?}; its field mapping is kept. Its first sync is queued."""
    d, sid = i["d"], str(i.get("id") or "")
    cur, _ = _current(ctx, sid)
    url, tool, key = str(d.get("url") or ""), str(d.get("tool") or "").strip(), str(d.get("resource_key") or "").strip()
    args = d.get("arguments") if d.get("arguments") is not None else {}
    if not _is_http(url):
        raise ActionError("validation_error", "Enter the MCP server's http(s) URL.")
    if not tool or not key:
        raise ActionError("validation_error", "Name the tool to call and the resource key.")
    if not isinstance(args, dict):
        raise ActionError("validation_error", '"arguments" must be an object.')
    res = mcp_client.resource(tool, args, key, str(d["id_field"]) if d.get("id_field") else None)
    s = ctx.session
    connection.save_connection(
        s, sid, _by(ctx), base_url=url, protocol=mcp_client.PROTOCOL, auth_kind="none", auth_params={}, paging={},
        resources=[res],
    )  # fmt: skip
    s.execute(text("UPDATE source_system SET status = 'live', updated_at = now() WHERE id = :i AND status <> 'live'"), {"i": sid})
    sync.enqueue_sync(s, sid, "initial", full=True)
    _event(ctx, cur, "connector.updated", "acknowledged", f"Reads {tool} on the MCP server {url}")
    return {"source_id": sid, "protocol": mcp_client.PROTOCOL}


@implement("source.update")
def source_update(i: dict[str, Any], ctx: CallContext):
    mode = i["mode"]
    _check_org(i, ctx)
    if mode == "catalog":
        return _bound(ctx, _connect_catalog(i, ctx), i)
    if mode == "mcp":  # plan 8 MVP-11.7
        return _bound(ctx, _connect_mcp(i, ctx), i)
    if mode not in ("new", "edit"):
        raise ActionError("validation_error", '"mode" must be new, edit or catalog.')
    d = i["d"]
    cm = CONN_METHODS.get(d.get("method") or "")
    if cm is None:
        raise ActionError("validation_error", f"No connection method {d.get('method')}.")
    if not str(d.get("name") or "").strip():
        raise ActionError("validation_error", "Enter a display name.")
    cur, cfg = _current(ctx, str(i.get("id") or "")) if mode == "edit" else (None, None)
    off = cur is not None and cur["status"] == "unavailable" and str(d.get("auth") or "").startswith("Pending")
    ops = i["ops"] or {}
    read = [str(y).strip() for y in ops.get("read") or [] if str(y).strip()]
    write = [str(y).strip() for y in ops.get("write") or [] if str(y).strip()]
    csv = d["method"] == "file"
    maps = [[str(y).strip() for y in m] for m in i["maps"]]
    _check_maps(cur["id"] if cur else "", maps)
    iv = _interval(d, cm)
    base = {
        "name": str(d["name"]).strip(), "vendor": d.get("vendor") or "", "ver": str(d.get("ver") or "").strip(),
        "env": d.get("env") or "Production", "url": "" if off else _build_url(d), "method": d["method"],
        "cfg": dict(d.get("cfg") or {}), "mode": "Not connected" if off else method_mode(d["method"], iv), "interval": iv,
        "auth": d.get("auth") or "", "owner": str(d.get("owner") or "").strip() or "Unassigned", "read": read, "write": write,
        "rw": "Read (import)" if csv else "—" if off else ("Read / write" if read else "Write") if write else "Read",
    }  # fmt: skip
    why = f" ({i['note']})" if i.get("note") else ""
    now = _now_ms(ctx)
    if mode == "new":
        return _bound(ctx, _create(ctx, d, base, maps, csv, cm, why, now, i), i)
    assert cur is not None  # noqa: S101 - edit mode loaded both
    assert cfg is not None  # noqa: S101
    ch: list[str] = []
    for k, label in (
        ("name", "display name"), ("vendor", "vendor product"), ("ver", "version"), ("env", "environment"),
        ("method", "connection method"), ("url", "endpoint"), ("auth", "authentication"), ("interval", "schedule"),
        ("owner", "owner"),
    ):  # fmt: skip
        if _js_str(cur.get(k)) != _js_str(base[k]):
            ch.append(label)
    if cur.get("cfg") != base["cfg"] and cur.get("method") == base["method"]:
        ch.append("method settings")
    if "|".join(read) != "|".join(cur.get("read") or []) or "|".join(write) != "|".join(cur.get("write") or []):
        ch.append("operations")
    if maps != cur["maps"]:
        ch.append(f"field mapping ({len(maps)} rows)")
    ch += _save_connection(ctx, cur["id"], i, base["url"], _js_str(cur.get("url")) != _js_str(base["url"]), None)
    ch += _bind_org(ctx, cur["id"], i)
    was_off = cur["status"] == "unavailable" and not off and not csv
    if not ch and not was_off and not (csv and cur["status"] != "manual") and not (not csv and cur["status"] == "manual"):
        raise ActionError("conflict", "No changes to save.")
    sid = cur["id"]
    cfg |= base | {"maps": maps}
    cur |= base
    if was_off:
        cfg.pop("prev", None), cfg.pop("discBy", None)
        sync.mark_connected(ctx.session, sid, "unavailable" if cur["db"] == "unavailable" else "live")
        ch.append("connected")
    elif csv and cur["status"] != "manual":
        _set_status(ctx, sid, "manual")
        ch.append("switched to flat file import")
    elif not csv and cur["status"] == "manual":
        _set_status(ctx, sid, "live")
        ch.append("switched to a live feed")
    ver = _bump(ctx, cur, cfg, "Updated " + ", ".join(ch) + why)
    cfg["updatedBy"] = _by(ctx)
    lifecycle.save(ctx.session, cfg)
    if any(c.startswith("field mapping") for c in ch):  # the mapping the next sync applies (plan 6 A4)
        mapping.save_version(ctx.session, sid, maps, _by(ctx), f"Config v{ver}", ctx.now)
    ctx.session.execute(
        text("UPDATE source_system SET vendor = :v, interval_min = :iv, owner = :o, updated_at = now() WHERE id = :i"),
        {"v": base["vendor"], "iv": iv, "o": base["owner"], "i": sid},
    )
    _event(ctx, cur, "connector.updated", "acknowledged", f"Config v{ver}: " + ", ".join(ch) + why)
    if was_off:
        sync.set_delivery(sid, True)
    return {"mode": "edit", "source_id": sid, "name": cur["name"], "ver": ver, "changes": ch, "wasOff": was_off}


def _set_status(ctx: CallContext, sid: str, status: str) -> None:
    ctx.session.execute(text("UPDATE source_system SET status = :st, updated_at = now() WHERE id = :i"), {"st": status, "i": sid})


def _free_id(ctx: CallContext, base: str) -> str:
    """The demo's id for a new source: its type, then type_2, type_3 ... (an id a deleted source keeps is not reused)."""
    taken = set(ctx.session.execute(text("SELECT id FROM source_system")).scalars())
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}_{n}", n + 1
    return sid


def _insert_source(ctx: CallContext, sid: str, vendor: str, type_: str, status: str, iv: int, owner: str, **kw: Any) -> None:
    ctx.session.execute(
        text(
            "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner, completeness, confidence) "
            "VALUES (:id, :v, :t, :st, :iv, :a, :o, :c, :k) ON CONFLICT (id) DO UPDATE SET vendor = EXCLUDED.vendor, "
            "type = EXCLUDED.type, status = EXCLUDED.status, interval_min = EXCLUDED.interval_min, owner = EXCLUDED.owner, "
            "completeness = EXCLUDED.completeness, confidence = EXCLUDED.confidence, note = NULL, last_sync_at = NULL, "
            "last_success_at = NULL, updated_at = now()"
        ),
        {"id": sid, "v": vendor, "t": type_, "st": status, "iv": iv, "a": kw.get("authority") or [], "o": owner,
         "c": kw.get("compl"), "k": kw.get("conf")},
    )  # fmt: skip


def _create(ctx: CallContext, d: dict, base: dict, maps: list, csv: bool, cm: dict, why: str, now: int, i: dict) -> dict:
    t = SRC_TYPES.get(d.get("type") or "")
    if t is None:
        raise ActionError("validation_error", f"No source type {d.get('type')}.")
    seed = SRC_SEED.get(d["type"], {"inputs": "", "authority": [], "step": []})
    sid = _free_id(ctx, d["type"])
    item = {
        "id": sid, "created": "new", "cat": t["cat"], "short": t["short"], "inputs": seed["inputs"],
        "authority": list(seed["authority"]), "step": list(seed["step"]), "cfgVer": "1.0", "credAt": now, "credDays": 180,
        "updatedBy": _by(ctx),
        "audit": [{"ver": "1.0", "who": _by(ctx), "ts": now, "change": "Connection created" + why, "prep": ctx.preparer}],
    } | base | {"maps": maps}  # fmt: skip
    _insert_source(
        ctx, sid, base["vendor"], d["type"], "manual" if csv else "live", base["interval"], base["owner"], compl=0, conf=0
    )
    if not csv:  # the endpoint entered is the one its connector reads (plan 6 A2)
        _save_connection(ctx, sid, i, base["url"], True, {"auth": base["auth"], "read": base["read"]})
    if csv:  # the demo: a manual import counts as just synced
        ctx.session.execute(
            text("UPDATE source_system SET last_sync_at = :at, last_success_at = :at WHERE id = :i"), {"at": ctx.now, "i": sid}
        )
    lifecycle.save(ctx.session, item)
    if not csv and registry.has_adapter(ctx.session, sid):  # its endpoint answers like a spec: the first sync reads it
        sync.enqueue_sync(ctx.session, sid, "initial", full=True)
    mapping.save_version(ctx.session, sid, maps, _by(ctx), "Connection created", ctx.now, strict=False)  # plan 6 A4
    cur = item | {"vendor": base["vendor"]}
    _event(
        ctx,
        cur,
        "connector.created",
        "acknowledged",
        f"{base['vendor']} connected as {base['name']} via {cm['label']} ({base['env']})",
    )
    return {"mode": "new", "source_id": sid, "name": base["name"], "vendor": base["vendor"], "csv": csv}


def _catalog_maps(sid: str, sent: list) -> list[list[str]]:
    """The rows a catalogue connection saves: the template's rows (di.connectors.catalog) the person accepted, matched
    on source field and canonical field (and resource, the 6th column, when sent), with the template's rule; then the
    key rows they need. Rows that are not the template's (the demo's FR_SAMPLE) are not saved: their fields are not in
    the system's records. A pass-through row keeps the demo's text."""
    offered = catalog.maps(sid)
    seen: dict[int, tuple[str, str]] = {}
    for m in sent:
        if not isinstance(m, list) or len(m) < 3:
            continue
        m = [str(x).strip() for x in m] + [""] * (6 - len(m))
        for n, r in enumerate(offered):
            if r["src"] == m[0] and f"{r['model']}.{r['field']}" == m[2] and m[5] in ("", r["resource"]):
                seen.setdefault(n, (m[1], m[3]))
    chosen = [offered[n] for n in sorted(seen)]
    out = [[r["src"], "", f"{r['model']}.key", "", r["rule"], r["resource"]] for r in catalog.key_rows(sid, chosen)]
    for n in sorted(seen):
        r = offered[n]
        out.append([r["src"], seen[n][0], f"{r['model']}.{r['field']}", seen[n][1],
                    ACCEPTED if r["rule"] == "copy" else r["rule"], r["resource"]])  # fmt: skip
    return out


def _connect_catalog(i: dict[str, Any], ctx: CallContext) -> dict:
    """frCxFinish: the new connection from the catalogue, live (a file drop is a manual import), with its accepted
    mappings; the catalogue entry shows connected from now on."""
    d = i["d"]
    c = CATALOG.get(str(d.get("catalog") or ""))
    if c is None:
        raise ActionError("not_found", f"No catalogue system {d.get('catalog')}.")
    sid = c["id"]
    row = ctx.session.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": sid}).first()
    if row is not None and not lifecycle.is_deleted(ctx.session, sid):
        raise ActionError("conflict", f"{c['vendor']} is already connected.")
    if row is not None and sid not in REF:  # connected again after a delete: none of the deleted source's history
        lifecycle.purge(ctx.session, sid)
    auth = next((a[1] for a in FR_AUTH if a[0] == d.get("auth")), None)
    if auth is None:
        raise ActionError("validation_error", "Choose how Circularity signs in.")
    scopes = [str(x) for x in d.get("scopes") or []]
    maps = _catalog_maps(sid, i["maps"])
    if catalog.maps(sid) and not maps:
        raise ActionError("validation_error", "Accept at least one mapping.")
    t = c["type"]
    m = "jdbc" if t == "db" else "file" if t == "store" else "delta" if t == "dw" else "api"
    T = type_of(t)
    now, events = _now_ms(ctx), "events" in scopes
    iv = 0 if m == "file" or events else 30
    tpl = catalog.template(sid)
    if tpl is None:
        raise ActionError("not_found", f"No connection template for {c['vendor']}.")
    base_url = connection.sim_url(tpl["base_path"])  # source-sim's synthetic mock of the system (plan 6 A3)
    item = {
        "id": sid, "created": "catalog", "vendor": c["vendor"], "ver": "Connected " + fmt_dy(now), "url": base_url,
        "mode": "Controlled CSV import" if m == "file" else "API + events" if events else "Polling · 30 min",
        "interval": iv, "auth": auth, "rw": "Read / write" if "write" in scopes else "Read", "inputs": c["desc"],
        "read": [f"GET {r['path']}" for r in tpl["resources"]], "write": ["POST /records"] if "write" in scopes else [],
        "step": [1], "authority": [],
        "owner": "Integration Engineering", "frConnectedAt": now, "cat": T.get("cat", "internal"),
        "name": T["label"], "short": T["short"], "env": "Production", "cfgVer": "1.0", "method": m, "cfg": cfg_defaults(m),
        "credAt": now, "credDays": 180, "updatedBy": _by(ctx), "scopes": scopes,
        "audit": [{"ver": "1.0", "who": _by(ctx), "ts": now, "change": "Connected from the catalogue"}], "maps": maps,
    }  # fmt: skip
    _insert_source(ctx, sid, c["vendor"], t, "manual" if m == "file" else "live", iv, item["owner"], compl=92, conf=88)
    ctx.session.execute(text("DELETE FROM source_connection WHERE source_id = :i"), {"i": sid})  # a stale row of this id
    connection.save_connection(
        ctx.session, sid, _by(ctx), base_url=base_url, protocol="rest", auth_kind=tpl["auth_kind"],
        auth_params=tpl["auth_params"], paging=tpl["paging"], resources=tpl["resources"],
    )  # fmt: skip
    # the one the person entered (the Connect dialog prefills the mock's sandbox key; another one fails at Auth), or,
    # when none is sent (the API), the credential source-sim's mock accepts (synthetic, README.md)
    secrets.put_secret(ctx.session, sid, "auth", str(i.get("secret") or tpl["demo_secret"]), 180, _by(ctx), ctx.now)
    lifecycle.save(ctx.session, item)
    mapping.save_version(ctx.session, sid, maps, _by(ctx), "Connected from the catalogue", ctx.now, strict=False)  # A4
    job = sync.enqueue_sync(ctx.session, sid, "initial", full=True)  # the first sync really reads the system
    _event(ctx, item, "source.connected", "acknowledged", "Connected from the catalogue by " + _by(ctx))
    return {"mode": "catalog", "source_id": sid, "name": item["name"], "vendor": c["vendor"], "records": None,
            "queued": job is not None, "csv": m == "file"}  # fmt: skip


_declare(
    "mapping.catalogSuggest", "Suggest field mappings", "suggest field mappings",
    "The field mappings a catalogue system's records support, each with a sample value read from the system. "
    "Changes nothing.", "read", {"catalog_id": {"req": True, "t": "string"}}, _MGR,
)  # fmt: skip


def _cell(v: Any) -> str:
    return "" if v is None else str(v)[:80]


@implement("mapping.catalogSuggest")
def mapping_suggest(i: dict[str, Any], ctx: CallContext):
    """Suggest mappings in the Connect dialog: the template's rows (di.connectors.catalog), each with the value of its
    source field in the first record of its resource, read from the system now (source-sim's synthetic mock, with its
    demo credential), and the value the rule makes of it. A row whose field that record does not have is left out; no
    row is invented for fields the template does not map. Rows: [source field, sample, model.field, normalised,
    confidence %, resource]; template rows are High (≥ 85 %). The key rows are not offered: connecting adds them."""
    import httpx

    from di.connectors.configured import ConfiguredAdapter
    from di.connectors.http import SourceClient, SourceError

    cid = str(i.get("catalog_id") or "")
    c, tpl = CATALOG.get(cid), catalog.template(cid)
    if c is None or tpl is None:
        raise ActionError("not_found", f"No catalogue system {cid}.")
    offered = catalog.maps(cid)
    out: dict[str, Any] = {"catalog_id": cid, "rows": [], "error": None}
    if not offered:
        return out
    conn = connection.Connection(
        cid, connection.sim_url(tpl["base_path"]), "rest", tpl["auth_kind"], tpl["auth_params"], tpl["paging"],
        tpl["resources"],
    )  # fmt: skip
    adapter = ConfiguredAdapter(conn)
    first: dict[str, Any] = {}
    client = SourceClient(cid, conn.base_url, adapter.auth(conn, tpl["demo_secret"]), ctx.session, None, timeout=10)
    try:
        for res in adapter.resources():
            if any(r["resource"] == res.name for r in offered):
                records = res.read(client, None)
                try:
                    first[res.name] = next(iter(records), None)
                finally:
                    getattr(records, "close", lambda: None)()
    except (SourceError, httpx.HTTPError) as e:
        out["error"] = f"Could not read a sample from {c['vendor']}: {e}"
    finally:
        client.close()
    for r in offered:
        rec = first.get(r["resource"])
        sample = norm = None
        if rec is not None:
            sample = mapping.lookup(rec.payload, r["src"])
            if sample is mapping._MISSING:
                continue  # the system's records do not have this field
            try:
                norm = mapping.apply_rule(r["rule"], sample)
            except (ValueError, TypeError):
                norm = None
        elif r["resource"] in first:  # the resource is empty: nothing shows the field exists
            continue
        conf = 96 if r["rule"] == "copy" else 91
        out["rows"].append([r["src"], _cell(sample), f"{r['model']}.{r['field']}", _cell(norm), conf, r["resource"]])
    return out


@implement("source.sandboxKey")
def sandbox_key(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - every action takes the context
    """The key source-sim's synthetic mock of a catalogue system accepts (di.connectors.catalog `demo_secret`): the
    Connect dialog prefills its key field with it and says so. It is no customer secret: the mock is public test data."""
    cid = str(i.get("catalog_id") or "")
    tpl = catalog.template(cid) if cid in CATALOG else None
    if tpl is None:
        raise ActionError("not_found", f"No catalogue system {cid}.")
    return {"catalog_id": cid, "key": tpl["demo_secret"]}


# ---------------------------------------------------------------- delete, reconnect, rotate
@implement("source.delete")
def source_delete(i: dict[str, Any], ctx: CallContext):
    """Gone from every screen, its syncs stop; its data and settings stay, so Undo (POST /api/journal/undo) restores it."""
    cur, _ = _current(ctx, i["source_id"])
    sync.drop_queued(ctx.session, cur["id"])
    _event(ctx, cur, "connector.deleted", "acknowledged", cur["vendor"] + " disconnected and removed from the Source map")
    return {"source_id": cur["id"], "name": cur["name"], "vendor": cur["vendor"]}


@implement("source.reconnect")
def source_reconnect(i: dict[str, Any], ctx: CallContext):
    """Refresh the feed token and re-sync: the source is live again (also after Pause or Disconnect, as in the demo),
    its credential is renewed, source-sim's expired-token fault is cleared and a sync is queued. A connector beyond the
    demo's sources (Windchill, plan 8 MVP-9.3) that nobody registered yet is registered first (di.connectors.extra)."""
    extra.ensure_registered(ctx.session, str(i["source_id"]))
    cur, cfg = _current(ctx, i["source_id"])
    sid, was = cur["id"], cur["db"]
    if was == "auth_expired" or cur["status"] == "stale":
        lifecycle.refresh_credentials(sid)
    job = sync.mark_connected(
        ctx.session, sid, "unavailable" if was == "unavailable" or cfg.get("prev") == "unavailable" else "live"
    )
    ctx.session.execute(text("UPDATE source_system SET note = NULL WHERE id = :i"), {"i": sid})
    for k in ("prev", "discBy", "note"):
        cfg.pop(k, None)
    cfg["credAt"] = _now_ms(ctx)
    ver = _bump(ctx, cur, cfg, "Token refreshed and feed re-synced")
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "feed.restored", "acknowledged", "Token refreshed; latest records re-pulled")
    sync.set_delivery(sid, True)
    return {"source_id": sid, "name": cur["name"], "ver": ver, "queued": job is not None}


@implement("credentials.rotate")
def credentials_rotate(i: dict[str, Any], ctx: CallContext):
    """A new secret and its term, or (reauth) the consent rerun and the term renewed. The secret is stored encrypted
    (di.connectors.secrets, plan 6 A1); it is never journaled (the pipeline drops `secret`) nor returned."""
    if i.get("secret") is not None and len(str(i["secret"])) < 8:
        raise ActionError("validation_error", "Enter at least 8 characters.")
    days = i["days"]
    if not (isinstance(days, int | float) and 1 <= days <= 3650):
        raise ActionError("validation_error", '"days" must be from 1 to 3650.')
    reauth = bool(i.get("reauth"))  # frCxDone: the consent step rerun, the credential renewed
    cur, cfg = _current(ctx, i["source_id"])
    if not reauth and not i.get("secret"):
        raise ActionError("validation_error", "Enter the new secret.")
    cfg["credAt"], cfg["credDays"] = _now_ms(ctx), int(days)
    meta: secrets.SecretMeta | None
    if i.get("secret"):
        meta = secrets.put_secret(ctx.session, cur["id"], "auth", str(i["secret"]), int(days), _by(ctx), ctx.now)
    else:
        meta = secrets.renew(ctx.session, cur["id"], int(days), now=ctx.now)
    ver = _bump(ctx, cur, cfg, "Re-authenticated; credential renewed" if reauth else "Credentials rotated")
    lifecycle.save(ctx.session, cfg)
    if reauth:
        _event(ctx, cur, "source.reauthenticated", "acknowledged", f"{cur['vendor']} · by {_by(ctx)}")
    else:
        _event(ctx, cur, "credential.rotated", "acknowledged", "Secret rotated; old secret revoked")
    return {
        "source_id": cur["id"],
        "ver": ver,
        "stale": cur["status"] == "stale",
        "credAt": cfg["credAt"],
        "credDays": cfg["credDays"],
        "credential": meta.public() if meta else None,
    }


# ---------------------------------------------------------------- pause, resume, disconnect
def _workflows_using(ctx: CallContext, sid: str) -> int:
    return len(wf_using(all_workflows(ctx.session), sid))


@implement("source.pause")
def source_pause(i: dict[str, Any], ctx: CallContext):
    cur, cfg = _current(ctx, i["source_id"])
    if cur["db"] == "paused":
        raise ActionError("conflict", f"{cur['name']} is already paused.")
    if cur["db"] in ("disconnected", "unavailable"):
        raise ActionError("conflict", f"{cur['name']} is not connected. Connect it first.")
    cfg["prev"] = cur["db"]
    _set_status(ctx, cur["id"], "paused")
    sync.drop_queued(ctx.session, cur["id"])
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "source.paused", "acknowledged", "Scheduled syncs stopped by " + _by(ctx))
    return {"source_id": cur["id"], "name": cur["name"], "vendor": cur["vendor"], "paused": True,
            "workflows": _workflows_using(ctx, cur["id"])}  # fmt: skip


@implement("source.resume")
def source_resume(i: dict[str, Any], ctx: CallContext):
    cur, cfg = _current(ctx, i["source_id"])
    if cur["db"] != "paused":
        raise ActionError("conflict", f"{cur['name']} is not paused.")
    _set_status(ctx, cur["id"], cfg.pop("prev", None) or "live")
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "source.resumed", "acknowledged", "Scheduled syncs resumed by " + _by(ctx))
    return {"source_id": cur["id"], "name": cur["name"], "vendor": cur["vendor"], "paused": False}


@implement("source.disconnect")
def source_disconnect(i: dict[str, Any], ctx: CallContext):
    cur, cfg = _current(ctx, i["source_id"])
    if str(i["confirm"]).strip() != cur["vendor"]:
        raise ActionError("validation_error", f"Type {cur['vendor']} to confirm.")
    if cur["db"] == "disconnected":
        raise ActionError("conflict", f"{cur['vendor']} is already disconnected.")
    cfg["prev"] = cfg.get("prev") if cur["db"] == "paused" else cur["db"]
    cfg["discBy"] = _by(ctx)
    _set_status(ctx, cur["id"], "disconnected")
    sync.drop_queued(ctx.session, cur["id"])
    _bump(ctx, cur, cfg, "Disconnected; settings kept for reconnect")
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "source.disconnected", "acknowledged", "Disconnected by " + _by(ctx))
    sync.set_delivery(cur["id"], False)
    return {"source_id": cur["id"], "name": cur["name"], "vendor": cur["vendor"]}


# ---------------------------------------------------------------- test connection (plan 6 A5: every step real)
def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _steps_of(p, auth: str, reauth: bool) -> list[dict]:
    """frTestRun's five steps from a real probe (di.connectors.probe): DNS (the resolved address), TLS (the handshake,
    or a warning for http), Auth, Permissions (one record from each read resource), Sample read. Stops at the first
    failure, as the demo does. Re-authenticating: a refused old credential does not stop the test."""
    out: list[dict] = []

    def add(ok: bool, msg: str, warn: bool = False) -> bool:
        out.append({"ok": ok, "msg": msg} | ({"warn": True} if warn else {}))
        return ok

    if not add(p.dns.ok, f"{p.host} → {p.dns.detail}" if p.dns.ok else p.dns.error):
        return out
    if not p.tcp.ok:
        add(False, p.tcp.error)
        return out
    if not add(p.tls.ok, p.tls.detail if p.tls.ok else p.tls.error, p.tls.warn):
        return out
    if not p.auth.ok and not reauth:
        refused = "Token rejected (HTTP 401): the credential is expired or revoked"
        add(False, p.auth.error if p.auth.error.startswith("Credential expired") or p.auth.status != 401 else refused)
        return out
    add(True, auth)
    if not p.auth.ok:  # reauth: the old credential was refused; the new one is used from Finish on
        add(True, "Permissions are checked with the new credential once you finish")
        add(True, "Reads with the new credential once you finish")
        return out
    if not add(p.perms.ok, _plural(p.resources, "read resource") + " answered" if p.perms.ok else p.perms.error):
        return out
    add(p.read.ok, f"{_plural(p.records, 'record')} in {p.read.ms} ms" if p.read.ok else p.read.error)
    return out


def _probe_steps(ctx: CallContext, sid: str, status: str, auth: str, reauth: bool) -> list[dict]:
    if status == "unavailable":  # not provisioned, not configured or disconnected: nothing to connect to
        return [{"ok": False, "msg": "No route to host: the system is not provisioned"}]
    if not registry.has_adapter(ctx.session, sid):  # a file import, or set up by hand with no read resources
        return [{"ok": False, "msg": "Nothing to probe: this connection has no read resources (add GET /path operations)"}]
    return _steps_of(probe(ctx.session, sid), auth, reauth)


def _catalog_steps(ctx: CallContext, c: dict, auth: str, secret: str | None = None) -> list[dict]:
    """A catalogue system being connected: its template's connection, probed with the credential the person typed
    (another key than the mock's sandbox key fails at Auth), or the simulator's sandbox credential when none is sent."""
    from di.connectors.configured import ConfiguredAdapter
    from di.connectors.probe import probe_connection

    tpl = catalog.template(c["id"])
    if tpl is None:
        return [{"ok": False, "msg": f"No connection template for {c['vendor']}"}]
    conn = connection.Connection(
        c["id"], connection.sim_url(tpl["base_path"]), "rest", tpl["auth_kind"], tpl["auth_params"], tpl["paging"],
        tpl["resources"],
    )  # fmt: skip
    used = secret or tpl["demo_secret"]
    return _steps_of(probe_connection(ctx.session, c["id"], ConfiguredAdapter(conn), conn, used), auth, False)


def _draft_test(ctx: CallContext, cur: dict | None, draft: dict) -> dict:
    """sdTest: the source drawer's one-line test of the settings being edited. The saved connection is probed when the
    endpoint is unchanged; a new endpoint is checked for DNS and a TCP connection."""
    cm = CONN_METHODS.get(str(draft.get("method") or "")) or {"label": "The connection"}
    url, auth = str(draft.get("url") or ""), str(draft.get("auth") or "")
    nr, nw = int(draft.get("read") or 0), int(draft.get("write") or 0)
    ops = f"{nr} read and {nw} write operations available."
    if cur and cur["status"] == "unavailable" and auth.startswith("Pending"):
        return {"ok": False, "msg": "No connection configured. Choose an authentication method and complete the settings."}
    if cur and cur.get("url") == url and cur["status"] != "unavailable" and registry.has_adapter(ctx.session, cur["id"]):
        p = probe(ctx.session, cur["id"])
        bad = next((c for c in (p.dns, p.tcp, p.tls, p.auth, p.perms, p.read) if not c.ok), None)
        if bad is None:
            return {"ok": True, "msg": f"{cm['label']} reached in {p.read.ms} ms. {ops}"}
        if bad.status == 401:
            return {
                "ok": False,
                "msg": "HTTP 401 Unauthorized. The credential was refused or has expired; "
                "use Refresh token and re-sync or rotate credentials.",
            }
        return {"ok": False, "msg": f"{cm['label']} did not answer: {bad.error}"}
    if _is_http(url):
        u = urlparse(url)
        try:
            socket.create_connection((u.hostname or "", u.port or (443 if u.scheme == "https" else 80)), timeout=3).close()
        except (OSError, UnicodeError) as e:
            return {"ok": False, "msg": f"{cm['label']} did not answer: {u.hostname}: {e}"}
        return {"ok": True, "msg": f"{u.hostname} answers. {ops} Save to test signing in and reading."}
    return {"ok": True, "msg": f"{cm['label']} settings are complete. {ops} Nothing to connect to until it is saved."}


@implement("source.test")
def source_test(i: dict[str, Any], ctx: CallContext):
    sid = str(i.get("source_id") or "")
    reauth = bool(i.get("reauth"))
    if isinstance(i.get("draft"), dict):
        cur = _current(ctx, sid)[0] if sid else None
        return _draft_test(ctx, cur, i["draft"])
    if sid.startswith("cat:"):  # a catalogue system being connected: its template, really probed
        c = CATALOG.get(sid[4:])
        if c is None:
            raise ActionError("not_found", f"No catalogue system {sid[4:]}.")
        steps = _catalog_steps(ctx, c, i.get("auth") or c["auth"][0], str(i["secret"]) if i.get("secret") else None)
    else:
        if not sid:
            raise ActionError("validation_error", 'Missing "source_id".')
        cur = _current(ctx, sid)[0]
        steps = _probe_steps(ctx, sid, cur["status"], i.get("auth") or cur.get("auth") or "", reauth)
    ok = all(x["ok"] for x in steps) and len(steps) == 5
    return {"source_id": sid, "steps": steps, "ok": ok, "at": iso(_now_ms(ctx))}


# ---------------------------------------------------------------- field mapping versions (plan 6 A4)
_declare(
    "mapping.preview", "Preview a field mapping", "preview field mappings",
    "Map a sample record of a source with a mapping (the saved one, or a draft) and show the facts. Changes nothing.",
    "read", _SRC | {"maps": {"req": False, "t": "array"}, "ext_id": {"req": False, "t": "string"}}, _MGR,
)  # fmt: skip
_declare(
    "mapping.revert", "Revert a field mapping", "revert field mappings",
    "Save a new version of a source's field mapping equal to an older one; the next sync applies it.", "act",
    _SRC | {"version": {"req": True, "t": "number"}}, _MGR,
)  # fmt: skip
mark_destructive("mapping.revert")  # an agent that prepares it is held for a person (P9-2.4)
_declare(
    "mapping.save", "Save a field mapping", "save field mappings",
    "Save a new version of a source's field mapping without touching its connection; the next sync applies it.", "act",
    _SRC | {"maps": {"req": True, "t": "array"}, "note": {"req": False, "t": "string"}}, _MGR,
)  # fmt: skip


def _check_maps(sid: str, maps: list) -> None:
    """The rows a sync can apply: a source field, a canonical model.field of a store model, a known rule."""
    try:
        mapping.rows_from_maps(sid, maps)
    except ValueError as e:
        raise ActionError("validation_error", str(e)) from None


def _fact_view(f: Any, status: str) -> dict:
    return {
        "target": f"{f.model}.{f.field}", "key": f.key, "value": f.value, "source_field": f.source_field,
        "source_value": f.source_value, "transform": f.transform, "status": status,
    }  # fmt: skip


@implement("mapping.preview")
def mapping_preview(i: dict[str, Any], ctx: CallContext):
    """The newest landed record of the source (or `ext_id`) mapped with `maps` (a draft of the Data Mapping tab's rows)
    or the saved mapping: each fact with its status (kept: as the adapter's code maps it; changed; added), the fields
    the mapping drops, or the error that would fail the record (e.g. "missing field grade_txt")."""
    cur, _ = _current(ctx, i["source_id"])
    sid = cur["id"]
    maps = i.get("maps")
    if maps is not None:
        maps = [[str(y).strip() for y in m] for m in maps if isinstance(m, list)]
        _check_maps(sid, maps)
    version = mapping.active_version(ctx.session, sid)
    if maps is not None:
        rows = mapping.to_rows(mapping.rows_from_maps(sid, maps))
    elif version is not None:
        rows = mapping.active_rows(ctx.session, sid)
    else:
        rows = mapping.to_rows(mapping.rows_from_maps(sid, cur["maps"], strict=False))
    q = "SELECT resource, ext_id, payload FROM raw_record WHERE source_id = :s"
    args: dict[str, Any] = {"s": sid}
    if i.get("ext_id"):
        q, args["e"] = q + " AND ext_id = :e", str(i["ext_id"])
    raw = ctx.session.execute(text(q + " ORDER BY fetched_at DESC, ext_id DESC LIMIT 1"), args).first()
    out: dict[str, Any] = {"source_id": sid, "version": version, "record": None, "facts": [], "dropped": [], "error": None}
    if raw is None:
        out["error"] = "No record has landed from this source yet: sync it first."
        return out
    from di.connectors.base import Record

    rec = Record(raw.resource, raw.ext_id, raw.payload)
    out["record"] = {"resource": raw.resource, "ext_id": raw.ext_id, "payload": raw.payload}
    adapter = ADAPTERS.get(sid)
    try:
        if adapter is None:
            out["facts"] = [_fact_view(f, "added") for f in mapping.apply_rows(rows, rec)]
            return out
        code = adapter.map(rec)
        got = mapping.overlay(code, rec, rows, mapping.builtin(sid))
    except Exception as e:  # noqa: BLE001 - the record would fail the same way in a sync: say why
        out["error"] = str(e) or type(e).__name__
        return out
    before = {(f.model, f.field): f for f in code}
    after = {(f.model, f.field) for f in got}
    for f in got:
        b = before.get((f.model, f.field))
        status = "added" if b is None else "kept" if (b.value, b.transform) == (f.value, f.transform) else "changed"
        out["facts"].append(_fact_view(f, status))
    out["dropped"] = [f"{m}.{fl}" for (m, fl) in before if (m, fl) not in after]
    return out


@implement("mapping.revert")
def mapping_revert(i: dict[str, Any], ctx: CallContext):
    """A new mapping version equal to an older one; the Data Mapping tab shows its rows; the next sync applies it."""
    cur, cfg = _current(ctx, i["source_id"])
    sid = cur["id"]
    try:
        new, maps = mapping.revert(ctx.session, sid, int(i["version"]), _by(ctx), ctx.now)
    except KeyError as e:
        raise ActionError("not_found", str(e).strip("'\"")) from None
    cfg["maps"] = maps
    ver = _bump(ctx, cur, cfg, f"Field mapping reverted to v{int(i['version'])} (mapping v{new})")
    cfg["updatedBy"] = _by(ctx)
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "connector.updated", "acknowledged", f"Config v{ver}: field mapping reverted to v{int(i['version'])}")
    return {"source_id": sid, "version": new, "ver": ver, "rows": len(maps), "maps": maps}


def _save_maps(i: dict[str, Any]) -> list[list[str]]:
    return [[str(y).strip() for y in m] for m in i["maps"] if isinstance(m, list)]


@guard("mapping.save")
def mapping_save_guard(i: dict[str, Any], ctx: CallContext):
    """P9-0.17: the checks run before the pipeline's hold (step 9b), so an agent's invalid call is refused, not held."""
    try:
        cur, _ = _current(ctx, i["source_id"])
        maps = _save_maps(i)
        _check_maps(cur["id"], maps)
    except ActionError as e:
        return e.code, e.message
    return ("conflict", "No changes to save.") if maps == cur["maps"] else None


@implement("mapping.save")
def mapping_save(i: dict[str, Any], ctx: CallContext):
    """plan 9 P9-0.10: the Data Mapping tab's rows saved as a new mapping version, apart from the rest of the source
    (source.update still takes `maps`). Held for a person when an agent prepares it (HELD_FOR_PERSON)."""
    cur, cfg = _current(ctx, i["source_id"])
    return _save_rows(ctx, cur, cfg, _save_maps(i), str(i.get("note") or "").strip() or "Field mapping saved")


def _save_rows(ctx: CallContext, cur: dict[str, Any], cfg: dict[str, Any], maps: list[list[str]], note: str) -> dict[str, Any]:
    """The one path that saves a source's field mapping as a new version: mapping.save and mapping.apply (P9-8.4) call it."""
    sid = cur["id"]
    version = mapping.save_version(ctx.session, sid, maps, _by(ctx), note, ctx.now)
    ver = _bump(ctx, cur, cfg, f"Field mapping saved ({len(maps)} rows)")
    cfg["maps"] = maps
    cfg["updatedBy"] = _by(ctx)
    lifecycle.save(ctx.session, cfg)
    _event(ctx, cur, "connector.updated", "acknowledged", f"Config v{ver}: field mapping saved")
    return {"source_id": sid, "version": version, "ver": ver, "rows": len(maps)}


ACTIONS["mapping.suggest"].perm = _MGR  # the demo's PERM_ACTS.manageIntegrations (P9-8.2)
ACTIONS["mapping.suggest"].input |= {"resource": {"req": False, "t": "string"}}


def _family_memory(s: Any, sid: str, vendor: str) -> dict[str, str]:
    """Source field -> model.field from the newest accepted mapping rows of every source of the vendor's family (its first
    word, the source itself included): what a person accepted before for this kind of system."""
    fam = vendor.split()[0].lower() if vendor.strip() else ""
    same = "SELECT id FROM source_system WHERE lower(split_part(vendor, ' ', 1)) = :f OR id = :i"
    rows = s.execute(text(same), {"f": fam, "i": sid})
    memory: dict[str, str] = {}
    for (other,) in rows.all():
        for r in mapping.active_rows(s, other):
            memory.setdefault(r.src, f"{r.model}.{r.field}")
    return memory | mapping_decisions.memory_for(s, mapping_decisions.family_of(vendor))  # the people's choices win (P9-8.4)


@implement("mapping.suggest")
def mapping_suggest_fields(i: dict[str, Any], ctx: CallContext):
    """P9-8.2 (I-19): propose canonical fields for the fields the source's stored sample has (up to 500 records per
    resource, discover.SAMPLE), with calibrated confidence, a band and a reason. The profiles are masked before the model
    reads them (di.connectors.mapping_suggest); the model, when the router has one, only reranks the candidates. Rows:
    the proposal, its `resource` and its masked `samples`; `gaps`: required canonical fields of the models proposed with
    no proposal; `decision` is the row's live choice and `waiting` the questions open to the system owner and `fields`
    the canonical fields to choose from (P9-8.4). Writes nothing."""
    from di.connectors import discover, mapping_suggest
    from di.services.agents.mapping_rerank import make_reranker

    sid, only = str(i["source_id"]), str(i.get("resource") or "")
    s = ctx.session
    row = s.execute(text("SELECT vendor FROM source_system WHERE id = :i"), {"i": sid}).first()
    if row is None or lifecycle.is_deleted(s, sid):
        raise ActionError("not_found", f"No source {sid}.")
    canon = mapping_suggest.canonical_fields()
    memory = _family_memory(s, sid, row.vendor)
    rerank = make_reranker(ctx)
    rows: list[dict[str, Any]] = []
    for res, recs in discover._samples(s, sid).items():
        if only and res != only:
            continue
        sample = [p for _, p in recs]
        profiles = [mapping_suggest.profile(sample, f) for f in mapping_suggest.field_paths(sample)]
        for p, prop in zip(profiles, mapping_suggest.suggest(profiles, sample, canon, memory=memory, rerank=rerank), strict=True):
            rows.append(prop.as_dict() | {"resource": res, "samples": p.top_values})
    live = {(d["resource"] or "", d["src"]): d for d in mapping_decisions.of_source(s, sid)}
    for r in rows:
        d = live.get((r["resource"], r["field"])) or live.get(("", r["field"]))
        r["decision"] = {k: d[k] for k in ("id", "decision", "target", "rule", "owner", "reason")} if d else None
    models = {r["target"].split(".")[0] for r in rows if r["target"]}
    have = {r["target"] for r in rows if r["target"]}
    gaps = [c.target for c in canon if c.required and c.model in models and c.target not in have]
    waiting = len(mapping_decisions.open_questions(s, sid))
    by_model = any(r["proposed_by"] == "model" for r in rows)
    fields = [c.target for c in canon]  # what "Choose another field" offers
    return {"source_id": sid, "rows": rows, "gaps": gaps, "waiting": waiting, "fields": fields, "by_model": by_model}


# ---------------------------------------------------------------- the five choices (plan 9 P9-8.4)
_CHOICES = ("accepted", "replaced", "accepted_with_rule", "not_needed")
_STRING = {"t": "string"}
_declare(
    "mapping.decide", "Choose for a suggested mapping", "choose for suggested mappings",
    "Record a person's choice for one suggested field: accept it, choose another field, accept it with a conversion or mark it "
    "not needed. Saves nothing: Apply mappings does.", "act",
    _SRC | {"src": {"req": True, "t": "string"}, "decision": {"req": True, "t": "string"}, "target": _STRING, "rule": _STRING,
            "resource": _STRING, "proposed": _STRING, "confidence": {"t": "number"}, "reason": _STRING, "proposed_by": _STRING},
    _MGR,
)  # fmt: skip
_declare(
    "mapping.askOwner", "Ask the system owner about a field", "ask system owners about fields",
    "Ask the source's system owner what a field means; it appears in their My work. Mapping cannot be applied until they answer.",
    "act",
    _SRC | {"src": {"req": True, "t": "string"}, "resource": _STRING,
            "question": {"req": True, "t": "string", "min": 5, "minText": "Write the question."}},
    _MGR,
)  # fmt: skip
_declare(
    "mapping.answerOwner", "Answer a mapping question", "answer mapping questions",
    "The system owner's choice for a field they were asked about; closes the work item.", "act",
    {"decision_id": {"req": True, "t": "number"}, "decision": {"req": True, "t": "string"}, "target": _STRING,
     "rule": _STRING}, None,
)  # fmt: skip
ACTIONS["mapping.apply"].input |= {"rows": {"req": True, "t": "array"}}  # the catalogue's action: the accepted rows (P9-8.4)
ACTIONS["mapping.apply"].perm = _MGR
_OWNER_TYPE = "mapping_owner"


def _refused(fn: Any, *a: Any) -> tuple[str, str] | None:
    try:
        fn(*a)
    except ActionError as e:
        return e.code, e.message
    return None


def _check_choice(i: dict[str, Any]) -> None:
    """A choice the server can record: a known decision, a canonical `model.field` target, a rule parse_rule knows."""
    from di.connectors import mapping_suggest

    d = str(i.get("decision") or "")
    if d not in _CHOICES:
        raise ActionError("validation_error", f"The choice is one of {', '.join(_CHOICES)}.")
    t = str(i.get("target") or "")
    if d != "not_needed" and t not in {c.target for c in mapping_suggest.canonical_fields()}:
        raise ActionError("validation_error", f"Choose a canonical field (model.field); {t or 'none'} is not one.")
    if d == "accepted_with_rule":
        rule = mapping.parse_rule(i.get("rule"))
        if rule is None or rule == mapping.CODE:
            raise ActionError("validation_error", f"No conversion rule '{i.get('rule') or ''}'.")


def _sample_values(s: Any, sid: str, src: str, resource: str | None) -> list[Any]:
    from di.connectors import discover

    out: list[Any] = []
    for res, recs in discover._samples(s, sid).items():
        if resource and res != resource:
            continue
        for _, payload in recs:
            v = mapping.lookup(payload, src)
            if v is not mapping._MISSING and v is not None:
                out.append(v)
    return out


def _converted(s: Any, sid: str, src: str, resource: str | None, rule: str, n: int = 5) -> dict[str, Any]:
    """The first sample values of the field before (masked) and after the rule: what the person sees at once."""
    from di.connectors.mapping_suggest import mask

    before, after = [], []
    for v in _sample_values(s, sid, src, resource)[:n]:
        before.append(mask(v))
        try:
            r = mapping.apply_rule(rule, v)
        except ValueError:
            r = None
        after.append(round(r, 2) if isinstance(r, float) else mask(r) if isinstance(r, str) else r)
    return {"samples": before, "values": after}


def _close_questions(ctx: CallContext, old: list[dict[str, Any]], outcome: str) -> None:
    from di.services.cases import process

    for o in old:
        if o["decision"] != "asked_owner":
            continue
        for (item,) in ctx.session.execute(
            text("SELECT id FROM work_item WHERE type = :t AND status = 'open'"), {"t": f"{_OWNER_TYPE}:{o['id']}"}
        ).all():
            process.close_item(ctx.session, item, outcome, _by(ctx))


def _record_choice(
    ctx: CallContext, sid: str, i: dict[str, Any], src: str, resource: str | None, owner: str | None
) -> dict[str, Any]:
    s = ctx.session
    d = str(i["decision"])
    target = str(i.get("target") or "") or None
    rule = mapping.parse_rule(i.get("rule")) if d == "accepted_with_rule" else None
    old = mapping_decisions.supersede(s, sid, src, resource)
    _close_questions(ctx, old, f"{d}: {target or src}")
    did = mapping_decisions.record(
        s, source_id=sid, src=src, resource=resource, decision=d, by=ctx.actor.id, target=target, rule=rule, owner=owner,
        confidence=float(i["confidence"]) if i.get("confidence") is not None else None, reason=i.get("reason"),
        proposed_by=i.get("proposed_by"), answer={"proposed": i["proposed"]} if i.get("proposed") else None,
    )  # fmt: skip
    out: dict[str, Any] = {"id": did, "source_id": sid, "src": src, "decision": d, "target": target, "rule": rule}
    if rule:
        out |= _converted(s, sid, src, resource, rule)
    if d == "not_needed" and target:
        from di.connectors import mapping_suggest

        if any(c.required and c.target == target for c in mapping_suggest.canonical_fields()):
            out |= {"blocking": True, "warning": f"Required field {target} is marked not needed."}
    return out


@guard("mapping.decide")
def mapping_decide_guard(i: dict[str, Any], ctx: CallContext):
    if bad := _refused(_current, ctx, i["source_id"]):
        return bad
    return _refused(_check_choice, i)


@implement("mapping.decide")
def mapping_decide(i: dict[str, Any], ctx: CallContext):
    """P9-8.4: one person's choice for one suggested field, recorded in `mapping_decision` (memory for the vendor family).
    An agent's call is held for a person (HELD_FOR_PERSON). It saves no mapping; `mapping.apply` does."""
    cur, _ = _current(ctx, i["source_id"])
    out = _record_choice(ctx, cur["id"], i, str(i["src"]), str(i.get("resource") or "") or None, None)
    return out | {"log": f"Chose for {i['src']}"}


def _owner_of(ctx: CallContext, sid: str) -> Any:
    conn = connection.connection_for(ctx.session, sid)
    owner = policy.account(conn.system_owner or "", ctx.actor.ctx) if conn else None
    if owner is None:
        raise ActionError("validation_error", f"{sid} has no system owner in the directory: name one first.")
    return owner


def _org_of(ctx: CallContext, sid: str) -> Any:
    return ctx.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": sid}).scalar()


@guard("mapping.askOwner")
def mapping_ask_guard(i: dict[str, Any], ctx: CallContext):
    try:
        _current(ctx, i["source_id"])
        _check_org({"org_unit_id": _org_of(ctx, i["source_id"])}, ctx)
        _owner_of(ctx, i["source_id"])
    except ActionError as e:
        return e.code, e.message
    return None


@implement("mapping.askOwner")
def mapping_ask_owner(i: dict[str, Any], ctx: CallContext):
    """P9-8.4: record the question (`asked_owner`) and open a My work item for the source's system owner with the field, three
    masked sample values and the question. Agents may ask (it creates a question, nothing else); only a person answers."""
    from di.connectors.mapping_suggest import mask
    from di.services.cases import process

    cur, _ = _current(ctx, i["source_id"])
    sid, src, owner = cur["id"], str(i["src"]), _owner_of(ctx, i["source_id"])
    resource = str(i.get("resource") or "") or None
    s = ctx.session
    question = str(i["question"]).strip()
    samples = [mask(v) for v in _sample_values(s, sid, src, resource)[:3]]
    _close_questions(ctx, mapping_decisions.supersede(s, sid, src, resource), "Asked again")
    did = mapping_decisions.record(
        s, source_id=sid, src=src, resource=resource, decision="asked_owner", by=ctx.actor.id, owner=owner.id, reason=question,
        answer={"question": question, "samples": samples},
    )  # fmt: skip
    item = process.open_item(
        s, kind="step", case_id=None, org_unit_id=_org_of(ctx, sid), type=f"{_OWNER_TYPE}:{did}",
        title=f"Which field is {src} on {cur['name']}?", action="Answer the mapping question",
        cause=f"{question} Sample values: {', '.join(samples) or 'none yet'}.",
        owner_role=owner.role, owner_account=owner.id, due_hours=None, by=ctx.actor.id,
    )  # fmt: skip
    return {"id": did, "source_id": sid, "src": src, "owner": owner.id, "item_id": item, "samples": samples,
            "log": f"Asked {owner.id} about {src}"}  # fmt: skip


@guard("mapping.answerOwner")
def mapping_answer_guard(i: dict[str, Any], ctx: CallContext):
    row = mapping_decisions.get(ctx.session, int(i["decision_id"]))
    if row is None or row["decision"] != "asked_owner":
        return "not_found", "No such question."
    if row["superseded"]:
        return "conflict", "That question is already answered."
    a = ctx.actor.account
    if a is None or not (a.id == row["owner"] or policy.can(a, _MGR, ctx.actor.ctx)):
        return "out_of_scope", f"Only {row['owner']} (the system owner) or an integration manager answers this."
    return _refused(_check_choice, i)


@implement("mapping.answerOwner")
def mapping_answer_owner(i: dict[str, Any], ctx: CallContext):
    """P9-8.4: the owner's choice replaces the question (the owner's word wins in the family memory) and closes the item.
    In `FORBIDDEN_ACTIONS`: an agent never answers for a person."""
    row = mapping_decisions.get(ctx.session, int(i["decision_id"]))
    assert row is not None  # noqa: S101 - the guard found it
    out = _record_choice(ctx, row["source_id"], i, row["src"], row["resource"], row["owner"])
    return out | {"log": f"Answered for {row['src']}"}


def _apply_maps(cur_maps: list[list[str]], rows: list[Any]) -> list[list[str]]:
    """The tab's rows with the accepted rows put in: a row of the same source field (and resource) is replaced."""
    new: list[list[str]] = []
    for r in rows:
        if isinstance(r, dict):
            m = [str(r.get("src", "")), "", str(r.get("target", "")), "", str(r.get("rule") or "")]
            new.append(m + ([str(r["resource"])] if r.get("resource") else []))
        elif isinstance(r, list):
            new.append([str(x).strip() for x in r])
    key = {(m[0], m[5] if len(m) > 5 else "") for m in new}
    return [m for m in cur_maps if (m[0], m[5] if len(m) > 5 else "") not in key] + new


def _required_not_needed(s: Any, sid: str, maps: list[list[str]]) -> list[str]:
    from di.connectors import mapping_suggest

    required = {c.target for c in mapping_suggest.canonical_fields() if c.required}
    mapped = {m[2] for m in maps if len(m) > 2}
    skipped = {d["target"] for d in mapping_decisions.of_source(s, sid) if d["decision"] == "not_needed" and d["target"]}
    return sorted((skipped & required) - mapped)


@guard("mapping.apply")
def mapping_apply_guard(i: dict[str, Any], ctx: CallContext):
    """Before the pipeline's hold, so an agent's invalid call is refused, not held (P9-0.17)."""
    try:
        cur, _ = _current(ctx, i["source_id"])
        if not isinstance(i["rows"], list) or not i["rows"]:
            raise ActionError("validation_error", "Accept at least one mapping.")
        maps = _apply_maps(cur["maps"], i["rows"])
        _check_maps(cur["id"], maps)
    except ActionError as e:
        return e.code, e.message
    if n := len(mapping_decisions.open_questions(ctx.session, cur["id"])):
        return "conflict", f"Waiting for the system owner on {n} field{'s' if n != 1 else ''}."
    if missing := _required_not_needed(ctx.session, cur["id"], maps):
        return "conflict", f"Required field {', '.join(missing)} is marked not needed."
    return ("conflict", "No changes to save.") if maps == cur["maps"] else None


@implement("mapping.apply")
def mapping_apply(i: dict[str, Any], ctx: CallContext):
    """P9-8.4: the accepted rows become a new mapping version through `_save_rows`, the path `mapping.save` uses. Refused
    while a question to the system owner is open. Held for a person when an agent prepares it (HELD_FOR_PERSON)."""
    cur, cfg = _current(ctx, i["source_id"])
    note = str(i.get("note") or "").strip() or "Suggested mappings accepted"
    return _save_rows(ctx, cur, cfg, _apply_maps(cur["maps"], i["rows"]), note)
