"""Load the seed (B2) into the Teamcenter object store, as Teamcenter would hold it at the demo's as-of time.

What Teamcenter owns here (the demo's SOURCES.plm: product configuration, compatibility rules, approved alternates,
revisions), as business objects (one row per object in `teamcenter.pom_object`, properties as Teamcenter names them):

- Item / ItemRevision: one Item per product configuration seen in the cases (the configuration is decoded from the
  case's spec): RT-1048's motor is Item MTR-55-IE3-250M "55 kW · IE3 · 250M". Revisions A.. up to the current one
  (RT-1048's: C), each released with status "TCM Released" (ReleaseStatus objects in release_status_list).
  The current revision carries the BOM reference (nf0BomRef, BOM-55-C), the configuration properties
  (nf0ConfigProps, "Rated power=55 kW" ...) and the speed variants (nf0Variants).
- Nf0AltApproval: a GRM relation between two Items of the same family (primary = the item, secondary = the
  candidate alternate), nf0Approved Y when the alternate fits the same mounting/interface and is at least as capable.
- Nf0CompatCheck: one per returned asset (nf0AssetId MTR-2041 -> nf0DesignRevision MTR-55-IE3-250M/C,
  nf0ConfigStatus VERIFIED, nf0AltApproved Y, nf0Compatibility COMPATIBLE, nf0CompatibleItems, nf0TargetUse).
- ImanQuery: the saved queries a client runs ("Item...", "Item Revision...", "Nf0 Compatibility Checks",
  "Nf0 Alternate Approvals").
Dates are stored in UTC (the server's zone here).
"""

import base64
import hashlib
import re
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.assetwise.seed import hash_id

metadata = MetaData(schema="teamcenter")
POM = Table(
    "pom_object",
    metadata,
    Column("uid", String(14), primary_key=True),
    Column("type", String(40), nullable=False),  # Item, ItemRevision, ReleaseStatus, Nf0AltApproval, Nf0CompatCheck, ImanQuery
    Column("class_name", String(40), nullable=False),
    Column("props", JSONB, nullable=False),  # property name -> db value (str, list[str] or None); dates ISO UTC
    Column("last_mod_date", DateTime(timezone=True), nullable=False),
)

PUMP_DRIVE = {"Gear": "GR", "Axial piston": "AP", "Vane": "VN"}
CTL_FAMILY = {"Drive module D4": "DM4", "Edge-X controller": "EDX", "HMI-12 panel": "HMI12", "Series 7 PLC": "S7PLC"}
SIL = {"None": 0, "SIL 1": 1, "SIL 2": 2, "SIL 3": 3}
DRILL_TYPE = {"Hammer drill": "HD", "Impact driver": "ID", "Rotary hammer": "RH", "Angle grinder": "AG"}
CHUCK = {"M14": "M14", "SDS-plus": "SDS", "13 mm": "C13"}
IT_DEVICE = {'Laptop 14"': "LT14", 'Laptop 15"': "LT15", "Rugged tablet": "RTB", 'Tablet 10"': "TB10"}
BATCH_TOOL = {"Cordless drills": "CD", "Impact wrenches": "IW", "Torque drivers": "TD"}
EFFICIENCY = {"IE1": 1, "IE2": 2, "IE3": 3, "IE4": 4, "IE5": 5}
UNIT_KEYS = {"Battery cycles", "Battery health", "Firmware", "Data erasure", "Calibration", "Lot grade", "Speed"}
FIXED_REV = {"MTR-55-IE3-250M": "C"}  # the demo's MAPPINGS.plm example
OWNER = "infodba (infodba)"
GROUP = "Engineering"
SAVED_QUERIES = {
    # name -> (description, searched type, [(entry name, attribute)])
    "Item...": (
        "Find Items",
        "Item",
        [
            ("Item ID", "item_id"),
            ("Name", "object_name"),
            ("Type", "object_type"),
            ("Modified After", "last_mod_date>"),
            ("Modified Before", "last_mod_date<"),
        ],
    ),
    "Item Revision...": (
        "Find Item Revisions",
        "ItemRevision",
        [
            ("Item ID", "item_id"),
            ("Revision", "item_revision_id"),
            ("Name", "object_name"),
            ("Release Status", "release_status_list.object_name"),
            ("Modified After", "last_mod_date>"),
            ("Modified Before", "last_mod_date<"),
        ],
    ),
    "Nf0 Compatibility Checks": (
        "Find asset compatibility checks (Northfield)",
        "Nf0CompatCheck",
        [
            ("Asset ID", "nf0AssetId"),
            ("Item ID", "nf0DesignRevision.item_id"),
            ("Configuration Status", "nf0ConfigStatus"),
            ("Modified After", "last_mod_date>"),
            ("Modified Before", "last_mod_date<"),
        ],
    ),
    "Nf0 Alternate Approvals": (
        "Find alternate approvals (Northfield)",
        "Nf0AltApproval",
        [
            ("Primary Item ID", "primary_object.item_id"),
            ("Approved", "nf0Approved"),
            ("Modified After", "last_mod_date>"),
            ("Modified Before", "last_mod_date<"),
        ],
    ),
}


