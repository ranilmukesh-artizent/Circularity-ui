"""Bentley AssetWise (eng): life assessments, requalification standards, engineering limits (the demo's SOURCES.eng).
Read only.

The engineering data warehouse over OData v4 (/assetwise/eB/Service/OData/Engineering/) with a Bentley IMS bearer
token (client credentials, scope assetwise-odata). Collections are paged by the server (@odata.nextLink; we ask for
Prefer: odata.maxpagesize=100).
- assessments: one record per LifeAssessment (one per asset), oldest change first; delta with
  $filter=MODIFIED_ON gt <cursor>. The cursor is the newest MODIFIED_ON. VALIDITY is worked out by AssetWise at read
  time, so an approval that expires without being changed is seen at the next full read (the hourly safety sync).
- standards: one record per asset class joining its Standards and EngineeringLimits. Reference lists, read in full.

Facts (eng has authority over life assessment and requalification)
    condition.<ASSET_ID>    life_assessment ("36 months", or the source's text such as "Below minimum"), life_months,
                            life_range {low, high}, life_confidence, standard, requalification, assessment_status,
                            assessment_approval, assessment_approved_by, assessment_valid_until, assessment_validity,
                            assessment_ref, next_inspection, assessed_at
    condition.class:<cls>   requal_interval_months, min_life_months, standards, limits
The demo's mapping: RUL_MONTHS 36 → condition.life_assessment "36 months" (Months; source & confidence retained);
STANDARD_REF IEC 60034-1 → condition.standard (Pass-through); REQUAL_STATUS APPROVED → approved (Status map; recorded as
condition.requalification, the field eng has authority over).
"""

from collections.abc import Iterator
from datetime import UTC, datetime

from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep
from di.connectors.http import OAuthClientCredentials, SourceClient
from di.services.canonical.store import Fact

PAGE = 100


