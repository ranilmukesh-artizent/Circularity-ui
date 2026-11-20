"""The systems source-sim mocks (docs/PLAN_FULLSTACK_POC.md section 4; docs/BACKEND_STEPS.md B5, B5b, B5c).

Plan decision D1: only the two sources that are SAP in the demo are mocked as SAP (S/4HANA, Ariba).
B5b: the systems on RT-1048's happy path are full vendor mocks (style "vendor"); SafetyCulture stays generic.
B5c: AWS IoT Core is a full vendor mock too; whether di uses it is di's choice (it starts not provisioned).
`source_id` matches SOURCES[].id in index.html. For the vendor mocks, base_path is the vendor host prefix and each
mock serves the vendor's real URL paths below it.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class System:
    source_id: str
    vendor: str
    schema: str
    style: Literal["sap-odata", "sap-ariba", "vendor", "generic-rest", "sftp-csv", "unavailable"]
    base_path: str


SYSTEMS: tuple[System, ...] = (
    # SAP
    System("erp", "SAP S/4HANA", "s4", "sap-odata", "/sap/opu/odata/sap"),
    System("proc", "SAP Ariba", "ariba", "sap-ariba", "/ariba/api"),
    # full vendor mocks (B5, B5b)
    System("crm", "Salesforce Sales Cloud", "salesforce", "vendor", "/salesforce/services/data/v59.0"),
    System("oms", "IBM Sterling OMS", "sterling", "vendor", "/sterling/smcfs/restapi"),
    System("eam", "IBM Maximo", "maximo", "vendor", "/maximo/api"),
    System("fsm", "ServiceNow Field Service Management", "servicenow", "vendor", "/servicenow/api/now"),
    System("lease", "Oracle Lease and Finance Management", "oracle_lease", "vendor", "/oracle-lease"),
    System("plm", "Siemens Teamcenter", "teamcenter", "vendor", "/teamcenter"),
    System("bom", "Aras Innovator", "aras", "vendor", "/aras"),
    System("qms", "MasterControl", "mastercontrol", "vendor", "/mastercontrol"),
    System("eng", "Bentley AssetWise", "assetwise", "vendor", "/assetwise"),
    System("wms", "Manhattan Active Warehouse Management", "manhattan", "vendor", "/manhattan"),
    System("tms", "Oracle Transportation Management", "otm", "vendor", "/otm"),  # replaces the demo's fictional ShipLane TMS
    System("rl", "Optoro", "optoro", "vendor", "/optoro"),
    System("repair", "Oracle Depot Repair", "depot_repair", "vendor", "/depot-repair"),
    System("mkt", "Ritchie Bros. Market Data", "ritchie", "vendor", "/ritchie"),
    System("dlr", "Machinio", "machinio", "vendor", "/machinio"),
    System("esg", "Persefoni", "persefoni", "vendor", "/persefoni"),
    System("rcy", "Sims Lifecycle Services", "sims", "sftp-csv", "/sims"),  # SFTP on port 2222; /sims is its admin view
    # generic mock (not on the happy path)
    System("insp", "SafetyCulture", "safetyculture", "generic-rest", "/safetyculture"),
    # B5c: a full mock, but di starts with it not provisioned, as in the demo (docs/BACKEND_STEPS.md, B5c)
    System("iot", "AWS IoT Core", "aws_iot", "vendor", "/aws-iot"),
)

BY_SOURCE_ID = {s.source_id: s for s in SYSTEMS}

# Vendors replaced on purpose (docs/BACKEND_STEPS.md, B5b). The frontend (index.html data) still shows the old name
# until it switches to the API (B17).
VENDOR_OVERRIDES = {"tms": "Oracle Transportation Management"}  # was the fictional "ShipLane TMS"