def tc_uid(*key: str) -> str:
    """A Teamcenter-style 14-character UID, stable for a key."""
    raw = base64.b64encode(hashlib.sha1("|".join(key).encode()).digest()).decode()
    return re.sub(r"[^A-Za-z0-9]", "x", raw)[:14]


def iso(d: datetime) -> str:
    return d.astimezone(UTC).isoformat(timespec="seconds")


# ------------------------------------------------------------------ configuration decoding (the demo's spec -> ITEM_ID)
def _code(value: object, table: dict[str, str]) -> str:
    return table.get(str(value)) or re.sub(r"[^A-Z0-9]", "", str(value).upper())[:6]


def _num(value: object) -> str:
    m = re.search(r"\d+(?:\.\d+)?", str(value))
    return m.group(0) if m else "0"


def config(f: CaseFacts) -> dict:
    """ITEM_ID, a readable name, the family (alternates group), the interface key and a capability rank."""
    sp = f.spec
    if f.cls == "motor":
        kw, eff, frame = _num(sp["Rated power"]), sp["Efficiency class"], sp["IEC frame"]
        return {
            "id": f"MTR-{kw}-{eff}-{frame}",
            "name": f"{kw} kW · {eff} · {frame}",
            "size": kw,
            "family": kw,
            "fit": frame,
            "rank": (EFFICIENCY.get(eff, 0),),
        }
    if f.cls == "pump":
        drive, bar, flow = sp["Drive"], _num(sp["Pressure"]), _num(sp["Flow"])
        code = f"{_code(drive, PUMP_DRIVE)}-{bar}-{flow}"
        return {
            "id": f"PMP-{code}",
            "name": f"{drive} · {bar} bar · {flow} m³/h",
            "size": code,
            "family": drive,
            "fit": sp["Port"],
            "rank": (int(bar),),
        }
    if f.cls == "control":
        fam, io, sil = sp["Family"], int(sp["I/O points"]), sp["Safety rating"]
        code = f"{_code(fam, CTL_FAMILY)}-{io}IO-S{SIL.get(sil, 0)}"
        return {
            "id": f"CTL-{code}",
            "name": f"{fam} · {io} I/O · {sil}",
            "size": code,
            "family": fam,
            "fit": sp["Supply"],
            "rank": (SIL.get(sil, 0), io),
        }
    if f.cls == "drill":
        typ, v, chuck = sp["Type"], _num(sp["Voltage"]), sp["Chuck"]
        code = f"{_code(typ, DRILL_TYPE)}-{v}V-{_code(chuck, CHUCK)}"
        return {"id": f"DRL-{code}", "name": f"{typ} · {v} V · {chuck}", "size": code, "family": typ, "fit": v, "rank": (0,)}
    if f.cls == "it":
        dev, cpu, st = sp["Device"], sp["CPU / RAM"], _num(sp["Storage"])
        arch, ram = cpu.split("/")[0].strip().upper(), int(_num(cpu.split("/")[1]))
        code = f"{_code(dev, IT_DEVICE)}-{arch}-{ram}G-{st}"
        return {
            "id": f"ITE-{code}",
            "name": f"{dev} · {cpu} · {st} GB",
            "size": code,
            "family": dev,
            "fit": "ARM" if arch == "ARM" else "X86",
            "rank": (ram, int(st)),
        }
    tool, v = sp.get("Tool type", f.product), _num(sp.get("Cell chemistry", ""))
    code = f"{_code(tool, BATCH_TOOL)}-{v}V"
    return {"id": f"BAT-{code}", "name": f"{tool} · Li-ion {v} V", "size": code, "family": tool, "fit": v, "rank": (0,)}


