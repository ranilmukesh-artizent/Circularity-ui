"""Fleet contract system (plan 9, P9-3.1): the lease contracts, their lines and returns for the tool-fleet pack.

    GET {base}/contracts | /contract-lines | /returns | /renewals | /contract-history | /proposals | /draft-lines

Synthetic, like every mock here; it reads like an ordinary JSON API (camelCase). Not a demo source: it is in
sim/core/registry.py EXTRA_SYSTEMS, so the industrial demo's systems and counts stay as they were. API key in
`x-api-key` (demo key `fleet-demo-key`), offset paging (`items`, `next`, `total`), `?updated_since=` deltas.

The seed is deterministic (md5, as sim/generic/specs/sandbox.py) and anchored on 2026-10-07: 40 contracts, 332 lines
(320 on the six tool classes, 12 batteries `BAT`), 18 open returns, 25 renewals, 60 ended contracts of history.
Lines of the two ended contracts (one ended, one terminated) read `returned`; their returns were processed before the
anchor, so only the 18 recent ones are in `/returns` (the repair log grades those 18, sim/generic/specs/repair_log.py).
`proposals` and `draftLines` start empty: a client creates them (P9-5.5).
"""

import hashlib
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
TODAY = AS_OF.date()
CLASSES = ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")
SITES = ("Houston", "Denver", "Atlanta", "Chicago", "Phoenix")  # the tool-fleet pack's sites
MARKETS = ("DE", "UK", "US", "AU", "FR")
CUSTOMERS = (
    "Brightline Mechanical", "Granite Civil", "Westmark Supply", "Pinecrest Builders", "Ridgeway Facilities",
    "Harborview Utilities", "Tri-County Paving", "Summit Industrial Services", "Lakeshore Contractors", "Granite Ridge Mining",
)  # fmt: skip
MODELS = {
    "CMH": ("CMH-12 Pro", "CMH-12 Lite"), "BRK": ("BRK-30 Heavy", "BRK-30 Std"), "DCD": ("DCD-250 Rig", "DCD-180 Rig"),
    "CRH": ("CRH-22V Plus", "CRH-22V"), "AGR": ("AGR-230 Pro", "AGR-230"), "LSR": ("LSR-R2 Rotary", "LSR-R1 Rotary"),
    "BAT": ("BAT-22V 5Ah", "BAT-22V 8Ah"),
}  # fmt: skip
RATE = {"CMH": 55.0, "BRK": 70.0, "DCD": 410.0, "CRH": 38.0, "AGR": 22.0, "LSR": 95.0, "BAT": 30.0}  # a line's fee a month
OWNER = {
    "US": "Fleet North America", "UK": "Fleet Europe", "DE": "Fleet Europe", "FR": "Fleet Europe", "AU": "Fleet Asia Pacific",
}  # fmt: skip
REASONS = ("end_of_term", "swap", "repair", "early_termination")
KIND_OF = {"end_of_term": "contract_end", "swap": "swap", "repair": "service_order", "early_termination": "pool_excess",
           "theft_recovered": "service_order"}  # fmt: skip
COVER = ("full", "damage_only", "none")

# the named fixtures the later tests and smokes use
NAMED_CONTRACTS: dict[str, dict[str, Any]] = {
    "FC-30117": {"customer": "Brightline Mechanical", "market": "US", "status": "active", "end": date(2027, 1, 5),
                 "notice": None, "term": 36, "key": False},
    "FC-30121": {"customer": "Granite Civil", "market": "DE", "status": "active", "end": date(2027, 6, 30),
                 "notice": date(2027, 1, 5), "term": 36, "key": False},
    "FC-30140": {"customer": "Westmark Supply", "market": "US", "status": "active", "key": True, "term": 24},
    "FC-30133": {"status": "active"},
    "FC-30128": {"status": "active"},
    "FC-30105": {"status": "ended"},
    "FC-30110": {"status": "terminated"},
}  # fmt: skip
FIXED_LINES = {"FC-30117": 14}  # a contract with a fixed number of non-battery lines


def h(*parts: object) -> int:
    return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def frac(*parts: object) -> float:
    return (h(*parts) % 10000) / 10000


