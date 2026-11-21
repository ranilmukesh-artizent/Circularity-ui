"""SafetyCulture iAuditor (insp): inspection reports, condition grades, photos, checklist results (SOURCES.insp).

OAuth 2.0 client credentials; offset paging (?limit=&offset=, body {data, next_offset, total}). As iAuditor clients
do, the adapter lists GET /audits/search (id + modified_at; ?modified_after= for delta reads) and fetches each audit
with GET /audits/{audit_id}. Media are counted from the audit (media_count); the files themselves are not fetched.

Facts (insp is not the authority over the grade or the inspection reference: Oracle Depot Repair is, so a different
grade here opens a conflict that names repair)
    condition.<asset_id>  grade ("Grade B" → B), inspection_ref (document_no), photo_count, inspection_status,
                          inspected_at, inspection_score, inspector, checklist, inspection_template
    asset.<asset_id>      case_ref (header return_reference)
The demo's mapping (MAPPINGS.insp): grade_text "Grade B" → condition.grade B "Grade table v3"; media_count →
condition.photo_count "Integer"; audit_id → condition.inspection_ref INS-xxxxx "Reference prefix". RT-1048's
inspection lives in Depot Repair, so the examples are reproduced on other assets (e.g. RT-1049).
"""

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import generic_pages, source_clock, utc
from di.connectors.http import OAuthClientCredentials, SourceClient


def grade_v3(text: str | None) -> str | None:
    """'Grade B' → 'B'."""
    if not text:
        return None
    letter = text.strip().removeprefix("Grade").strip()[:1].upper()
    return letter if letter.isalpha() else None


class SafetyCultureAdapter(Adapter):
    source_id = "insp"
    base_path = "/safetyculture"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials("/oauth/token", "di-connector", secret or "insp-demo-secret")

    def resources(self):
        return [Resource("audits", self.read_audits)]

    def read_audits(self, client: SourceClient, since):
        stamp = source_clock(client)
        hits = list(
            generic_pages(
                client,
                "/audits/search",
                since,
                items_key="data",
                next_key="next_offset",
                next_param="offset",
                size_param="limit",
                since_param="modified_after",
            )
        )
        for hit, _ in hits:
            if hit.get("archived"):
                continue
            r = client.request("GET", f"/audits/{hit['audit_id']}")
            yield Record("audits", hit["audit_id"], r.json(), str(r.request.url), stamp)

    def map(self, record: Record) -> list[Fact]:
        a = record.payload
        head = a.get("header_items") or {}
        key = a.get("asset_id") or head.get("asset_id")
        if not key:
            return []
        data = a.get("audit_data") or {}
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        fact(
            "asset",
            "case_ref",
            head.get("return_reference"),
            "header_items.return_reference",
            head.get("return_reference"),
            "Pass-through",
        )
        fact("condition", "grade", grade_v3(a.get("grade_text")), "grade_text", a.get("grade_text"), "Grade table v3")
        fact("condition", "inspection_ref", data.get("document_no"), "audit_id", a.get("audit_id"), "Reference prefix")
        fact("condition", "photo_count", a.get("media_count"), "media_count", a.get("media_count"), "Integer")
        fact("condition", "inspection_status", data.get("status"), "audit_data.status", data.get("status"), "Pass-through")
        done = data.get("date_completed")
        fact("condition", "inspected_at", utc(done), "audit_data.date_completed", done, "Timestamp to UTC")
        fact(
            "condition",
            "inspection_score",
            data.get("score_percentage"),
            "audit_data.score_percentage",
            data.get("score_percentage"),
            "Percent",
        )
        fact(
            "condition",
            "inspector",
            (data.get("authorship") or {}).get("author"),
            "audit_data.authorship.author",
            None,
            "Pass-through",
        )
        tmpl = ((a.get("template_data") or {}).get("metadata") or {}).get("name")
        fact("condition", "inspection_template", tmpl, "template_data.metadata.name", tmpl, "Pass-through")
        items = a.get("items") or []
        if items:
            fact(
                "condition",
                "checklist",
                [{"label": i.get("label"), "response": i.get("response"), "action": i.get("action_required")} for i in items],
                "items",
                None,
                "Checklist responses",
            )
        return out


ADAPTER = SafetyCultureAdapter()
