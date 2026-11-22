"""IBM Maximo Manage (eam): installed base, asset registry, work orders, failure history, criticality (SOURCES.eam).

OSLC JSON API: apikey header, `lean=1`, `oslc.select`, `oslc.where`, `oslc.pageSize` + `responseInfo.nextPage`.
Delta reads by `changedate>"<cursor>"`. Times come back in the server's zone (+05:30) and are stored in UTC.

Resources
    asset       GET /os/mxasset (with assetmeter{*}, assetspec{*}); one record per asset
    workorders  GET /os/mxwo (with failurereport{*}); grouped per asset, since an asset's service history is a summary
                of all its orders. A delta read asks which orders changed, then re-reads every order of those assets.
Facts
    asset.<ASSETNUM>      asset_id (eam has authority over identity), site, eam_location, description, asset_type,
                          operating_status, priority, criticality, manufacturer, eam_serial, install_date,
                          purchase_price, maintenance_cost, owner_tenant, run_hours, rated_power_kw, nameplate
                          work_order_ref/_status/_type (the refurbishment/teardown order, else the latest open order;
                          eam has authority), work_order_count, failure_codes, failure_history, labour_cost,
                          material_cost, case_ref (EXTERNALREFID of the return inspection, RT-xxxx)
    condition.<ASSETNUM>  grade (CONDITIONCODE B+ → B; eam is not the authority), condition_code, service_date
                          (LASTSERVICEDATE to UTC), inspection_work_order/_status (the return inspection),
                          next_inspection_due
The demo's mapping (MAPPINGS.eam), reproduced for MTR-2041: ASSETNUM → asset.asset_id; CONDITIONCODE B+ →
condition.grade B "Grade table v3 (B+ → B); source value kept"; RATED_PWR 55000 W → 55 kW "Unit normalised W → kW"
(field rated_power_kw); LASTSERVICEDATE 2026-03-14T08:20:00+05:30 → condition.service_date 2026-03-14T02:50:00Z.
"""

from datetime import UTC, datetime
from decimal import Decimal

from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import ApiKey, SourceClient
from di.services.canonical.store import Fact

PAGE = 200
CHUNK = 40  # assets per `assetnum in [...]` re-read
OPEN = ("WAPPR", "APPR", "WSCH", "WMATL", "INPRG")
ASSET_SELECT = (
    "assetnum,siteid,location,description,assettype,status,priority,criticality,manufacturer,serialnum,installdate,"
    "purchaseprice,totalcost,conditioncode,lastservicedate,pluscustomer,changedate,assetmeter{*},assetspec{*}"
)
WO_SELECT = (
    "wonum,siteid,description,status,statusdate,worktype,assetnum,reportdate,targstartdate,actstart,actfinish,"
    "failurecode,problemcode,actlabhrs,actlabcost,actmatcost,estlabhrs,estlabcost,estmatcost,externalrefid,changedate,"
    "failurereport{failurecode,description,type,linenum}"
)
SITES = {"WH01": "Warehouse 1", "WH02": "Warehouse 2", "RC01": "Repair centre"}


def to_utc(v: str | None) -> str | None:
    """'2026-03-14T08:20:00+05:30' → '2026-03-14T02:50:00Z'."""
    if not v:
        return None
    return datetime.fromisoformat(v).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def cursor(v: str | None) -> str | None:
    """A Maximo time as the delta cursor (ISO 8601 UTC, +00:00)."""
    return datetime.fromisoformat(v).astimezone(UTC).isoformat() if v else None


def site_name(site: str | None) -> str | None:
    if not site:
        return None
    return SITES.get(site) or (f"Site {int(site[2:])}" if site.startswith("ST") and site[2:].isdigit() else site)


def grade_v3(code: str | None) -> str | None:
    """Grade table v3: the condition code's letter (B+ → B, C- → C)."""
    return code.strip()[0].upper() if code and code.strip() and code.strip()[0].isalpha() else None


