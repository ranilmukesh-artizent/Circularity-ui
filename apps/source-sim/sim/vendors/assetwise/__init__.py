"""Bentley AssetWise (CONNECT Edition) mock (docs/BACKEND_STEPS.md, B5b): the demo's engineering source (SOURCES.eng).

The engineering data warehouse over OData v4 under /assetwise/eB/Service/OData/Engineering/ (see api.py), with
Bentley IMS tokens (client credentials) or AssetWise Basic authentication. Data in Postgres schema `assetwise`
(seed.py): life assessments, requalification standards, engineering limits.

Documentation followed
    AssetWise CONNECT Edition Implementation Guide, "Accessing Data Warehouse Information": the OData endpoint
        http://<application_server>/eB/Service/OData/<warehouse_name>/<entity>, the service root lists the entities,
        Basic authentication, standard OData query syntax:
        https://docs.bentley.com/LiveContent/web/AssetWise%20CONNECT%20Edition%20Implementation%20Guide%20WebHelp-v2/en/GUID-58BD404D-79FD-4232-85DD-0D8A697720A6.html
    AssetWise CONNECT Edition Implementation Guide, "IMS Integration" (AssetWise sign-in through Bentley IMS):
        https://docs.bentley.com/LiveContent/web/AssetWise%20CONNECT%20Edition%20Implementation%20Guide%20WebHelp-v2/en/GUID-DE5AEB42-6239-4566-905C-188B5B2733BD.html
    Bentley IMS service applications: POST https://ims.bentley.com/connect/token with grant_type=client_credentials,
        client_id, client_secret and scope as form fields: https://developer.bentley.com/apis/overview/authorization/service-app/
    OData v4.01 (OASIS) for $filter / $select / $orderby / $top / $skip / $count, server-driven paging with
        odata.maxpagesize and @odata.nextLink, the JSON error format, bound actions: https://docs.oasis-open.org/odata/odata/v4.01/

Demo credentials (auth.py)
    IMS service app: client_id service-circularity-di, client_secret circularity-demo-ims-secret, scope assetwise-odata
        (runs as di.connector)
    Basic: di.connector / Circularity-demo-aw-1; eng.approver / Circularity-demo-aw-approver (approves assessments)

Business rules (an assessment's approval status and validity)
    - APPROVAL_STATUS moves Draft -> Submitted (AssetWise.Submit; needs RUL_MONTHS) -> Approved (AssetWise.Approve) or
      Rejected (AssetWise.Reject). The approver must not be the submitter (403). Only drafts and rejected assessments
      can be edited (PATCH; 409 otherwise); an edit returns the assessment to Draft / requalification PENDING.
    - Approval needs a remaining life of at least MIN_RUL_MONTHS (12); it sets REQUAL_STATUS APPROVED, APPROVED_BY,
      APPROVED_AT and the validity window VALID_FROM .. VALID_UNTIL = approval + the class standard's requalification
      interval (24 months for motors).
    - VALIDITY is worked out at every read against the simulated clock: VALID, EXPIRED (on or after VALID_UNTIL),
      NOT_YET_VALID or NOT_APPROVED.
    - Every change stamps MODIFIED_ON with the simulated clock and emits com.bentley.assetwise.LifeAssessment.<Action>.

ASSUMPTION: AssetWise has no public REST reference for life assessments; the engineering data is published as a data
    warehouse named "Engineering" with entity sets LifeAssessments, Standards and EngineeringLimits whose columns keep
    the warehouse view names the demo maps (RUL_MONTHS, STANDARD_REF, REQUAL_STATUS ...).
ASSUMPTION: the warehouse OData service follows ASP.NET Web API OData conventions (OData v4, minimal metadata, error
    {"error": {"code", "message"}}, 401 "Authorization has been denied for this request.", 404 "No HTTP resource was
    found that matches the request URI ..."), with 100 rows per page unless Prefer: odata.maxpagesize asks for fewer.
ASSUMPTION: the IMS host is reached under the vendor prefix (/assetwise/ims/connect/token), IMS bearer tokens are
    accepted directly by the service (no separate AssetWise Session token exchange), tokens are opaque and live 3600 s,
    and the scope is "assetwise-odata".
ASSUMPTION: the approval workflow is exposed as bound OData actions AssetWise.Submit / Approve / Reject (optional
    {"Comment"}), answering 204; PATCH answers 204.
ASSUMPTION: all times are UTC (Edm.DateTimeOffset with Z); NEXT_INSPECTION_DATE is an Edm.Date.
"""

from sim.mock import Mock
from sim.vendors.assetwise.api import router
from sim.vendors.assetwise.seed import ensure, reset

MOCK = Mock("eng", router, ensure, reset, "Bentley AssetWise")