def shift_months(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    return date(y, m + 1, min(d.day, 28))


def stamp(*parts: object, days: int = 30) -> str:
    return (AS_OF - timedelta(minutes=h(*parts, "at") % (days * 24 * 60))).isoformat()


@cache
def build() -> dict[str, Any]:
    """Every document of the seed (contracts, lines, returns, renewals, history), in a stable order."""
    ids = [f"FC-{30100 + i}" for i in range(1, 41)]
    # non-battery lines: FC-30117 has 14, the other 39 contracts share the remaining 306
    others = [c for c in ids if c not in FIXED_LINES]
    ranked = sorted(others, key=lambda c: h("n", c))
    count = {c: 7 + (1 if ranked.index(c) < 306 - 7 * len(others) else 0) for c in others} | FIXED_LINES
    bat_in = [c for c in sorted(others, key=lambda c: h("bat", c)) if c not in ("FC-30105", "FC-30110")][:12]

    contracts: list[dict] = []
    lines: list[dict] = []
    used = {"CMH-48213", "CRH-44120", "BRK-51007", "AGR-20991"}
    for cid in ids:
        nm = NAMED_CONTRACTS.get(cid, {})
        roll = h("status", cid) % 20
        status = nm.get("status") or ("active" if roll < 15 else "evergreen" if roll < 18 else "active")
        customer = nm.get("customer") or CUSTOMERS[h("cust", cid) % len(CUSTOMERS)]
        market = nm.get("market") or MARKETS[h("mkt", cid) % len(MARKETS)]
        term = nm.get("term") or (12, 24, 36, 48)[h("term", cid) % 4]
        if status in ("ended", "terminated"):
            end = TODAY - timedelta(days=15 + h("end", cid) % 300)
        else:
            end = nm.get("end") or TODAY + timedelta(days=25 + h("end", cid) % 620)
        start = shift_months(end, -term)
        if "notice" in nm:
            notice = nm["notice"]
        else:
            notice = end - timedelta(days=60) if status == "active" and h("nt", cid) % 8 == 0 else None
        key = nm["key"] if "key" in nm else h("key", cid) % 9 == 0
        if status in ("ended", "terminated"):
            renewal = "lapsed" if status == "terminated" else "renewed"
        elif status == "evergreen":
            renewal = None
        else:
            renewal = "open" if (end - TODAY).days < 150 else None
        n = count[cid] + (1 if cid in bat_in else 0)
        line_ids = []
        for j in range(1, n + 1):
            lid = f"FL-{cid[3:]}-{j:02d}"
            cls = "BAT" if (cid in bat_in and j == n) else CLASSES[h("cls", lid) % 6]
            attempt = 0
            serial = f"{cls}-{10000 + h('ser', lid, attempt) % 30000}"
            while serial in used:
                attempt += 1
                serial = f"{cls}-{10000 + h('ser', lid, attempt) % 30000}"
            used.add(serial)
            ended = status in ("ended", "terminated")
            cover = COVER[h("cov", lid) % 3]
            line: dict[str, Any] = {
                "lineId": lid, "contractId": cid, "serial": serial, "toolClass": cls,
                "model": MODELS[cls][h("model", lid) % 2], "status": "returned" if ended else "active",
                "returnReason": ("early_termination" if status == "terminated" else "end_of_term") if ended else None,
                "theftClaimOpen": False, "claimRef": None, "damageChargeOpen": h("dmg", lid) % 40 == 0, "chargeRef": None,
                "feeMonth": RATE[cls], "coverType": cover, "coverActive": cover != "none" and not ended, "coverUntil": None,
                "swapAllowed": h("swap", lid) % 3 != 0, "nonReturnFee": 0.0,
                "monthsOnContract": max(1, min(term, (TODAY.year - start.year) * 12 + TODAY.month - start.month)),
                "updatedAt": stamp("line", lid),
            }  # fmt: skip
            if line["coverActive"]:
                line["coverUntil"] = (TODAY + timedelta(days=30 + h("cu", lid) % 500)).isoformat()
            if line["damageChargeOpen"]:
                line["chargeRef"] = f"CHG-{4000 + h('chg', lid) % 5000}"
            lines.append(line)
            line_ids.append(lid)
        contracts.append(
            {
                "contractId": cid, "customer": customer, "market": market, "startDate": start.isoformat(),
                "endDate": end.isoformat(), "noticeDate": notice.isoformat() if notice else None, "termMonths": term,
                "status": status, "rateCardVersion": "v4", "feeMonth": 0.0, "keyAccount": key, "ownerOrg": OWNER[market],
                "renewalStatus": renewal, "lineIds": line_ids, "updatedAt": stamp("contract", cid),
            }
        )  # fmt: skip

    by_line = {ln["lineId"]: ln for ln in lines}
    for lid, serial, cls in (
        ("FL-30117-03", "CMH-48213", "CMH"), ("FL-30140-01", "CRH-44120", "CRH"), ("FL-30133-02", "BRK-51007", "BRK"),
        ("FL-30128-04", "AGR-20991", "AGR"),
    ):  # fmt: skip
        used.discard(by_line[lid]["serial"])
        by_line[lid].update({"serial": serial, "toolClass": cls, "model": MODELS[cls][0], "feeMonth": RATE[cls]})
    by_line["FL-30117-03"].update({"status": "returned", "returnReason": "end_of_term"})
    by_line["FL-30140-01"].update({"status": "returned", "returnReason": "swap", "swapAllowed": True})
    by_line["FL-30133-02"].update(
        {"status": "returned", "returnReason": "theft_recovered", "theftClaimOpen": True, "claimRef": "CLM-7781"}
    )
    by_line["FL-30128-04"].update({"status": "closed_not_returned", "nonReturnFee": 180.0})
    fixed = {"FL-30117-03", "FL-30140-01", "FL-30133-02", "FL-30128-04"}

    # 15 more open returns and 4 more lines closed without a return, picked from the active lines of live contracts
    live = [ln for ln in lines if ln["status"] == "active" and ln["toolClass"] != "BAT"]
    pick = sorted(live, key=lambda ln: h("ret", ln["lineId"]))
    for k, ln in enumerate(pick[:15]):
        ln.update({"status": "returned", "returnReason": REASONS[k % 4]})
    for ln in sorted(pick[15:], key=lambda ln: h("cnr", ln["lineId"]))[:4]:
        ln.update({"status": "closed_not_returned", "nonReturnFee": float(120 + h("fee", ln["lineId"]) % 280)})

    fee = {c["contractId"]: 0.0 for c in contracts}
    for ln in lines:
        fee[ln["contractId"]] += ln["feeMonth"]
    for c in contracts:
        c["feeMonth"] = round(fee[c["contractId"]], 2)
    contract = {c["contractId"]: c for c in contracts}

    open_lines = [ln for ln in lines if ln["lineId"] in fixed - {"FL-30128-04"}]
    open_lines += [
        ln for ln in lines
        if ln["status"] == "returned" and ln["lineId"] not in fixed
        and contract[ln["contractId"]]["status"] in ("active", "evergreen")
    ]  # fmt: skip
    returns = []
    for n, ln in enumerate(open_lines, 1):
        site = "Houston" if ln["serial"] == "CMH-48213" else SITES[h("site", ln["serial"]) % 5]
        at = AS_OF - timedelta(days=1 + h("rcv", ln["serial"]) % 20, minutes=h("rcvm", ln["serial"]) % 600)
        returns.append(
            {"returnId": f"FR-{70000 + n}", "serial": ln["serial"], "lineId": ln["lineId"], "contractId": ln["contractId"],
             "kind": KIND_OF[ln["returnReason"]], "site": site, "receivedAt": at.isoformat()}
        )  # fmt: skip

    live_contracts = [c for c in contracts if c["status"] in ("active", "evergreen") and c["contractId"] != "FC-30117"]
    chosen = ["FC-30117"] + [c["contractId"] for c in sorted(live_contracts, key=lambda c: h("ren", c["contractId"]))[:24]]
    renewals = []
    for cid in chosen:
        c = contract[cid]
        classes = [by_line[x]["toolClass"] for x in c["lineIds"]]
        cls = "CMH" if cid == "FC-30117" else classes[h("rc", cid) % len(classes)]
        cls = "CRH" if cls == "BAT" else cls
        need = TODAY + timedelta(days=19 if cid == "FC-30117" else 5 + h("need", cid) % 85)
        renewals.append(
            {"demandId": f"{cid}-R", "kind": "lease", "contractId": cid, "customer": c["customer"],
             "site": "Houston" if cid == "FC-30117" else SITES[h("rsite", cid) % 5], "needBy": need.isoformat(),
             "rateMonth": RATE[cls], "termMonths": 12 if cid == "FC-30117" else (12, 24)[h("rt", cid) % 2],
             "renew": True if cid == "FC-30117" else h("rn", cid) % 5 < 3, "toolClass": cls, "status": "open"}
        )  # fmt: skip

    history = []
    for i in range(1, 61):
        cid = f"FC-{20100 + i}"
        proposal = h("prop", cid) % 2 == 0
        renewed = frac("out", cid) < (0.75 if proposal else 0.45)
        before = float(1500 + h("fb", cid) % 9000)
        delta = (h("fd", cid) % 18 - 5) / 100
        history.append(
            {"contractId": cid, "customer": CUSTOMERS[h("hc", cid) % len(CUSTOMERS)], "market": MARKETS[h("hm", cid) % 5],
             "lines": 3 + h("hl", cid) % 18, "endedAt": (TODAY - timedelta(days=10 + h("he", cid) % 720)).isoformat(),
             "outcome": "renewed" if renewed else "lapsed", "hadProposal": proposal, "feeBefore": before,
             "feeAfter": round(before * (1 + delta), 2)}
        )  # fmt: skip
    return {"contracts": contracts, "lines": lines, "returns": returns, "renewals": renewals, "history": history,
            "proposals": [], "draftLines": []}  # fmt: skip


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - anchored on its own date, as the sandbox
    return build()


SPEC = Spec(
    source_id="fleet",
    title="Fleet contract system (synthetic)",
    schema="fleet",
    base_path="/fleet/api/v1",
    auth=Auth("api_key", header="x-api-key"),
    paging=Paging("offset", limit_param="limit", offset_param="offset", items_key="items", next_key="next", total_key="total"),
    resources=(
        Resource("contracts", "/contracts", "contractId", filters=("status", "market")),
        Resource("lines", "/contract-lines", "lineId", filters=("serial", "contractId", "status"), update=True),
        Resource("returns", "/returns", "returnId", filters=("serial",), event="fleet.return"),
        Resource("renewals", "/renewals", "demandId", filters=("toolClass",)),
        Resource("history", "/contract-history", "contractId"),
        Resource("proposals", "/proposals", "proposalId", create=True, id_format="FP-{n:05d}", event="fleet.proposal"),
        Resource("draftLines", "/draft-lines", "draftLineId", create=True, id_format="FD-{n:05d}", event="fleet.draft_line"),
    ),
    seed=seed,
)
