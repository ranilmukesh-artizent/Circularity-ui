"""Bentley AssetWise (eng): life assessments, requalification standards, engineering limits (the demo's SOURCES.eng).
Read only.

OAuth client credentials, $top/continuationToken paging, `?updated_since=` deltas (see oracle_lease.GenericAdapter).
- assessments: one record per assessment (one per asset). Delta.
- standards: one record per asset class joining its standards and engineering limits. Reference lists, read in full.

Facts (eng has authority over life assessment and requalification)
    condition.<ASSET_ID>    life_assessment ("36 months", or the source's text such as "Below minimum"), life_months,
                            life_range {low, high}, life_confidence, standard, requalification, assessment_status,
                            assessment_ref, next_inspection, assessed_at
    condition.class:<cls>   requal_interval_months, min_life_months, standards, limits
The demo's mapping: RUL_MONTHS 36 → condition.life_assessment "36 months" (Months; source & confidence retained);
STANDARD_REF IEC 60034-1 → condition.standard (Pass-through); REQUAL_STATUS APPROVED → approved (Status map; recorded as
condition.requalification, the field eng has authority over).
"""

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep


class AssetWiseAdapter(GenericAdapter):
    source_id = "eng"
    base_path = "/assetwise/api"
    items_key, next_key, next_param, size_param, page_size = "items", "continuationToken", "continuationToken", "$top", 200

    def resources(self):
        return [
            Resource("assessments", lambda c, s: self.flat(c, "assessments", "/v1/assessments", "ASSESSMENT_ID", s)),
            Resource("standards", self.read_standards, delta=False),
        ]

    def read_standards(self, client, since):
        standards = self.read_all(client, "/v1/standards")
        limits = self.read_all(client, "/v1/limits")
        url = client.url("/v1/standards")
        for cls in sorted({s["ASSET_CLASS"] for s in standards if s.get("ASSET_CLASS")}):
            payload = {
                "ASSET_CLASS": cls,
                "standards": [s for s in standards if s.get("ASSET_CLASS") == cls],
                "limits": [x for x in limits if x.get("ASSET_CLASS") == cls],
            }
            yield Record("standards", cls, payload, url)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "standards":
            return keep(self._standards(p))
        key = p["ASSET_ID"]
        rul = p.get("RUL_MONTHS")
        life = f"{rul} months" if rul is not None else p.get("LIFE_TEXT")
        facts = [
            Fact(
                "condition",
                key,
                "life_assessment",
                life,
                "RUL_MONTHS" if rul is not None else "LIFE_TEXT",
                rul if rul is not None else p.get("LIFE_TEXT"),
                "Months; source & confidence retained",
            ),
            Fact("condition", key, "life_months", rul, "RUL_MONTHS", rul, "Integer months"),
            Fact(
                "condition",
                key,
                "life_range",
                {"low": p["RUL_LOW_MONTHS"], "high": p["RUL_HIGH_MONTHS"]} if p.get("RUL_LOW_MONTHS") is not None else None,
                "RUL_LOW_MONTHS / RUL_HIGH_MONTHS",
                [p.get("RUL_LOW_MONTHS"), p.get("RUL_HIGH_MONTHS")],
                "Months",
            ),
            Fact(
                "condition",
                key,
                "life_confidence",
                (p.get("CONFIDENCE") or "").lower() or None,
                "CONFIDENCE",
                p.get("CONFIDENCE"),
                "Confidence map",
            ),
            Fact("condition", key, "standard", p.get("STANDARD_REF"), "STANDARD_REF", p.get("STANDARD_REF"), "Pass-through"),
            Fact(
                "condition",
                key,
                "requalification",
                (p.get("REQUAL_STATUS") or "").lower() or None,
                "REQUAL_STATUS",
                p.get("REQUAL_STATUS"),
                "Status map",
            ),
            Fact(
                "condition",
                key,
                "assessment_status",
                (p.get("ASSESSMENT_STATUS") or "").lower() or None,
                "ASSESSMENT_STATUS",
                p.get("ASSESSMENT_STATUS"),
                "Status map",
            ),
            Fact("condition", key, "assessment_ref", p["ASSESSMENT_ID"], "ASSESSMENT_ID", p["ASSESSMENT_ID"], "Pass-through"),
            Fact(
                "condition",
                key,
                "next_inspection",
                p.get("NEXT_INSPECTION_DATE"),
                "NEXT_INSPECTION_DATE",
                p.get("NEXT_INSPECTION_DATE"),
                "ISO date",
            ),
            Fact("condition", key, "assessed_at", p.get("ASSESSED_AT"), "ASSESSED_AT", p.get("ASSESSED_AT"), "Timestamp (UTC)"),
        ]
        return keep(facts)

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
