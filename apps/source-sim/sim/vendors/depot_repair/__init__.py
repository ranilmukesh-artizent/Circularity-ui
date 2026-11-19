"""Oracle Depot Repair (Oracle E-Business Suite 12.2.13, product CSD) mock: the demo's SOURCES.repair
(docs/BACKEND_STEPS.md, B5b). Receiving inspection and grade, teardown findings, repair orders, tasks and hours,
parts, bench test results, release to service.

Documentation followed
    Oracle E-Business Suite Integrated SOA Gateway Developer's Guide, Release 12.2 (REST services: URL pattern, JSON
      payload wrappers, token-based authentication, ISGServiceFault):
      https://docs.oracle.com/cd/E26401_01/doc.122/e20927/toc.htm
      https://docs.oracle.com/cd/E26401_01/doc.122/e20927/T511473T669558.htm
    My Oracle Support notes on ISG REST faults (ISG_SERVICE_EXECUTION_ERROR, ISG_UNSUPPORTED_REST_VERB; 2466214.1,
      2754634.1, 2177901.1) and the upper-case parameter rule for PL/SQL services (2802250.1)
    Oracle Depot Repair public API CSD_REPAIRS_PUB.CREATE_REPAIR_ORDER (P_API_VERSION_NUMBER, P_REPAIR_NUMBER,
      P_REPLN_REC, X_REPAIR_LINE_ID, X_REPAIR_NUMBER, X_RETURN_STATUS, X_MSG_COUNT, X_MSG_DATA), as listed in the
      Integration Repository (Oracle Depot Repair Implementation Guide)

Base: /depot-repair (the vendor host) + /webservices/rest/<alias>/<method>/ (see isg.py for the shared conventions).
Auth: HTTP Basic with EBS user DI_CONNECTOR / repair-demo-password, or token-based: GET|POST
    /depot-repair/webservices/rest/login (Basic) → {"data": {"accessTokenName": "EBSDRP1", "accessToken", "ebsVersion"}},
    then the cookie EBSDRP1=<accessToken>. 401 → ISGServiceFault ISG_USER_AUTHENTICATION_FAILED | ISG_INVALID_ACCESS_TOKEN.

Reads (GET; IN parameters as query parameters; paging P_START_INDEX (1-based) and P_MAX_RECORDS (≤ 500); delta
P_LAST_UPDATE_DATE_FROM, exclusive) on the custom query service XXCSD_RO_QUERY (alias xxcsdroquery):
    get_repair_orders/  P_SERIAL_NUMBER, P_REPAIR_NUMBER, P_ORIGINAL_SOURCE_REFERENCE, P_FLOW_STATUS_CODE, P_STATUS,
                        P_REPAIR_ORG → X_REPAIR_ORDERS {X_REPAIR_ORDERS_ITEM: [...]}, X_TOTAL_COUNT, X_HAS_MORE
    get_repair_tasks/   P_REPAIR_NUMBER, P_SERIAL_NUMBER → X_REPAIR_TASKS
    get_test_results/   P_REPAIR_NUMBER, P_SERIAL_NUMBER → X_TEST_RESULTS
    Record fields: REPAIR_LINE_ID, REPAIR_NUMBER (RO-61048), SERIAL_NUMBER, ORIGINAL_SOURCE_REFERENCE (RT-1048),
    STATUS (O | C), FLOW_STATUS_CODE, REPAIR_TYPE, REPAIR_ORG (RC01), CURRENT_LOCATION (WH01), RECEIVING_INSPECTION,
    TEARDOWN_FINDINGS, SCOPE, REPAIR_COST + CURRENCY_CODE, RESULT_STATE, PARTS, LABOUR, RELEASE_TO_SERVICE,
    PROMISE_DATE, CREATION_DATE, LAST_UPDATE_DATE (EBS time, +05:30, milliseconds).
Writes (POST, {"CREATE_REPAIR_ORDER_Input": {"RESTHeader": {...}, "InputParameters": {...}}}):
    csdrepairs/create_repair_order/ (CSD_REPAIRS_PUB.CREATE_REPAIR_ORDER): P_API_VERSION_NUMBER 1.0, optional
        P_REPAIR_NUMBER, P_REPLN_REC {SERIAL_NUMBER (required), REPAIR_TYPE (Refurbishment, Repair and Return,
        Evaluation, Teardown, Walk-in Repair), QUANTITY, PROMISE_DATE, ORIGINAL_SOURCE_REFERENCE, PROBLEM_DESCRIPTION,
        CURRENCY_CODE, descriptive flexfield ATTRIBUTE_CATEGORY "CIRCULARITY": ATTRIBUTE1 scope ("Light repair +
        test"), ATTRIBUTE2 estimate amount (1800), ATTRIBUTE3 predicted grade (B)} → X_REPAIR_LINE_ID,
        X_REPAIR_NUMBER (RO-7nnnn). Validation failures answer 200 with X_RETURN_STATUS "E" and X_MSG_DATA (bad
        version, missing serial, unknown repair type, bad quantity / flexfields / promise date, duplicate repair
        number, serial already in repair); a malformed payload is a 400 ISGServiceFault.
Business rules (sim/scheduler.py, simulated clock): a new order is OPEN with its WIP operations (labour from the
    serial's earlier repair order or the class standard, machine operations of the class) and its parts plan.
    +1 h → IN_PROGRESS (operations in progress, parts issued); + planned labour and machine hours → REPAIR_COMPLETE
    (operations complete with actual hours, final bench tests recorded at the predicted grade, release to service
    RTS-<repair number> when they pass); + 2 h → CLOSED (STATUS C, DATE_CLOSED). Each change stamps LAST_UPDATE_DATE.
Outbox events (source "repair", EBS business event names): oracle.apps.csd.repair.create,
    oracle.apps.csd.repair.status.update, oracle.apps.csd.repair.complete. Each carries the caller's references:
    REPAIR_NUMBER (the caller may choose it with P_REPAIR_NUMBER), REPAIR_LINE_ID, SERIAL_NUMBER and
    ORIGINAL_SOURCE_REFERENCE.

ASSUMPTION: EBS has no public query API for repair orders; reads go through a custom PL/SQL package XXCSD_RO_QUERY
    deployed in ISG (as EBS customers do), returning CSD_REPAIRS columns plus the estimate, inspection, parts and
    labour the demo needs, under the demo's field names in upper case (REPAIR_COST, SCOPE, RESULT_STATE).
ASSUMPTION: the scope / estimate / predicted grade of a new order travel in the repair order's descriptive
    flexfield (ATTRIBUTE1-3); REPAIR_TYPE is taken by name instead of REPAIR_TYPE_ID.
ASSUMPTION: service aliases xxcsdroquery and csdrepairs; token cookie name EBSDRP1; 12.2.13; database time zone IST.
ASSUMPTION: the ISG fault codes ISG_USER_AUTHENTICATION_FAILED, ISG_INVALID_ACCESS_TOKEN, ISG_INVALID_INPUT_PAYLOAD,
    ISG_INVALID_PARAMETER_VALUE, ISG_SERVICE_NOT_FOUND and ISG_METHOD_NOT_FOUND (ISG_UNSUPPORTED_REST_VERB is real).
ASSUMPTION: the flow statuses (Open → In Progress → Repair Complete → Closed, plus the seeded Awaiting Inspection,
    Inspection Partial, Estimate Pending Approval) are this depot's flow-status setup; timings are the mock's.
"""

from sim.mock import Mock
from sim.vendors.depot_repair import api, seed

MOCK = Mock("repair", api.router, seed.ensure, seed.reset, "Oracle Depot Repair")
