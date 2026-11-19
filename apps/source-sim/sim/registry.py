"""The systems source-sim mocks (docs/PLAN_FULLSTACK_POC.md section 4).

Plan decision D1: only the two sources that are SAP in the demo are mocked as SAP (S/4HANA, Ariba).
Every other source keeps its demo vendor and gets a generic mock. `source_id` matches SOURCES[].id in index.html.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class System:
    source_id: str
    vendor: str
    schema: str
    style: Literal["sap-odata", "sap-ariba", "generic-rest", "sftp-csv", "unavailable"]
    base_path: str


SYSTEMS: tuple[System, ...] = (
    # SAP
    System("erp", "SAP S/4HANA", "s4", "sap-odata", "/sap/opu/odata/sap"),
    System("proc", "SAP Ariba", "ariba", "sap-ariba", "/ariba/api"),
    # generic vendor mocks
    System("crm", "Salesforce Sales Cloud", "salesforce", "generic-rest", "/salesforce/services/data/v59.0"),
    System("lease", "Oracle Lease and Finance Management", "oracle_lease", "generic-rest", "/oracle-lease/fscmRestApi"),
    System("oms", "IBM Sterling OMS", "sterling", "generic-rest", "/sterling/smcfs/restapi"),
    System("eam", "IBM Maximo", "maximo", "generic-rest", "/maximo/api"),
    System("fsm", "ServiceNow Field Service Management", "servicenow", "generic-rest", "/servicenow/api/now"),
    System("plm", "Siemens Teamcenter", "teamcenter", "generic-rest", "/teamcenter/tc/rest"),
    System("bom", "Aras Innovator", "aras", "generic-rest", "/aras/InnovatorServer/odata"),
    System("qms", "MasterControl", "mastercontrol", "generic-rest", "/mastercontrol/mc/api"),
    System("eng", "Bentley AssetWise", "assetwise", "generic-rest", "/assetwise/api"),
    System("wms", "Manhattan Active Warehouse Management", "manhattan", "generic-rest", "/manhattan/wms/api"),
    System("tms", "ShipLane TMS", "shiplane", "generic-rest", "/shiplane/v3"),
    System("rl", "Optoro", "optoro", "generic-rest", "/optoro/v1"),
    System("insp", "SafetyCulture", "safetyculture", "generic-rest", "/safetyculture"),
    System("repair", "Oracle Depot Repair", "depot_repair", "generic-rest", "/depot-repair/webservices/rest/csd"),
    System("mkt", "Ritchie Bros. Market Data", "ritchie", "generic-rest", "/ritchie/v2"),
    System("dlr", "Machinio", "machinio", "generic-rest", "/machinio/v1"),
    System("esg", "Persefoni", "persefoni", "generic-rest", "/persefoni/v1"),
    # kept as in the demo
    System("rcy", "Sims Lifecycle Services", "sims", "sftp-csv", "/sims/outbound"),
    System("iot", "AWS IoT Core", "aws_iot", "unavailable", ""),
)

BY_SOURCE_ID = {s.source_id: s for s in SYSTEMS}
