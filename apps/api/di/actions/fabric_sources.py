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
                                test of a draft (`draft`), probed against source-sim (di.connectors.probe)
Reconnecting after a disconnect is source.reconnect, as in the demo. Connecting from the catalogue is source.update with
mode "catalog" (d = {catalog, auth, scopes}, maps = the accepted rows): it creates the source, as mode "new" does.

**Sources without a connector.** A source connected from the catalogue or set up by hand has no adapter: source-sim
simulates no system behind it. It is recorded honestly: its first sync is a finished run whose note says it was
synthetic (the row count is the one the demo's connect flow shows), a later source.sync is refused with that reason,
and its connection test passes on its settings with a sample-read line that says nothing was read.

**Not ported.** The demo's Source Map activity lines (smLogAdd; the map's activity is the real sync runs), the draft
ingest workflow the demo adds for a new source (wfAddForSource; Workflow Studio's list is its own), and the connection
test's `source.tested` event (a read action changes nothing).
"""

import copy
import math
import re
from typing import Any

from sqlalchemy import text

from di import golden
from di.actions.decisions import push_event
from di.actions.pipeline import CallContext
from di.actions.registry import ACTIONS, ActionDef, ActionError, implement
from di.connectors import lifecycle, secrets, sync
from di.connectors.probe import probe
from di.connectors.registry import ADAPTERS
from di.reads.common import fmt_dy, hash_id, iso, ms
from di.reads.constants import MAPPINGS, SRC_TYPES
from di.reads.fabric import SCREEN_STATUS, type_of
from di.reads.reference import lists
from di.reads.workflows import all_workflows, wf_using

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
NO_CONNECTOR = "First sync (synthetic): no simulated system behind this connection, so nothing was read"
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
     "auth": {"req": False, "t": "string"}, "draft": {"req": False, "t": "object"}}, None,
)  # fmt: skip
# the secret, when a caller sends it, is only checked (never stored); reauth: the Re-authenticate dialog's renewal
ACTIONS["credentials.rotate"].input |= {"secret": {"req": False, "t": "string"}, "reauth": {"req": False, "t": "boolean"}}


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


def first_sync_rows(key: str) -> int:
    """The demo's connect flow: 1200 + hashId(id) % 9000 records in the first sync."""
    return 1200 + int(hash_id(key), 16) % 9000


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


def _interval(d: dict, cm: dict) -> int:
    if not cm.get("sched"):
        return 0
    try:
        v = float(d.get("interval") or 0)
    except (TypeError, ValueError):
        v = 0
    return int(v) if math.isfinite(v) else 0


@implement("source.update")
def source_update(i: dict[str, Any], ctx: CallContext):
    mode = i["mode"]
    if mode == "catalog":
        return _connect_catalog(i, ctx)
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
        return _create(ctx, d, base, maps, csv, cm, why, now)
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


def _create(ctx: CallContext, d: dict, base: dict, maps: list, csv: bool, cm: dict, why: str, now: int) -> dict:
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
    if csv:  # the demo: a manual import counts as just synced
        ctx.session.execute(
            text("UPDATE source_system SET last_sync_at = :at, last_success_at = :at WHERE id = :i"), {"at": ctx.now, "i": sid}
        )
    else:
        item["records"] = first_sync_rows(sid)
        sync.record_synthetic_run(ctx.session, sid, item["records"], ctx.now, NO_CONNECTOR)
    lifecycle.save(ctx.session, item)
    cur = item | {"vendor": base["vendor"]}
    _event(
        ctx,
        cur,
        "connector.created",
        "acknowledged",
        f"{base['vendor']} connected as {base['name']} via {cm['label']} ({base['env']})",
    )
    return {"mode": "new", "source_id": sid, "name": base["name"], "vendor": base["vendor"], "csv": csv}


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
    auth = next((a[1] for a in FR_AUTH if a[0] == d.get("auth")), None)
    if auth is None:
        raise ActionError("validation_error", "Choose how Circularity signs in.")
    scopes = [str(x) for x in d.get("scopes") or []]
    maps = [[str(y) for y in m[:4]] + [ACCEPTED] for m in i["maps"] if len(m) >= 4]
    if not maps:
        raise ActionError("validation_error", "Accept at least one mapping.")
    t = c["type"]
    m = "jdbc" if t == "db" else "file" if t == "store" else "delta" if t == "dw" else "api"
    T = type_of(t)
    now, events = _now_ms(ctx), "events" in scopes
    iv = 0 if m == "file" or events else 30
    rows = first_sync_rows(sid)
    item = {
        "id": sid, "created": "catalog", "vendor": c["vendor"], "ver": "Connected " + fmt_dy(now),
        "url": f"sftp://{sid}.northfield.example/outbound" if m == "file" else f"https://{sid}.northfield.example/api",
        "mode": "Controlled CSV import" if m == "file" else "API + events" if events else "Polling · 30 min",
        "interval": iv, "auth": auth, "rw": "Read / write" if "write" in scopes else "Read", "inputs": c["desc"],
        "read": ["GET /records"], "write": ["POST /records"] if "write" in scopes else [], "step": [1], "authority": [],
        "owner": "Integration Engineering", "records": rows, "frConnectedAt": now, "cat": T.get("cat", "internal"),
        "name": T["label"], "short": T["short"], "env": "Production", "cfgVer": "1.0", "method": m, "cfg": cfg_defaults(m),
        "credAt": now, "credDays": 180, "updatedBy": _by(ctx), "scopes": scopes,
        "audit": [{"ver": "1.0", "who": _by(ctx), "ts": now, "change": "Connected from the catalogue"}], "maps": maps,
    }  # fmt: skip
    _insert_source(ctx, sid, c["vendor"], t, "manual" if m == "file" else "live", iv, item["owner"], compl=92, conf=88)
    sync.record_synthetic_run(ctx.session, sid, rows, ctx.now, NO_CONNECTOR)
    lifecycle.save(ctx.session, item)
    _event(ctx, item, "source.connected", "acknowledged", "Connected from the catalogue by " + _by(ctx))
    return {"mode": "catalog", "source_id": sid, "name": item["name"], "vendor": c["vendor"], "records": rows, "csv": m == "file"}


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
    its credential is renewed, source-sim's expired-token fault is cleared and a sync is queued."""
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


# ---------------------------------------------------------------- test connection
def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _host(url: str, vendor: str) -> str:
    return re.sub(r"^[a-z]+://", "", url or "").split("/")[0] or vendor


def _ip(key: str) -> str:
    """The demo's address line: 10.<hash % 200>.<hash % 250>.<hash % 250>, from the source id."""
    h = lambda k: int(hash_id(k), 16)  # noqa: E731 - the demo's one-line helper
    return f"10.{h(key) % 200}.{h(key + 'b') % 250}.{h(key + 'c') % 250}"


def _steps(ctx: CallContext, key: str, vendor: str, url: str, status: str, auth: str, read: list, sid: str | None, reauth: bool):
    """frTestRun: DNS, TLS, Auth, Permissions, Sample read; stops at the first failure, as the demo does."""
    host = _host(url, vendor)
    out = []

    def add(ok: bool, msg: str) -> bool:
        out.append({"ok": ok, "msg": msg})
        return ok

    if status == "unavailable":  # not provisioned, not configured or disconnected: the demo's first-step failure
        add(False, "No route to host: the system is not provisioned")
        return out
    if sid is None or sid not in ADAPTERS:  # nothing behind it to probe: the settings only
        add(True, f"{host} → {_ip(key)}")
        add(True, "TLS 1.3 · certificate valid")
        add(True, auth)
        add(True, _plural(len(read), "read scope") + " granted")
        add(True, "No simulated system behind this connection: nothing was read")
        return out
    p = probe(ctx.session, sid)
    if not add(p.dns.ok, f"{host} → {_ip(key)}" if p.dns.ok else p.dns.error):
        return out
    if not add(p.tcp.ok, "TLS 1.3 · certificate valid" if p.tcp.ok else p.tcp.error):
        return out
    rejected = (status == "stale" and not reauth) or (p.auth.status == 401 and not reauth)
    if rejected:
        add(False, "Token rejected: expired")
        return out
    if p.auth.status == 403:
        add(True, auth)
        add(False, "Access denied: the read scopes are missing (HTTP 403)")
        return out
    add(True, auth)
    add(True, _plural(len(read), "read scope") + " granted")
    if not p.auth.ok and reauth:  # the old credential was refused; the new one is used from Finish on
        add(True, "Reads with the new credential once you finish")
    elif p.read.ok:
        add(True, f"{_plural(p.records, 'record')} in {p.read.ms} ms")
    else:
        add(False, p.read.error)
    return out


def _draft_test(ctx: CallContext, cur: dict | None, draft: dict) -> dict:
    """sdTest: the source drawer's one-line test of the settings being edited."""
    cm = CONN_METHODS.get(str(draft.get("method") or "")) or {"label": "The connection"}
    url, auth = str(draft.get("url") or ""), str(draft.get("auth") or "")
    nr, nw = int(draft.get("read") or 0), int(draft.get("write") or 0)
    ops = f"{nr} read and {nw} write operations available."
    if cur and cur["status"] == "stale" and cur.get("url") == url:
        return {
            "ok": False,
            "msg": "HTTP 401 Unauthorized. The feed token expired; use Refresh token and re-sync or rotate credentials.",
        }
    if cur and cur["status"] == "unavailable" and auth.startswith("Pending"):
        return {"ok": False, "msg": "No connection configured. Choose an authentication method and complete the settings."}
    if cur and cur["id"] in ADAPTERS and cur.get("url") == url and cur["status"] != "unavailable":
        p = probe(ctx.session, cur["id"])
        bad = next((c for c in (p.dns, p.tcp, p.auth, p.read) if not c.ok), None)
        if bad is None:
            return {"ok": True, "msg": f"{cm['label']} reached in {p.read.ms} ms. {ops}"}
        if bad.status == 401:
            return {
                "ok": False,
                "msg": "HTTP 401 Unauthorized. The feed token expired; use Refresh token and re-sync or rotate credentials.",
            }
        return {"ok": False, "msg": f"{cm['label']} did not answer: {bad.error}"}
    nothing = "No simulated system answers at this endpoint, so nothing was reached."
    return {"ok": True, "msg": f"{cm['label']} settings are complete. {ops} {nothing}"}


@implement("source.test")
def source_test(i: dict[str, Any], ctx: CallContext):
    sid = str(i.get("source_id") or "")
    reauth = bool(i.get("reauth"))
    if isinstance(i.get("draft"), dict):
        cur = _current(ctx, sid)[0] if sid else None
        return _draft_test(ctx, cur, i["draft"])
    if sid.startswith("cat:"):  # a catalogue system being connected: what it will be once connected
        c = CATALOG.get(sid[4:])
        if c is None:
            raise ActionError("not_found", f"No catalogue system {sid[4:]}.")
        url = f"https://{c['id']}.northfield.example/api"
        steps = _steps(ctx, sid, c["vendor"], url, "live", i.get("auth") or c["auth"][0], ["GET /records"], None, False)
    else:
        if not sid:
            raise ActionError("validation_error", 'Missing "source_id".')
        cur = _current(ctx, sid)[0]
        status = "live" if reauth and cur["status"] == "stale" else cur["status"]
        steps = _steps(
            ctx,
            sid,
            cur["vendor"],
            cur.get("url") or "",
            status,
            i.get("auth") or cur.get("auth") or "",
            cur.get("read") or [],
            sid,
            reauth,
        )
    ok = all(x["ok"] for x in steps) and len(steps) == 5
    return {"source_id": sid, "steps": steps, "ok": ok, "at": iso(_now_ms(ctx))}
