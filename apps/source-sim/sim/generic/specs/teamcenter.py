"""Siemens Teamcenter (the demo's SOURCES.plm): product configuration, compatibility rules, approved alternates,
revisions. Read: GET /v1/items, /v1/alternates, /v1/compatibility. No writes.

Field names follow the demo's MAPPINGS.plm (ITEM_ID, ALT_APPROVED, REV). One item per product configuration seen in
the cases (the configuration is decoded from the case's spec), e.g. RT-1048's motor is MTR-55-IE3-250M,
"55 kW · IE3 · 250M", revision C, BOM-55-C. One compatibility record per asset. Alternates pair configurations of the
same family; an alternate is approved when it fits the same mounting/interface and is at least as capable.
"""

import re
from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.assetwise import hash_id
from sim.seed import Seed
from sim.seed.model import CaseFacts

PUMP_DRIVE = {"Gear": "GR", "Axial piston": "AP", "Vane": "VN"}
CTL_FAMILY = {"Drive module D4": "DM4", "Edge-X controller": "EDX", "HMI-12 panel": "HMI12", "Series 7 PLC": "S7PLC"}
SIL = {"None": 0, "SIL 1": 1, "SIL 2": 2, "SIL 3": 3}
DRILL_TYPE = {"Hammer drill": "HD", "Impact driver": "ID", "Rotary hammer": "RH", "Angle grinder": "AG"}
CHUCK = {"M14": "M14", "SDS-plus": "SDS", "13 mm": "C13"}
IT_DEVICE = {'Laptop 14"': "LT14", 'Laptop 15"': "LT15", "Rugged tablet": "RTB", 'Tablet 10"': "TB10"}
BATCH_TOOL = {"Cordless drills": "CD", "Impact wrenches": "IW", "Torque drivers": "TD"}
EFFICIENCY = {"IE1": 1, "IE2": 2, "IE3": 3, "IE4": 4, "IE5": 5}
# per-unit values, not part of a configuration
UNIT_KEYS = {"Battery cycles", "Battery health", "Firmware", "Data erasure", "Calibration", "Lot grade", "Speed"}
FIXED_REV = {"MTR-55-IE3-250M": "C"}  # the demo's MAPPINGS.plm example


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
        it = out.setdefault(c["id"], {"config": c, "cls": f.cls, "product": f.product, "facts": []})
        it["facts"].append(f)
    return out


def revision(item_id: str) -> str:
    return FIXED_REV.get(item_id) or "ABCD"[hash_id(item_id) % 4]


def bom_ref(item_id: str, cfg: dict) -> str:
    return f"BOM-{cfg['size']}-{revision(item_id)}"


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    by_item = items_by_config(s)
    items, alternates, compatibility = [], [], []
    approved: dict[str, list[str]] = {}
    for item_id, it in by_item.items():
        cfg, rev = it["config"], revision(item_id)
        n = "ABCD".index(rev) + 1
        revs = [
            {
                "REV": "ABCD"[i],
                "STATUS": "TCM Released" if i == n - 1 else "Superseded",
                "RELEASE_DATE": (as_of - timedelta(days=210 * (n - 1 - i) + 30 + hash_id(item_id) % 60)).date().isoformat(),
            }
            for i in range(n)
        ]
        props = {k: v for k, v in it["facts"][0].spec.items() if k not in UNIT_KEYS}
        items.append(
            {
                "ITEM_ID": item_id,
                "OBJECT_NAME": cfg["name"],
                "OBJECT_TYPE": "Design",
                "ASSET_CLASS": it["cls"],
                "PRODUCT": it["product"],
                "REV": rev,
                "REVISIONS": revs,
                "RELEASE_STATUS": "TCM Released",
                "BOM_REF": bom_ref(item_id, cfg),
                "FAMILY": str(cfg["family"]),
                "PROPERTIES": props,
                "VARIANTS": sorted({str(f.spec["Speed"]) for f in it["facts"] if "Speed" in f.spec}),
                "MANUFACTURERS": sorted({f.mfr for f in it["facts"]}),
                "LAST_MODIFIED": revs[-1]["RELEASE_DATE"],
            }
        )
    for a_id, a in by_item.items():
        for b_id, b in by_item.items():
            ca, cb = a["config"], b["config"]
            if a_id == b_id or a["cls"] != b["cls"] or ca["family"] != cb["family"]:
                continue
            ok = ca["fit"] == cb["fit"] and cb["rank"] >= ca["rank"]
            if ok:
                approved.setdefault(a_id, []).append(b_id)
            alternates.append(
                {
                    "ALTERNATE_ID": f"ALT-{a_id}-{b_id}",
                    "ITEM_ID": a_id,
                    "ALT_ITEM_ID": b_id,
                    "ALT_APPROVED": "Y" if ok else "N",
                    "ASSET_CLASS": a["cls"],
                    "REASON": "Same interface, equal or higher rating"
                    if ok
                    else ("Interface differs" if ca["fit"] != cb["fit"] else "Lower rating than the item it replaces"),
                    "EFFECTIVE_DATE": "2026-01-01",
                }
            )
    for case in s.cases.values():
        f = case.facts
        cfg = config(f)
        ev = next((e for e in f.evidence if e.k == "id"), None)
        verified = ev is None or ev.state == "ready"
        redeploy = next((r for r in f.routes if r.id == "redeploy"), None)
        compatibility.append(
            {
                "RULE_ID": f"CMP-{f.asset_id}",
                "ASSET_ID": f.asset_id,
                "ITEM_ID": cfg["id"],
                "REV": revision(cfg["id"]),
                "CONFIG_STATUS": "VERIFIED" if verified else "MISMATCH",
                "TARGET_USE": redeploy.target if redeploy else None,
                "TARGET_ITEM_ID": cfg["id"] if redeploy and redeploy.target else None,
                "ALT_APPROVED": "Y" if verified else "N",
                "COMPATIBILITY": "COMPATIBLE" if verified else "UNDER_REVIEW",
                "COMPATIBLE_ITEMS": [cfg["id"], *approved.get(cfg["id"], [])],
                "CHECKED_AT": as_of.isoformat(),
            }
        )
    return {"items": items, "alternates": alternates, "compatibility": compatibility}


SPEC = Spec(
    source_id="plm",
    title="Siemens Teamcenter",
    schema="teamcenter",
    base_path="/teamcenter/tc/rest",
    auth=Auth("api_key", header="X-TC-API-Key"),
    paging=Paging(
        "offset",
        limit_param="maxToLoad",
        offset_param="startIndex",
        items_key="objects",
        next_key="nextStartIndex",
        total_key="totalFound",
    ),
    resources=(
        Resource("items", "/v1/items", "ITEM_ID", filters=("ASSET_CLASS", "REV", "BOM_REF", "FAMILY", "RELEASE_STATUS")),
        Resource(
            "alternates", "/v1/alternates", "ALTERNATE_ID", filters=("ITEM_ID", "ALT_ITEM_ID", "ALT_APPROVED", "ASSET_CLASS")
        ),
        Resource(
            "compatibility",
            "/v1/compatibility",
            "RULE_ID",
            filters=("ASSET_ID", "ITEM_ID", "CONFIG_STATUS", "COMPATIBILITY", "ALT_APPROVED"),
        ),
    ),
    seed=seed,
)