def items_by_config(s: Seed) -> dict[str, dict]:
    """ITEM_ID -> {config, cls, product, facts: [CaseFacts...]}, in case order."""
    out: dict[str, dict] = {}
    for case in s.cases.values():
        f = case.facts
        c = config(f)
        out.setdefault(c["id"], {"config": c, "cls": f.cls, "product": f.product, "facts": []})["facts"].append(f)
    return out


def revision(item_id: str) -> str:
    return FIXED_REV.get(item_id) or "ABCD"[hash_id(item_id) % 4]


def bom_ref(item_id: str, cfg: dict) -> str:
    return f"BOM-{cfg['size']}-{revision(item_id)}"


# ------------------------------------------------------------------ objects
def objects(s: Seed) -> list[dict]:
    as_of = s.world.as_of
    rows: list[dict] = []

    def add(uid: str, type_: str, props: dict, modified: datetime, class_name: str | None = None) -> dict:
        props = {"object_type": type_, "last_mod_date": iso(modified)} | props
        rows.append({"uid": uid, "type": type_, "class_name": class_name or type_, "props": props, "last_mod_date": modified})
        return rows[-1]

    for name, (desc, cls, entries) in SAVED_QUERIES.items():
        add(
            tc_uid("ImanQuery", name),
            "ImanQuery",
            {"object_name": name, "object_desc": desc, "query_class": cls, "nf0Entries": [e for e, _ in entries]},
            datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

    by_item = items_by_config(s)
    rev_uid: dict[str, str] = {}
    for item_id, it in by_item.items():
        cfg, cur = it["config"], revision(item_id)
        n = "ABCD".index(cur) + 1
        item_uid = tc_uid("Item", item_id)
        revs = []
        for i in range(n):
            rev = "ABCD"[i]
            released = datetime.combine(
                (as_of - timedelta(days=210 * (n - 1 - i) + 30 + hash_id(item_id) % 60)).date(), time(10, 30), UTC
            )
            st_uid = tc_uid("ReleaseStatus", item_id, rev)
            add(
                st_uid,
                "ReleaseStatus",
                {"object_name": "TCM Released", "name": "TCM Released", "date_released": iso(released)},
                released,
            )
            ru = tc_uid("ItemRevision", item_id, rev)
            props = {
                "item_id": item_id,
                "item_revision_id": rev,
                "object_name": cfg["name"],
                "object_desc": f"{it['product']} {cfg['name']}",
                "object_string": f"{item_id}/{rev};1-{cfg['name']}",
                "items_tag": item_uid,
                "release_status_list": [st_uid],
                "date_released": iso(released),
                "creation_date": iso(released - timedelta(days=14)),
                "owning_user": OWNER,
                "owning_group": GROUP,
                "nf0BomRef": f"BOM-{cfg['size']}-{rev}",
            }
            if rev == cur:
                spec = {k: v for k, v in it["facts"][0].spec.items() if k not in UNIT_KEYS}
                props |= {
                    "nf0ConfigProps": [f"{k}={v}" for k, v in spec.items()],
                    "nf0Variants": sorted({str(f.spec["Speed"]) for f in it["facts"] if "Speed" in f.spec}),
                }
            add(ru, "ItemRevision", props, released)
            revs.append(ru)
        rev_uid[item_id] = revs[-1]
        first = rows[-1]["last_mod_date"] - timedelta(days=210 * (n - 1) + 14)
        add(
            item_uid,
            "Item",
            {
                "item_id": item_id,
                "object_name": cfg["name"],
                "object_desc": f"{it['product']} {cfg['name']}",
                "object_string": f"{item_id}-{cfg['name']}",
                "revision_list": revs,
                "creation_date": iso(first),
                "owning_user": OWNER,
                "owning_group": GROUP,
                "nf0AssetClass": it["cls"],
                "nf0Product": it["product"],
                "nf0Family": str(cfg["family"]),
                "nf0Manufacturers": sorted({f.mfr for f in it["facts"]}),
            },
            rows[-1]["last_mod_date"],
        )

    approved: dict[str, list[str]] = {}
    alt_date = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    for a_id, a in by_item.items():
        for b_id, b in by_item.items():
            ca, cb = a["config"], b["config"]
            if a_id == b_id or a["cls"] != b["cls"] or ca["family"] != cb["family"]:
                continue
            ok = ca["fit"] == cb["fit"] and cb["rank"] >= ca["rank"]
            if ok:
                approved.setdefault(a_id, []).append(b_id)
            reason = (
                "Same interface, equal or higher rating"
                if ok
                else "Interface differs"
                if ca["fit"] != cb["fit"]
                else "Lower rating than the item it replaces"
            )
            add(
                tc_uid("Nf0AltApproval", a_id, b_id),
                "Nf0AltApproval",
                {
                    "relation_type": "Nf0AltApproval",
                    "primary_object": tc_uid("Item", a_id),
                    "secondary_object": tc_uid("Item", b_id),
                    "object_string": f"{a_id} -> {b_id}",
                    "nf0Approved": "Y" if ok else "N",
                    "nf0Reason": reason,
                    "nf0EffectiveDate": iso(alt_date),
                },
                alt_date,
                class_name="ImanRelation",
            )

    for case in s.cases.values():
        f = case.facts
        cfg = config(f)
        ev = next((e for e in f.evidence if e.k == "id"), None)
        verified = ev is None or ev.state == "ready"
        redeploy = next((r for r in f.routes if r.id == "redeploy"), None)
        checked = min(f.received, as_of)
        add(
            tc_uid("Nf0CompatCheck", f.asset_id),
            "Nf0CompatCheck",
            {
                "object_name": f"CMP-{f.asset_id}",
                "object_string": f"CMP-{f.asset_id}",
                "nf0AssetId": f.asset_id,
                "nf0DesignRevision": rev_uid[cfg["id"]],
                "nf0ConfigStatus": "VERIFIED" if verified else "MISMATCH",
                "nf0AltApproved": "Y" if verified else "N",
                "nf0Compatibility": "COMPATIBLE" if verified else "UNDER_REVIEW",
                "nf0CompatibleItems": [cfg["id"], *approved.get(cfg["id"], [])],
                "nf0TargetUse": redeploy.target if redeploy and redeploy.target else None,
                "nf0CheckedAt": iso(as_of),
                "owning_user": OWNER,
                "owning_group": GROUP,
            },
            checked,
        )
    return rows


def load(conn: Connection, s: Seed) -> dict[str, int]:
    rows = objects(s)
    conn.execute(insert(POM), rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS teamcenter"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM teamcenter.pom_object")).scalar_one() == 0:
        load(conn, s)
