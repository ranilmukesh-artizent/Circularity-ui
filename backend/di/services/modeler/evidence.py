"""Evidence types and the evidence on file for a case (plan 9, P9-1.2; research B section 5). Implements registry
entry I-3: `EvidenceType`, `Evidence`, `evidence_of(case, type)`.

Owns: `EVIDENCE_TYPES` (the id and label of every evidence record a gate of the catalogue asks for), the `Evidence`
record and the pure lookup of the newest valid record of one type on a case.
Never does: read the canonical store (`di.services.cases.gate_hold` copies the `compliance` records onto the case as
`case["evidenceRecords"]`), decide whether a gate passes (`gates.py`), or read the clock (callers pass `as_of`).

A record on a case is a mapping `{type, source, at, result, value, valid_until}`; `at` and `valid_until` are datetimes
or ISO 8601 strings (a case is JSON). A record that does not parse is ignored.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

EvidenceType = str  # an id that is a key of EVIDENCE_TYPES

EVIDENCE_TYPES: dict[str, str] = {
    "battery_passport": "Battery passport",
    "battery_safety_class": "Battery safety class and packaging",
    "battery_soh": "Battery state of health",
    "carbon_provenance": "Carbon factor provenance",
    "case_material_report": "Mass, material and treatment category",
    "config_wipe": "Configuration-wipe certificate",
    "contract_clause": "Contract clause",
    "contract_line": "Fleet contract line",
    "controller_signoff": "Data-controller sign-off",
    "covered_list_clearance": "Covered-list clearance",
    "customer_consent": "Customer consent",
    "data_wipe": "Data-wipe certificate",
    "decontamination": "Decontamination record",
    "destination_listing": "Destination listing",
    "destruction_exception": "Destruction exception",
    "destruction_record": "Destruction record",
    "device_registry_check": "Registry status check",
    "downstream_declaration": "Downstream declaration",
    "export_classification": "Export classification and screening",
    "field_safety_status": "Field safety notice status",
    "inventory_match": "Network inventory match",
    "lease_residual": "Lease residual value",
    "lien_release": "Lien release",
    "market_duties_record": "Market duties, UDI and service record",
    "odometer_statement": "Odometer statement",
    "product_passport": "Product passport",
    "recall_check": "Recall check",
    "recycler_permit": "Recycler permit",
    "refurb_assessment": "Servicing-versus-remanufacturing assessment",
    "reporting_status": "Buyer reporting status",
    "repurpose_fitness": "Repurposing fitness documentation",
    "service_record": "Service and certification record",
    "shipment_consent": "Shipment consent",
    "single_use_clearance": "Single-use reprocessing clearance",
    "telematics_reading": "Telematics reading",
    "test_certificate": "Test certificate",
    "title_brand": "Title brand record",
    "title_status": "Title and lien search",
    "treatment_code": "Treatment code (R or D)",
    "treatment_facility_authorisation": "Treatment facility authorisation",
    "vendor_certificate": "Vendor certificate",
    "vin_recall": "VIN recall result",
    "weee_transfer_documents": "Transfer documents",
}


def label_of(evidence_type: str) -> str:
    """The label of an evidence type (the id itself when unknown)."""
    return EVIDENCE_TYPES.get(evidence_type, evidence_type)


@dataclass(frozen=True)
class Evidence:
    type: str
    source: str
    at: datetime
    result: Literal["pass", "fail"]
    value: Mapping[str, Any]
    valid_until: datetime | None = None


def parse_time(v: Any) -> datetime | None:
    """A datetime (naive means UTC) from a datetime or an ISO 8601 string; None when it is neither."""
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(v, datetime):
        return None
    return v if v.tzinfo else v.replace(tzinfo=UTC)


def _record(r: Any) -> Evidence | None:
    if not isinstance(r, Mapping) or r.get("result") not in ("pass", "fail"):
        return None
    at = parse_time(r.get("at"))
    if at is None or not isinstance(r.get("type"), str):
        return None
    value = r.get("value")
    return Evidence(
        r["type"], str(r.get("source") or ""), at, r["result"], value if isinstance(value, Mapping) else {},
        parse_time(r.get("valid_until")),
    )  # fmt: skip


def records_of(case: Mapping[str, Any]) -> list[Evidence]:
    """Every parsable record on the case."""
    return [e for r in case.get("evidenceRecords") or [] if (e := _record(r)) is not None]


def evidence_of(case: Mapping[str, Any], type: str, as_of: datetime | None = None) -> Evidence | None:
    """The newest record of that type on the case: with `as_of`, only one made at or before it that has not expired by
    it (`valid_until` after `as_of`); without it, the newest record (no clock is read). Pure."""
    best: Evidence | None = None
    for e in records_of(case):
        if e.type != type:
            continue
        if as_of is not None and (e.at > as_of or (e.valid_until is not None and e.valid_until <= as_of)):
            continue
        if best is None or e.at >= best.at:
            best = e
    return best
