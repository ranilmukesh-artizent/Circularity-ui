"""Oracle Lease and Finance Management (Oracle E-Business Suite 12.2.13, product OKL) mock: the demo's SOURCES.lease
(docs/backend-steps.md, B5b). Contract end dates, lease rates, lessee and asset ownership, renewal options, asset
returns.

Documentation followed
    Oracle E-Business Suite Integrated SOA Gateway Developer's Guide, Release 12.2 (REST services, payload wrappers,
      token-based authentication, ISGServiceFault): https://docs.oracle.com/cd/E26401_01/doc.122/e20927/toc.htm
    Oracle Lease and Finance Management public API OKL_AM_ASSET_RETURN_PUB (CREATE_ASSET_RETURN /
      UPDATE_ASSET_RETURN with P_API_VERSION, P_ARTV_REC: KLE_ID, ARS_CODE, ART1_CODE, DATE_RETURNED; X_ARTV_REC,
      X_RETURN_STATUS, X_MSG_COUNT, X_MSG_DATA) as listed in the Integration Repository, and OKL's contract statuses
      (BOOKED, EVERGREEN, EXPIRED, TERMINATED) from the Oracle Lease and Finance Management User Guide
    The shared ISG conventions are in sim/vendors/depot_repair/isg.py.

Base: /oracle-lease (the vendor host) + /webservices/rest/<alias>/<method>/.
Auth: HTTP Basic with EBS user DI_CONNECTOR / lease-demo-password, or token-based (GET|POST
    /oracle-lease/webservices/rest/login → cookie EBSOKL1=<accessToken>). 401 → ISGServiceFault.

Reads (GET; paging P_START_INDEX / P_MAX_RECORDS ≤ 500; delta P_LAST_UPDATE_DATE_FROM, exclusive) on the custom query
service XXOKL_LEASE_QUERY (alias xxoklleasequery); each record carries LAST_UPDATE_DATE:
    get_contracts/      P_CONTRACT_NUMBER, P_ASSET_NUMBER, P_LESSEE_NAME, P_CONTRACT_STATUS → X_CONTRACTS
                        LEASE_CONTRACT_ID (LC-004417), CONTRACT_NUMBER, CHR_ID, CONTRACT_STATUS, DEAL_TYPE, LESSEE_NAME
                        (CUSTOMER_A), CONTRACT_START_DATE, CONTRACT_END_DATE (2026-12-31), TERM_MONTHS, MONTHLY_RENTAL
                        (2400.0) + CURRENCY_CODE (USD), BILLING_FREQUENCY, RENEWAL_OPTION, ASSET_NUMBER, KLE_ID
    get_lease_assets/   P_ASSET_NUMBER, P_LEASE_CONTRACT_ID, P_LEASE_STATUS, P_OWNER_NAME, P_KLE_ID → X_ASSETS
    get_renewals/       P_ASSET_NUMBER, P_LEASE_OPPORTUNITY_ID, P_LEASE_CONTRACT_ID, P_STATUS → X_RENEWALS
    get_asset_returns/  P_KLE_ID, P_ASSET_NUMBER, P_ARS_CODE → X_ASSET_RETURNS
Writes (POST {"<METHOD>_Input": {"RESTHeader", "InputParameters": {"P_API_VERSION": "1.0", "P_ARTV_REC": {...}}}}),
    service OKL_AM_ASSET_RETURN_PUB (alias oklamassetreturn):
    create_asset_return/  KLE_ID (required), ARS_CODE SCHEDULED (default) | RETURNED, ART1_CODE TERM_EXPIRATION
                          (default) | EARLY_TERMINATION | REPOSSESSION, DATE_RETURNED (default today), COMMENTS
    update_asset_return/  ID or KLE_ID, ARS_CODE RETURNED, DATE_RETURNED: a scheduled return is received
    Validation errors answer 200 with X_RETURN_STATUS "E" (bad version, missing/unknown asset line, bad codes, a
    second return for the same line, a return already received, a future DATE_RETURNED).
Business rules (simulated clock):
    - a received return sets the asset to RETURNED with its RETURN_DATE; on an EVERGREEN contract whose assets are now
      all back, the contract is TERMINATED (DATE_TERMINATED); on a BOOKED contract the term-end run is scheduled for
      the end of CONTRACT_END_DATE (sim/core/scheduler.py, handler okl.contract.term_end)
    - term end (OKL's expiration run): a BOOKED contract past its end date becomes EXPIRED when all its assets are
      returned, else EVERGREEN (month-to-month until they are). The run also catches up before every read.
    Every change stamps LAST_UPDATE_DATE with simulated time.
Outbox events (source "lease"): oracle.apps.okl.am.asset_return.created | returned,
    oracle.apps.okl.la.contract.expired | evergreen | terminated.

ASSUMPTION: OKL has no public query API for contracts; reads go through a custom PL/SQL package XXOKL_LEASE_QUERY
    deployed in ISG, flattening OKC_K_HEADERS / OKL_K_HEADERS / OKC_K_LINES / OKL asset returns under the demo's
    field names (LEASE_CONTRACT_ID, CONTRACT_END_DATE, LESSEE_NAME, MONTHLY_RENTAL ...).
ASSUMPTION: the demo lists this source as "Fusion 24B" at .../fscmRestApi; Oracle's lessor product is the EBS module,
    so the EBS ISG conventions are used, as docs/backend-steps.md (B5b) decides.
ASSUMPTION: re-lease opportunities (renewals) are a custom table of this deployment.
ASSUMPTION: aliases xxoklleasequery and oklamassetreturn, cookie EBSOKL1, the business event names, and the ISG fault
    codes other than ISG_UNSUPPORTED_REST_VERB.
ASSUMPTION: MTR-2077 (no case in the demo, still on lease) is on its own contract LC-005077 ending 2027-03-31.
"""

from sim.core.mock import Mock
from sim.vendors.oracle_lease import routes, seed

MOCK = Mock("lease", routes.router, seed.ensure, seed.reset, "Oracle Lease and Finance Management")