class MaximoAdapter(Adapter):
    source_id = "eam"
    base_path = "/maximo/api"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return ApiKey("apikey", secret or "circularity-demo-maximo-apikey")

    def resources(self):
        return [Resource("asset", self.read_assets), Resource("workorders", self.read_workorders)]

    # ------------------------------------------------------------------ reading
    def _query(self, client: SourceClient, os_name: str, select: str, where: str | None):
        """Every member of an OSLC query, following responseInfo.nextPage to the end."""
        query = {"lean": "1", "oslc.select": select, "oslc.pageSize": str(PAGE)}
        if where:
            query["oslc.where"] = where
        params: dict[str, str] | None = query
        url: str | None = f"/os/{os_name}"
        while url:
            r = client.request("GET", url, params=params)
            body = r.json()
            members = body.get("member") or []
            client.note_records(len(members))
            for m in members:
                yield m, str(r.request.url)
            url = ((body.get("responseInfo") or {}).get("nextPage") or {}).get("href")
            params = None  # the next-page link carries the query

    @staticmethod
    def _since(since: str | None) -> str | None:
        return f'changedate>"{since}"' if since else None

    def read_assets(self, client, since):
        for a, url in self._query(client, "mxasset", ASSET_SELECT, self._since(since)):
            yield Record("asset", f"{a['assetnum']}|{a['siteid']}", a, url, cursor(a.get("changedate")))

    def read_workorders(self, client, since):
        groups: dict[str, list[dict]] = {}
        urls: dict[str, str] = {}
        if since is None:
            for wo, url in self._query(client, "mxwo", WO_SELECT, None):
                if wo.get("assetnum"):
                    groups.setdefault(wo["assetnum"], []).append(wo)
                    urls[wo["assetnum"]] = url
        else:
            changed = sorted(
                {
                    wo["assetnum"]
                    for wo, _ in self._query(client, "mxwo", "wonum,assetnum", self._since(since))
                    if wo.get("assetnum")
                }
            )
            for i in range(0, len(changed), CHUNK):
                chunk = changed[i : i + CHUNK]
                where = "assetnum in [" + ",".join(f'"{a}"' for a in chunk) + "]"
                for wo, url in self._query(client, "mxwo", WO_SELECT, where):
                    groups.setdefault(wo["assetnum"], []).append(wo)
                    urls[wo["assetnum"]] = url
        for assetnum, wos in groups.items():
            newest = max((cursor(w.get("changedate")) or "" for w in wos), default="") or None
            yield Record("workorders", assetnum, {"assetnum": assetnum, "workorders": wos}, urls[assetnum], newest)

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "asset":
            return self._map_asset(record.payload)
        if record.resource == "workorders":
            return self._map_workorders(record.payload)
        return []

    def _map_asset(self, a: dict) -> list[Fact]:
        key = a["assetnum"]
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        fact("asset", "asset_id", key, "ASSETNUM", key, "Pass-through; identity key")
        fact("asset", "site", a.get("siteid"), "SITEID", a.get("siteid"), "Pass-through")
        fact("asset", "site_name", site_name(a.get("siteid")), "SITEID", a.get("siteid"), "Site code lookup")
        fact("asset", "eam_location", a.get("location"), "LOCATION", a.get("location"), "Pass-through")
        fact("asset", "description", a.get("description"), "DESCRIPTION", a.get("description"), "Pass-through")
        fact("asset", "asset_type", a.get("assettype"), "ASSETTYPE", a.get("assettype"), "Pass-through")
        st = a.get("status")
        fact("asset", "operating_status", a.get("status_description") or st, "STATUS", st, "Status description")
        fact("asset", "priority", a.get("priority"), "PRIORITY", a.get("priority"), "Integer (1 highest)")
        fact("asset", "criticality", a.get("criticality"), "CRITICALITY", a.get("criticality"), "Integer (10 most critical)")
        fact("asset", "manufacturer", a.get("manufacturer"), "MANUFACTURER", a.get("manufacturer"), "Pass-through")
        # Maximo's SERIALNUM differs from the serial FSM holds for the same asset in the seed, so it is kept apart
        fact("asset", "eam_serial", a.get("serialnum"), "SERIALNUM", a.get("serialnum"), "Pass-through")
        inst = a.get("installdate")
        fact("asset", "install_date", inst[:10] if inst else None, "INSTALLDATE", inst, "Date (site time)")
        if a.get("purchaseprice") is not None:
            fact(
                "asset",
                "purchase_price",
                a["purchaseprice"],
                "PURCHASEPRICE",
                f"{a['purchaseprice']:.2f} USD",
                "Base currency USD",
            )
        if a.get("totalcost") is not None:
            fact("asset", "maintenance_cost", a["totalcost"], "TOTALCOST", f"{a['totalcost']:.2f} USD", "Base currency USD")
        fact("asset", "owner_tenant", a.get("pluscustomer"), "PLUSCUSTOMER", a.get("pluscustomer"), "Pass-through")
        for m in a.get("assetmeter") or []:
            if m.get("metername") == "RUNHOURS" and m.get("lastreading") is not None:
                hrs = m["lastreading"]
                fact(
                    "asset",
                    "run_hours",
                    hrs,
                    "ASSETMETER.RUNHOURS",
                    f"{hrs:,.0f} {m.get('measureunitid') or 'HOURS'}",
                    "Meter reading",
                )
        nameplate = {}
        for s in a.get("assetspec") or []:
            attr = s.get("assetattrid")
            if s.get("numvalue") is not None:
                nameplate[attr.lower()] = f"{s['numvalue']:g} {s.get('measureunitid') or ''}".strip()
            elif s.get("alnvalue") is not None:
                nameplate[attr.lower()] = s["alnvalue"]
            if attr == "RATED_PWR" and s.get("numvalue") is not None:
                w = Decimal(str(s["numvalue"]))
                unit = (s.get("measureunitid") or "W").upper()
                kw = float(w / 1000) if unit == "W" else float(w)
                fact(
                    "asset",
                    "rated_power_kw",
                    kw,
                    "RATED_PWR",
                    f"{w:f}".rstrip("0").rstrip(".") + f" {unit}",
                    "Unit normalised W → kW",
                )
        if nameplate:
            fact("asset", "nameplate", nameplate, "ASSETSPEC", None, "Attributes collected")
        code = a.get("conditioncode")
        fact("condition", "grade", grade_v3(code), "CONDITIONCODE", code, "Grade table v3 (B+ → B); source value kept")
        fact("condition", "condition_code", code, "CONDITIONCODE", code, "Pass-through")
        lsd = a.get("lastservicedate")
        fact("condition", "service_date", to_utc(lsd), "LASTSERVICEDATE", lsd, "Timestamp to UTC")
        return out

    def _map_workorders(self, p: dict) -> list[Fact]:
        key = p["assetnum"]
        wos = sorted(p["workorders"], key=lambda w: (w.get("reportdate") and to_utc(w["reportdate"])) or "")
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        # the order that matters for the case: refurbishment/teardown first, else the latest open order
        refurb = [w for w in wos if w.get("worktype") in ("REFURB", "TDOWN") and w.get("status") != "CAN"]
        open_ = [w for w in wos if w.get("status") in OPEN]
        current = (refurb or open_ or [None])[-1]
        if current:
            fact(
                "asset",
                "work_order_ref",
                current["wonum"],
                "WONUM",
                current["wonum"],
                "Refurbishment order, else latest open order",
            )
            fact("asset", "work_order_status", current.get("status"), "STATUS", current.get("status"), "Pass-through")
            fact("asset", "work_order_type", current.get("worktype"), "WORKTYPE", current.get("worktype"), "Pass-through")
        fact("asset", "work_order_count", len(wos), "WONUM", None, "Count of work orders")
        history, codes = [], []
        for w in wos:
            frs = sorted(w.get("failurereport") or [], key=lambda f: f.get("linenum") or 0)
            if not frs and not w.get("problemcode"):
                continue
            by_type = {f.get("type"): f.get("failurecode") for f in frs}
            problem = by_type.get("PROBLEM") or w.get("problemcode")
            if problem and problem not in codes:
                codes.append(problem)
            history.append(
                {
                    "wonum": w["wonum"],
                    "date": to_utc(w.get("actstart") or w.get("reportdate")),
                    "failure_class": w.get("failurecode"),
                    "problem": problem,
                    "cause": by_type.get("CAUSE"),
                    "remedy": by_type.get("REMEDY"),
                }
            )
        fact("asset", "failure_codes", codes, "FAILUREREPORT.FAILURECODE", None, "Problem codes, oldest first")
        fact("asset", "failure_history", history, "FAILUREREPORT", None, "Problem / cause / remedy per order")
        lab = sum(Decimal(str(w.get("actlabcost") or 0)) for w in wos)
        mat = sum(Decimal(str(w.get("actmatcost") or 0)) for w in wos)
        fact("asset", "labour_cost", float(lab), "ACTLABCOST", f"{lab:.2f} USD", "Sum over work orders (base currency USD)")
        fact("asset", "material_cost", float(mat), "ACTMATCOST", f"{mat:.2f} USD", "Sum over work orders (base currency USD)")
        insp = [w for w in wos if w.get("worktype") == "INSP" and (w.get("externalrefid") or "").startswith("RT-")]
        if insp:
            ri = insp[-1]
            fact("asset", "case_ref", ri["externalrefid"], "EXTERNALREFID", ri["externalrefid"], "Pass-through")
            fact("condition", "inspection_work_order", ri["wonum"], "WONUM", ri["wonum"], "Return inspection order")
            fact("condition", "inspection_work_order_status", ri.get("status"), "STATUS", ri.get("status"), "Pass-through")
        nxt = [w for w in wos if w.get("worktype") == "INSP" and w.get("status") in OPEN and w not in insp]
        if nxt and nxt[-1].get("targstartdate"):
            t = nxt[-1]["targstartdate"]
            fact("condition", "next_inspection_due", to_utc(t), "TARGSTARTDATE", t, "Timestamp to UTC")
        return out


ADAPTER = MaximoAdapter()
