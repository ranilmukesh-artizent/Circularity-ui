"""The systems source-sim mocks (docs/plan-fullstack-poc.md section 4; docs/backend-steps.md B5, B5b, B5c).

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
    # B5c: a full mock, but di starts with it not provisioned, as in the demo (docs/backend-steps.md, B5c)
    System("iot", "AWS IoT Core", "aws_iot", "vendor", "/aws-iot"),
)

BY_SOURCE_ID = {s.source_id: s for s in SYSTEMS}

# Plan 6 A3: the Connection Fabric's catalogue (systems a person can connect; not demo sources). Each has a generic
# mock (sim/generic/specs/catalog_*.py), synthetic like every mock here, so that connecting one really reads records.
CATALOG_SYSTEMS: tuple[System, ...] = (
    System("workday", "Workday HCM", "cat_workday", "generic-rest", "/workday/ccx/api/v1/northfield"),
    System("jira", "Atlassian Jira", "cat_jira", "generic-rest", "/jira/rest/api/3"),
    System("confluence", "Atlassian Confluence", "cat_confluence", "generic-rest", "/confluence/wiki/api/v2"),
    System("postgres", "PostgreSQL", "cat_postgres", "generic-rest", "/postgres/rest/v1"),
    System("mysql", "MySQL", "cat_mysql", "generic-rest", "/mysql/api/v1"),
    System("sqlserver", "Microsoft SQL Server", "cat_sqlserver", "generic-rest", "/sqlserver/api/v1"),
    System("s3", "Amazon S3", "cat_s3", "generic-rest", "/s3/northfield-partner-drop"),
    System("azureblob", "Azure Blob Storage", "cat_azureblob", "generic-rest", "/azureblob/partner-files"),
    System("excel", "Microsoft Excel and SharePoint", "cat_excel", "generic-rest", "/excel/v1.0/sites/northfield/drive"),
    System("dynamics", "Microsoft Dynamics 365", "cat_dynamics", "generic-rest", "/dynamics/api/data/v9.2"),
    System("ebs", "Oracle E-Business Suite", "cat_ebs", "generic-rest", "/ebs/webservices/rest/ap"),
    System("netsuite", "Oracle NetSuite", "cat_netsuite", "generic-rest", "/netsuite/services/rest/record/v1"),
    System("teams", "Microsoft Teams", "cat_teams", "generic-rest", "/teams/v1.0"),
    System("gdrive", "Google Drive", "cat_gdrive", "generic-rest", "/gdrive/drive/v3"),
    System("snowflake", "Snowflake", "cat_snowflake", "generic-rest", "/snowflake/api/v2/databases/CIRCULARITY/schemas/HISTORY"),
)
CATALOG_BY_ID = {s.source_id: s for s in CATALOG_SYSTEMS}

# Plan 8 (MVP-9.2): full vendor mocks beyond the demo's sources, for the platform's own stories (a second PLM). Not in
# SYSTEMS, so the demo's systems and counts stay as they were; /_sim/systems lists them after the demo's.
EXTRA_SYSTEMS: tuple[System, ...] = (
    System("plm_wc", "PTC Windchill", "windchill", "vendor", "/Windchill"),
    # Plan 9 P9-6.1: the device-recommerce mocks (sim/seed/devices.py), generic and synthetic
    System("dvreg", "Device Registry", "device_registry", "generic-rest", "/device-registry/v1"),
    System("dvlab", "Device Lab", "device_lab", "generic-rest", "/device-lab/v1"),
    System("dvmkt", "Device Market", "device_market", "generic-rest", "/device-market/v1"),
    # Plan 9 P9-3.1: the tool-fleet contract system and the legacy depot repair log, synthetic
    System("fleet", "Fleet contract system (synthetic)", "fleet", "generic-rest", "/fleet/api/v1"),
    System("repairlog", "Legacy depot repair log (synthetic)", "repairlog", "generic-rest", "/repairlog/api"),
    # Plan 9 P9-3.2: the recall register, connected-tool telematics and the parts, stock and trade demand, synthetic
    System("recall", "Safety recall register (synthetic)", "recall", "generic-rest", "/recalls/api"),
    System("tooltel", "Connected-tool telematics (synthetic)", "tooltel", "generic-rest", "/tooltel/v2"),
    System("parts", "Tool service, stock and trade demand (synthetic)", "parts", "generic-rest", "/parts/api"),
    # Plan 9 P9-9.2: the used-car segment's lease system and dealer management system, synthetic vendor mocks
    System("uc_lease", "Vehicle lease system (synthetic)", "vehicle_lease", "vendor", "/vehicle-lease"),
    System("uc_dms", "Dealer management system (synthetic)", "dealer_dms", "vendor", "/dealer-dms"),
    # Plan 9 P9-9.3: the title and lien service, a synthetic vendor mock
    System("uc_title", "Title and lien service (synthetic)", "title_lien", "vendor", "/title-lien"),
    # Plan 9 P9-9.4: the vehicle inspection app (condition evidence), a synthetic vendor mock
    System("uc_insp", "Vehicle inspection app (synthetic)", "vehicle_inspection", "vendor", "/vehicle-inspection"),
    # Plan 9 P9-9.5: the vehicle recall database (open and remedied recalls by VIN), synthetic
    System("uc_recall", "Vehicle recall database (synthetic)", "vehicle_recall", "vendor", "/vehicle-recall"),
    # Plan 9 P9-9.6: the wholesale auction platform and the pricing guide, synthetic vendor mocks
    System("uc_auction", "Vehicle auction platform (synthetic)", "vehicle_auction", "vendor", "/vehicle-auction"),
    System("uc_price", "Vehicle pricing guide (synthetic)", "vehicle_pricing", "vendor", "/vehicle-pricing"),
    # Plan 9 P9-10.2: the telecom segment's network inventory and decommission tracker, synthetic vendor mocks
    System("tn_inv", "Network inventory (synthetic)", "network_inventory", "vendor", "/network-inventory"),
    System("tn_decom", "Decommission tracker (synthetic)", "decommission_tracker", "vendor", "/decommission"),
    # Plan 9 P9-11.2: the medical-device rental segment's rental system and asset management, synthetic vendor mocks
    System("mr_rental", "Rental system (synthetic)", "medical_rental_system", "vendor", "/rental-system"),
    System("mr_assets", "Asset management (synthetic)", "medical_asset_mgmt", "vendor", "/asset-management"),
    # Plan 9 P9-11.3: the decontamination log (cleaning cycles by device tag), a synthetic vendor mock
    System("mr_decon", "Decontamination log (synthetic)", "decon_log", "vendor", "/decon-log"),
    # Plan 9 P9-11.4: the biomedical service system (PM, certification, tests, field safety notices), a synthetic vendor mock
    System("mr_biomed", "Biomedical service system (synthetic)", "biomed_service", "vendor", "/biomed-service"),
    # Plan 9 P9-10.3: the telecom segment's test bench (results, wipe evidence, firmware), a synthetic vendor mock
    System("tn_bench", "Test bench (synthetic)", "test_bench", "vendor", "/test-bench"),
    # Plan 9 P9-10.4: the telecom segment's spares planning system (catalogue, targets, requisitions), synthetic
    System("tn_spares", "Spares planning (synthetic)", "spares_planning", "vendor", "/spares-planning"),
)
EXTRA_BY_ID = {s.source_id: s for s in EXTRA_SYSTEMS}

# Vendors replaced on purpose (docs/backend-steps.md, B5b). The frontend (index.html data) still shows the old name
# until it switches to the API (B17).
VENDOR_OVERRIDES = {"tms": "Oracle Transportation Management"}  # was the fictional "ShipLane TMS"
