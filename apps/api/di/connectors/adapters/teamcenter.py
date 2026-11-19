"""Siemens Teamcenter (plm): product configuration, compatibility, approved alternates (the demo's SOURCES.plm). Read only.

Teamcenter Services over HTTP/JSON (POST /teamcenter/tc/JsonRestServices/<Library>-<version>-<Port>/<operation>,
{"header", "body"}). Core-2011-06-Session/login opens a session kept in the JSESSIONID cookie (TcSession below);
a call answered with InvalidUserException logs in again once. Reading:
1. Query-2006-03-SavedQuery/getSavedQueries finds the saved queries by name;
2. Query-2008-06-SavedQuery/executeSavedQueries runs "Nf0 Compatibility Checks" (one per asset; Asset ID = *), or on
   a delta read "Modified After" the cursor, plus the checks of every Item, ItemRevision or alternate approval
   modified after it ("Item...", "Item Revision...", "Nf0 Alternate Approvals", then the checks by Item ID);
3. Core-2006-03-DataManagement/getProperties loads the checks, their design revisions and items (100 per call);
4. Core-2007-09-DataManagement/expandGRMRelationsForPrimary follows each item's Nf0AltApproval relations.
One record per asset joins its check with the revision, the item and the item's alternates. The cursor is the newest
last_mod_date among them (UTC).

Facts (plm has authority over configuration and compatibility)
    asset.<nf0AssetId>   configuration (Item object_name), configuration_item (item_id), config_revision
                         (item_revision_id), config_release_status, bom_ref (nf0BomRef), config_properties
                         (nf0ConfigProps), compatibility, config_status, compatible_items, approved_alternates, target_use
Provenance keeps the demo's mapping names: ITEM_ID MTR-55-IE3-250M → asset.configuration "55 kW · IE3 · 250M"
(Config decoded); ALT_APPROVED Y → compatible (Boolean); REV C → asset.bom_ref BOM-55-C (Revision prefix).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep
from di.connectors.http import Auth, SourceClient, SourceError

SERVICES = "/JsonRestServices"
HEADER = {"state": {"stateless": True, "formatProperties": True, "unloadObjects": True, "locale": "en_US"}, "policy": {}}
CHUNK = 100
ARRAYS = {"nf0CompatibleItems", "nf0ConfigProps", "nf0Variants", "nf0Manufacturers", "release_status_list", "revision_list"}
CHECK_ATTRS = [
    "nf0AssetId",
    "nf0DesignRevision",
    "nf0ConfigStatus",
    "nf0AltApproved",
    "nf0Compatibility",
    "nf0CompatibleItems",
    "nf0TargetUse",
    "nf0CheckedAt",
    "last_mod_date",
]
REV_ATTRS = [
    "item_id",
    "item_revision_id",
    "object_name",
    "items_tag",
    "release_status_list",
    "date_released",
    "nf0BomRef",
    "nf0ConfigProps",
    "nf0Variants",
    "last_mod_date",
]
ITEM_ATTRS = ["item_id", "object_name", "nf0AssetClass", "nf0Family", "last_mod_date"]
COMPATIBILITY = {"COMPATIBLE": "compatible", "UNDER_REVIEW": "under_review", "INCOMPATIBLE": "incompatible"}


def _exception(body: Any) -> str | None:
    q = body.get(".QName", "") if isinstance(body, dict) else ""
    return q.rsplit(".", 1)[-1] if "/Exceptions." in q else None


class TcSession(Auth):
    """Teamcenter login; the session travels in the JSESSIONID cookie."""

    def __init__(self, user: str, password: str, group: str = "", role: str = ""):
        self.user, self.password, self.group, self.role = user, password, group, role
        self.sid: str | None = None

    def headers(self, client: SourceClient, force_refresh: bool = False) -> dict[str, str]:
        if force_refresh or not self.sid:
            body = {
                "credentials": {
                    "user": self.user,
                    "password": self.password,
                    "group": self.group,
                    "role": self.role,
                    "locale": "en_US",
                    "descrimator": "circularity-di",
                }
            }
            r = client.raw(
                "POST", f"{SERVICES}/Core-2011-06-Session/login", json={"header": HEADER, "body": body}, log_records=False
            )
            if r.status_code != 200 or _exception(r.json()):
                raise SourceError("auth", f"plm: Teamcenter login failed: {r.text[:200]}", r.status_code)
            self.sid = r.cookies.get("JSESSIONID")
            if not self.sid:
                raise SourceError("auth", "plm: Teamcenter login returned no JSESSIONID")
        return {"Cookie": f"JSESSIONID={self.sid}"}


def tc_date(iso: str) -> str:
    """ISO 8601 → a saved-query date entry (dd-Mon-yyyy HH:MM:SS, the server's zone: UTC)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).strftime("%d-%b-%Y %H:%M:%S")


def utc_iso(v: str | None) -> str | None:
    return datetime.fromisoformat(v).astimezone(UTC).isoformat() if v else None


class TeamcenterAdapter(Adapter):
    source_id = "plm"
    base_path = "/teamcenter/tc"

    def auth(self):
        return TcSession("di_connector", "Circularity-demo-tc-1", "Engineering", "Designer")

    def resources(self):
        return [Resource("compatibility", self.read_compatibility)]

    # ------------------------------------------------------------- SOA calls
    def call(self, client: SourceClient, operation: str, body: dict) -> dict:
        path = f"{SERVICES}/{operation}"
        out = client.request("POST", path, json={"header": HEADER, "body": body}).json()
        if _exception(out) == "InvalidUserException":  # the session expired: log in again once
            out = client.raw(
                "POST", path, json={"header": HEADER, "body": body}, headers=client.auth.headers(client, force_refresh=True)
            ).json()
        kind = _exception(out)
        if kind:
            raise SourceError(
                "auth" if kind in ("InvalidUserException", "InvalidCredentialsException") else "client",
                f"plm: {operation}: {kind} {out.get('message')}",
            )
        return out

    def run_query(self, client, queries: dict[str, dict], name: str, entries: list[str], values: list[str]) -> list[str]:
        if name not in queries:
            raise SourceError("client", f"plm: saved query {name!r} not found")
        out = self.call(
            client,
            "Query-2008-06-SavedQuery/executeSavedQueries",
            {
                "input": [
                    {
                        "query": queries[name],
                        "entries": entries,
                        "values": values,
                        "maxNumToReturn": 0,
                        "limitList": [],
                        "resultsType": 0,
                        "clientId": "circularity-di",
                    }
                ]
            },
        )
        uids = out["arrayOfResults"][0]["objectUIDS"]
        client.note_records(len(uids))
        return uids

    def props(self, client, uids, attributes: list[str]) -> dict[str, dict]:
        """uid -> {property: value} (one value, or a list for multi-valued properties)."""
        out: dict[str, dict] = {}
        uids = sorted(set(uids))
        for i in range(0, len(uids), CHUNK):
            chunk = uids[i : i + CHUNK]
            sd = self.call(
                client,
                "Core-2006-03-DataManagement/getProperties",
                {"objects": [{"uid": u} for u in chunk], "attributes": attributes},
            )
            for u in chunk:
                mo = sd.get("modelObjects", {}).get(u)
                if not mo or "props" not in mo:
                    continue
                vals = {k: v.get("dbValues") or [] for k, v in mo["props"].items()}
                out[u] = {k: (v if k in ARRAYS else (v[0] if v else None)) for k, v in vals.items()} | {"uid": u}
        return out

    # ------------------------------------------------------------- reading
    def read_compatibility(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        res = self.call(client, "Query-2006-03-SavedQuery/getSavedQueries", {})
        queries = {q["name"]: {"uid": q["query"]["uid"], "type": q["query"]["type"]} for q in res["queries"]}
        if since:
            after = tc_date(since)
            uids = set(self.run_query(client, queries, "Nf0 Compatibility Checks", ["Modified After"], [after]))
            touched = set()
            revs = self.run_query(client, queries, "Item Revision...", ["Modified After"], [after])
            touched |= {p["item_id"] for p in self.props(client, revs, ["item_id"]).values()}
            items = self.run_query(client, queries, "Item...", ["Modified After"], [after])
            touched |= {p["item_id"] for p in self.props(client, items, ["item_id"]).values()}
            rels = self.props(
                client,
                self.run_query(client, queries, "Nf0 Alternate Approvals", ["Modified After"], [after]),
                ["primary_object"],
            )
            touched |= {
                p["item_id"] for p in self.props(client, [r["primary_object"] for r in rels.values()], ["item_id"]).values()
            }
            for item_id in sorted(touched):
                uids |= set(self.run_query(client, queries, "Nf0 Compatibility Checks", ["Item ID"], [item_id]))
        else:
            uids = set(self.run_query(client, queries, "Nf0 Compatibility Checks", ["Asset ID"], ["*"]))
        if not uids:
            return
        checks = self.props(client, uids, CHECK_ATTRS)
        revs = self.props(client, {c["nf0DesignRevision"] for c in checks.values() if c.get("nf0DesignRevision")}, REV_ATTRS)
        items = self.props(client, {r["items_tag"] for r in revs.values() if r.get("items_tag")}, ITEM_ATTRS)
        statuses = self.props(client, {s for r in revs.values() for s in r.get("release_status_list") or []}, ["object_name"])
        grm = self.call(
            client,
            "Core-2007-09-DataManagement/expandGRMRelationsForPrimary",
            {
                "primaryObjects": [{"uid": u} for u in sorted(items)],
                "pref": {
                    "expItemRev": False,
                    "returnRelations": True,
                    "info": [{"relationTypeName": "Nf0AltApproval", "otherSideObjectTypes": []}],
                },
            },
        )
        pairs: dict[str, list[tuple[str, str]]] = {}
        for out in grm.get("output", []):
            for data in out["relationshipData"]:
                for ro in data["relationshipObjects"]:
                    pairs.setdefault(out["inputObject"]["uid"], []).append((ro["otherSideObject"]["uid"], ro["relation"]["uid"]))
        relp = self.props(client, {r for ps in pairs.values() for _, r in ps}, ["nf0Approved", "nf0Reason", "last_mod_date"])
        others = self.props(client, {o for ps in pairs.values() for o, _ in ps}, ["item_id"])
        url = client.url(f"{SERVICES}/Query-2008-06-SavedQuery/executeSavedQueries")
        for c in sorted(checks.values(), key=lambda c: c.get("nf0AssetId") or ""):
            if not c.get("nf0AssetId"):
                continue
            rev = revs.get(c.get("nf0DesignRevision") or "", {})
            item = items.get(rev.get("items_tag") or "", {})
            alts = [
                {
                    "item_id": others.get(o, {}).get("item_id"),
                    "approved": relp.get(r, {}).get("nf0Approved"),
                    "reason": relp.get(r, {}).get("nf0Reason"),
                    "last_mod_date": relp.get(r, {}).get("last_mod_date"),
                }
                for o, r in pairs.get(item.get("uid") or "", [])
            ]
            rev = rev | {"release_status": [statuses.get(s, {}).get("object_name") for s in rev.get("release_status_list") or []]}
            stamps = [
                x
                for x in [
                    c.get("last_mod_date"),
                    rev.get("last_mod_date"),
                    item.get("last_mod_date"),
                    *(a["last_mod_date"] for a in alts),
                ]
                if x
            ]
            changed = max((utc_iso(x) for x in stamps), default=None)
            payload = {"check": c, "revision": rev, "item": item, "alternates": alts}
            yield Record("compatibility", c["nf0AssetId"], payload, url, changed)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        c, rev, item = p["check"], p.get("revision") or {}, p.get("item") or {}
        key, item_id, rv = c["nf0AssetId"], item.get("item_id") or rev.get("item_id"), rev.get("item_revision_id")
        alt = c.get("nf0AltApproved")
        compat = "compatible" if alt == "Y" else COMPATIBILITY.get(c.get("nf0Compatibility") or "", "incompatible")
        if compat == "compatible" and alt != "Y":
            compat = "under_review"
        cfg_props = {}
        for kv in rev.get("nf0ConfigProps") or []:
            k, _, v = kv.partition("=")
            cfg_props[k] = v
        approved = [a for a in p.get("alternates") or [] if a.get("approved") == "Y"]
        released = [s for s in rev.get("release_status") or [] if s]
        return keep(
            [
                Fact(
                    "asset",
                    key,
                    "configuration",
                    item.get("object_name") or rev.get("object_name"),
                    "ITEM_ID",
                    item_id,
                    "Config decoded",
                ),
                Fact("asset", key, "configuration_item", item_id, "ITEM_ID", item_id, "Pass-through"),
                Fact("asset", key, "config_revision", rv, "REV", rv, "Pass-through"),
                Fact(
                    "asset",
                    key,
                    "config_release_status",
                    "released" if released else ("in_work" if rev else None),
                    "release_status_list",
                    released,
                    "Status map: TCM Released → released",
                ),
                Fact("asset", key, "bom_ref", rev.get("nf0BomRef"), "REV", rv, "Revision prefix"),
                Fact(
                    "asset", key, "config_properties", cfg_props or None, "PROPERTIES", rev.get("nf0ConfigProps"), "Pass-through"
                ),
                Fact("asset", key, "compatibility", compat, "ALT_APPROVED", alt, "Boolean"),
                Fact(
                    "asset",
                    key,
                    "config_status",
                    (c.get("nf0ConfigStatus") or "").lower() or None,
                    "CONFIG_STATUS",
                    c.get("nf0ConfigStatus"),
                    "Status map",
                ),
                Fact(
                    "asset",
                    key,
                    "compatible_items",
                    c.get("nf0CompatibleItems"),
                    "COMPATIBLE_ITEMS",
                    c.get("nf0CompatibleItems"),
                    "Pass-through",
                ),
                Fact(
                    "asset",
                    key,
                    "approved_alternates",
                    [{"item": a["item_id"], "reason": a.get("reason")} for a in approved],
                    "ALT_APPROVED",
                    [f"{a['item_id']}:{a['approved']}" for a in p.get("alternates") or []],
                    "Approved alternates (ALT_APPROVED = Y)",
                ),
                Fact("asset", key, "target_use", c.get("nf0TargetUse"), "TARGET_USE", c.get("nf0TargetUse"), "Pass-through"),
            ]
        )


ADAPTER = TeamcenterAdapter()
