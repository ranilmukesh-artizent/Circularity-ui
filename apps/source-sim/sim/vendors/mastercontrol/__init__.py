"""MasterControl Quality Excellence mock (docs/BACKEND_STEPS.md, B5b): the demo's QMS source (SOURCES.qms).

REST API under /mastercontrol/mc/api (the demo's url https://qms.northfield.example/mc/api), see api.py. Data in Postgres
schema `mastercontrol` (tables.py), seeded from the world (seed.py). Replaces sim/generic/specs/mastercontrol.py.

Documentation followed
- MasterControl help, "Access and Use MasterControl APIs" (customer portal, login required; not readable here):
  https://currentcloud.onlinehelp.mastercontrol.com/2024.1/en_us/Content/Appendix/Access_and_Use_MasterControl_APIs.htm
- MasterControl API Toolkit: https://www.mastercontrol.com/solutions/toolkit/ and
  https://www.mastercontrol.com/resource-center/documents/mastercontrol-api-toolkit
- Public summary of the API surfaces (Qx REST, Mx REST, legacy Web Service API; REST uses tenant API keys; an API
  licence is required; no generic webhooks): https://supergood.ai/api-report-card/mastercontrol
- The demo's own contract (index.html SOURCES.qms): OAuth 2.0 client credentials, GET /v2/controlled-documents,
  /v2/certificates, /v2/test-criteria, cursor pagination, 60 requests/min; MAPPINGS.qms field names.
MasterControl publishes no public reference for its REST payloads, so every shape below is an assumption.

Demo credentials (constants in api.py)
    OAuth client credentials: client_id circularity-di / client_secret circularity-demo-mastercontrol-secret
                              POST /mastercontrol/mc/api/oauth2/token (form; client in the form or HTTP Basic)
    Tenant API key:           header X-API-KEY: circularity-demo-mastercontrol-apikey

ASSUMPTION: both auth styles are accepted: the demo lists OAuth client credentials, public material says the REST API
    uses static tenant API keys. Token endpoint path /oauth2/token, lifetime 3600 s, RFC 6749 error bodies.
ASSUMPTION: list envelope {"data", "paging": {"limit", "nextCursor"}, "totalCount"}, ?limit= (max 1000) and an opaque
    ?cursor= (the demo's connector config says "Cursor"); deltas with ?modifiedSince= (strictly after).
ASSUMPTION: error body {"status", "errorCode", "message", "timestamp", "path"[, "errors": [{"field", "message"}]]}
    (MasterControl is a Java/Spring platform; this is the Spring Boot shape).
ASSUMPTION: standard metadata in camelCase (infoCardId, documentNumber, revision, lifecycleState, effectiveDate ...);
    site-configured form data fields keep their configured upper-case names under "dataFields" (CERT_EXPIRY,
    REUSE_CLASS, TEST_RESULT: the names in the demo's MAPPINGS).
ASSUMPTION: certificates are a configured quality-event form ("certificates") rather than training records; expiry is
    the CERT_EXPIRY data field; dates are evaluated in UTC on the simulated clock.
ASSUMPTION: deviations are served read-only (DEV-118, approver Q. Lead: the demo's unmapped sample fields).
ASSUMPTION: the 60 requests/min rate limit is not enforced.

Business rules: document revision status (Pending Effective / Effective / Superseded; only Effective revisions are
policy, and a certificate can only be recorded against one); certificate expiry by date (Expired from the day after
CERT_EXPIRY) and revocation. Writes stamp clock.now() and emit outbox events mastercontrol.certificate.created/.revoked.
"""

from sim.mock import Mock
from sim.vendors.mastercontrol.api import router
from sim.vendors.mastercontrol.seed import ensure, reset

MOCK = Mock("qms", router, ensure, reset, "MasterControl")