def odata_z(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_iso(z: str | None) -> str | None:
    return datetime.fromisoformat(z.replace("Z", "+00:00")).astimezone(UTC).isoformat() if z else None


class AssetWiseAdapter(Adapter):
    source_id = "eng"
    base_path = "/assetwise/eB/Service/OData/Engineering"

    def auth(self, conn=None, secret=None):
        return OAuthClientCredentials(
            self.origin(conn) + "/assetwise/ims/connect/token",
            "service-circularity-di",
            secret or "circularity-demo-ims-secret",
            form=True,
            extra={"scope": "assetwise-odata"},
        )

    def resources(self):
        return [Resource("assessments", self.read_assessments), Resource("standards", self.read_standards, delta=False)]

    # ------------------------------------------------------------- reading
    def collection(self, client: SourceClient, path: str, params: dict) -> Iterator[tuple[dict, str]]:
        url = path
        q: dict | None = params
        while url:
            r = client.request("GET", url, params=q, headers={"Prefer": f"odata.maxpagesize={PAGE}"})
            body = r.json()
            client.note_records(len(body["value"]))
            for row in body["value"]:
                yield row, str(r.request.url)
            url, q = body.get("@odata.nextLink"), None

    def read_assessments(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        params = {"$orderby": "MODIFIED_ON,ASSESSMENT_ID"}
        if since:
            params["$filter"] = f"MODIFIED_ON gt {odata_z(since)}"
        for row, url in self.collection(client, "/LifeAssessments", params):
            yield Record("assessments", row["ASSESSMENT_ID"], row, url, utc_iso(row.get("MODIFIED_ON")))

    def read_standards(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - the adapter read interface; this read is always full
        standards = [r for r, _ in self.collection(client, "/Standards", {"$orderby": "STANDARD_ID"})]
        limits = [r for r, _ in self.collection(client, "/EngineeringLimits", {"$orderby": "LIMIT_ID"})]
        url = client.url("/Standards")
        for cls in sorted({s["ASSET_CLASS"] for s in standards if s.get("ASSET_CLASS")}):
            payload = {
                "ASSET_CLASS": cls,
                "standards": [s for s in standards if s.get("ASSET_CLASS") == cls],
                "limits": [x for x in limits if x.get("ASSET_CLASS") == cls],
            }
            yield Record("standards", cls, payload, url)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "standards":
            return keep(self._standards(p))
        key = p["ASSET_ID"]
        rul = p.get("RUL_MONTHS")
        life = f"{rul} months" if rul is not None else p.get("LIFE_TEXT")

        def c(field, value, source_field, source_value, transform="Pass-through"):
            return Fact("condition", key, field, value, source_field, source_value, transform)

        def low(name):
            return (p.get(name) or "").lower() or None

        return keep(
            [
                c(
                    "life_assessment",
                    life,
                    "RUL_MONTHS" if rul is not None else "LIFE_TEXT",
                    rul if rul is not None else p.get("LIFE_TEXT"),
                    "Months; source & confidence retained",
                ),
                c("life_months", rul, "RUL_MONTHS", rul, "Integer months"),
                c(
                    "life_range",
                    {"low": p["RUL_LOW_MONTHS"], "high": p["RUL_HIGH_MONTHS"]} if p.get("RUL_LOW_MONTHS") is not None else None,
                    "RUL_LOW_MONTHS / RUL_HIGH_MONTHS",
                    [p.get("RUL_LOW_MONTHS"), p.get("RUL_HIGH_MONTHS")],
                    "Months",
                ),
                c("life_confidence", low("CONFIDENCE"), "CONFIDENCE", p.get("CONFIDENCE"), "Confidence map"),
                c("standard", p.get("STANDARD_REF"), "STANDARD_REF", p.get("STANDARD_REF")),
                c("requalification", low("REQUAL_STATUS"), "REQUAL_STATUS", p.get("REQUAL_STATUS"), "Status map"),
                c("assessment_status", low("ASSESSMENT_STATUS"), "ASSESSMENT_STATUS", p.get("ASSESSMENT_STATUS"), "Status map"),
                c("assessment_approval", low("APPROVAL_STATUS"), "APPROVAL_STATUS", p.get("APPROVAL_STATUS"), "Status map"),
                c("assessment_approved_by", p.get("APPROVED_BY"), "APPROVED_BY", p.get("APPROVED_BY")),
                c(
                    "assessment_valid_until",
                    utc_iso(p.get("VALID_UNTIL")),
                    "VALID_UNTIL",
                    p.get("VALID_UNTIL"),
                    "Timestamp (UTC)",
                ),
                c("assessment_validity", low("VALIDITY"), "VALIDITY", p.get("VALIDITY"), "Status map"),
                c("assessment_ref", p["ASSESSMENT_ID"], "ASSESSMENT_ID", p["ASSESSMENT_ID"]),
                c(
                    "next_inspection",
                    p.get("NEXT_INSPECTION_DATE"),
                    "NEXT_INSPECTION_DATE",
                    p.get("NEXT_INSPECTION_DATE"),
                    "ISO date",
                ),
                c("assessed_at", p.get("ASSESSED_AT"), "ASSESSED_AT", p.get("ASSESSED_AT"), "Timestamp (UTC)"),
            ]
        )

    def _standards(self, p: dict) -> list[Fact]:
        key = f"class:{p['ASSET_CLASS']}"
        primary = next((s for s in p["standards"] if s.get("MIN_RUL_MONTHS") is not None), None) or (p["standards"] or [{}])[0]
        return [
            Fact(
                "condition",
                key,
                "requal_interval_months",
                primary.get("REQUAL_INTERVAL_MONTHS"),
                "REQUAL_INTERVAL_MONTHS",
                primary.get("REQUAL_INTERVAL_MONTHS"),
                "Integer months",
            ),
            Fact(
                "condition",
                key,
                "min_life_months",
                primary.get("MIN_RUL_MONTHS"),
                "MIN_RUL_MONTHS",
                primary.get("MIN_RUL_MONTHS"),
                "Integer months",
            ),
            Fact(
                "condition",
                key,
                "standards",
                [
                    {
                        "ref": s["STANDARD_REF"],
                        "id": s["STANDARD_ID"],
                        "title": s.get("TITLE"),
                        "requal_months": s.get("REQUAL_INTERVAL_MONTHS"),
                    }
                    for s in p["standards"]
                ],
                "STANDARD_REF",
                [s["STANDARD_REF"] for s in p["standards"]],
                "Pass-through",
            ),
            Fact(
                "condition",
                key,
                "limits",
                [
                    {
                        "id": x["LIMIT_ID"],
                        "parameter": x["PARAMETER"],
                        "type": (x.get("LIMIT_TYPE") or "").lower(),
                        "value": x.get("LIMIT_VALUE"),
                        "unit": x.get("UNIT"),
                        "standard": x.get("STANDARD_REF"),
                        "routes": x.get("APPLIES_TO_ROUTES") or [],
                    }
                    for x in p["limits"]
                ],
                "LIMIT_VALUE",
                [f"{x['LIMIT_ID']} {x.get('LIMIT_TYPE')} {x.get('LIMIT_VALUE')} {x.get('UNIT')}" for x in p["limits"]],
                "Unit kept",
            ),
        ]


ADAPTER = AssetWiseAdapter()
