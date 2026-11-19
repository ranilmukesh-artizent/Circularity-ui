"""The canonical models and which source has authority over which field (docs/BACKEND_STEPS.md, B9).

Models use the namespaces of the demo's field mappings (MAPPINGS in index.html): `asset.asset_id`,
`condition.grade`, `demand.need_by` … How they relate to the demo's seven canonical models (CANON):

    asset          Asset & component v2.3      identity, owner, configuration, components, location, availability, refs
    condition      Condition & eligibility v2.1 grade, inspection, life assessment, certificates, policy
    demand         Demand opportunity v1.8      demand line, buyer, need-by, ship-to, status, purchase baseline/alternative
    intervention   Intervention v1.5            repair/refurbishment scope, cost, duration, tests
    market         (pricing inputs of Demand)   comparable sale prices, dealer offers, time to sale
    route          (logistics inputs)           lanes, rates, carriers, ETAs
    sustainability (Outcome evidence)           emission factors, footprints
    vendor         (partner eligibility)        recycler certification, yields
    outcome        Outcome (B13b)               the actual cost lines S/4HANA posted against a decision, keyed by the
                                                approval reference (the journal entry's DocumentReferenceID)
Route candidate and Decision are produced by Circularity itself (B10-B13), not by connectors; an Outcome's actuals
are read back from S/4HANA.

FIELD_AUTHORITY: when sources disagree on a field, the value of this source counts and a conflict is opened
(the demo: "Circularity names the system with authority and holds any dependent route; it never picks silently").
It follows the demo's SOURCES[*].authority labels.
"""

MODELS = ("asset", "condition", "demand", "intervention", "market", "route", "sustainability", "vendor", "outcome")

FIELD_AUTHORITY: dict[str, str] = {
    # asset
    "asset.asset_id": "eam",  # Asset identity
    "asset.owner_tenant": "lease",  # Ownership, Lessee
    "asset.lessee": "lease",
    "asset.lease_ref": "lease",
    "asset.contract_end": "lease",  # Contract term
    "asset.configuration": "plm",  # Configuration
    "asset.compatibility": "plm",
    "asset.components": "bom",  # Part structure
    "asset.location": "wms",  # Location
    "asset.availability": "wms",  # Availability
    "asset.qty": "wms",
    "asset.return_ref": "rl",  # Return receipt
    "asset.received_at": "rl",
    "asset.disposition": "rl",
    "asset.work_order_ref": "eam",  # Work order status
    # condition
    "condition.grade": "repair",  # Inspection grade (MRO)
    "condition.inspection_ref": "repair",
    "condition.test_result": "repair",  # Bench test result
    "condition.life_assessment": "eng",  # Life assessment
    "condition.requalification": "eng",
    "condition.certificates": "qms",  # Certification
    "condition.policy": "qms",  # Policy
    # demand
    "demand.demand_id": "oms",  # Order line
    "demand.ship_to": "oms",  # Ship-to
    "demand.need_by": "oms",  # Need-by date
    "demand.status": "crm",  # Opportunity stage
    "demand.purchase_baseline": "erp",  # Purchase baseline
    "demand.supplier_lead_time": "proc",  # Supplier lead time
    "demand.purchase_alternative": "proc",  # Quoted price
    "demand.service_demand": "fsm",  # Service demand
    # intervention
    "intervention.scope": "repair",  # Repair scope and hours
    "intervention.cost": "repair",
    "intervention.hours": "repair",
    # market
    "market.sale_price": "mkt",  # Market price
    "market.dealer_offer": "dlr",  # Dealer offer
    # route (logistics)
    "route.lane_rate": "tms",  # Lane rate
    "route.carrier": "tms",  # Carrier booking
    "route.eta": "tms",  # ETA
    # sustainability, vendor
    "sustainability.emission_factor": "esg",  # Emissions factor
    "vendor.certification": "rcy",  # Vendor certification
    # outcome (B13b): actual costs are SAP S/4HANA's (K1, the book of record for actual cost)
    "outcome.line": "erp",
    "outcome.accounting_document": "erp",
}


def authority(model: str, field: str) -> str | None:
    """The source with authority over model.field (a nested field like certificates[0].expires uses its top field)."""
    top = field.split(".")[0].split("[")[0]
    return FIELD_AUTHORITY.get(f"{model}.{top}")
