"""Aras Innovator 14 mock (docs/backend-steps.md, B5b): the demo's BOM source (SOURCES.bom).

The RESTful API (OData v4) under /aras/InnovatorServer/server/odata and the Innovator OAuth server under
/aras/InnovatorServer/oauthserver (see api.py, auth.py). Data in Postgres schema `aras` (seed.py): Parts, Part BOM,
Manufacturers, Manufacturer Parts and the Part AML (approved manufacturer list). odata4.py is the small OData v4
query engine this mock and the AssetWise mock share.

Documentation followed
    Aras Innovator 12.0 - RESTful API (the OData interface: URL format /server/odata/<ItemType>, entities and
        properties, item properties and @aras.* annotations, relationships, $filter operators and functions,
        bracketed ItemType names, $expand / $select / $orderby / $top / $skip / $count, create / update / upsert with
        Prefer: return=minimal|representation and @odata.bind, server-driven paging with odata.maxpagesize and
        $skiptoken, the error response, "Using OAuth Tokens from the Authentication Server":
        OAuthServerDiscovery.aspx, .well-known/openid-configuration, the token request fields grant_type=password,
        scope=Innovator, client_id=IOMApp, username, password, database, and the token response):
        https://aras.com/wp-content/uploads/2024/04/Aras-Innovator-120-RESTful-API-1.pdf
    Aras Innovator 2025 / 33 RESTful API guides (same interface):
        https://aras.com/wp-content/uploads/2025/06/Aras-Innovator-2025-Release-RESTful-API.pdf
    Using OAuth 2.0 Tokens from the Authentication Server:
        https://docs.aras.com/using-oauth-2-0-tokens-from-the-authentication-server/0000019f-274a-d087-a79f-e77b61ee0000
    Aras Labs, "Token authentication using the REST API" (the password is sent as its MD5 hash):
        https://community.aras.com/blog/labs/token-authentication-using-the-rest-api/15916
    Aras community, navigating a BOM: GET /Part('id')/Part BOM?$expand=related_id:
        https://community.aras.com/discussions/development/aras-rest-api---how-do-you-navigate--create-a-bom-structure-using-the-rest-api/5991
    Aras Product Engineering data model: Part (item_number, name, classification, state Preliminary/In Review/
        Released/Superseded/Obsolete, major_rev, make_buy, unit, cost), Part BOM (quantity, sort_order,
        reference_designator), Manufacturer, Manufacturer Part (item_number, manufacturer), Part AML.

Demo credentials (auth.py): database InnovatorDB, client_id IOMApp, scope Innovator;
    di-connector / Circularity-demo-aras-1 (sent as md5 hex) and admin / innovator.

Business rules
    - A Released Part cannot be edited, nor can the BOM lines under it (its lifecycle state grants no update):
      400 with Aras.Server.Core.InsufficientPermissionsException. New Parts start Preliminary, major_rev A.
    - Part item_number is unique (Manufacturer Part: unique per manufacturer).
    - Manufacturer parts may be added to a Released Part's AML (POST Part('id')/Part AML), as approved sourcing changes
      do not revise the design.
    - Every change stamps modified_on / modified_by_id with the simulated clock and the caller, and emits
      com.aras.innovator.<ItemType>.created|updated.

ASSUMPTION: without Prefer: odata.maxpagesize, a collection is returned whole (the guide documents paging only when
    the client asks for it); $count=true adds @odata.count (OData v4) besides the documented /$count segment.
ASSUMPTION: item properties in $select are returned as "<name>@aras.id", "<name>@aras.type" and
    "<name>@aras.keyed_name" annotations; every entity carries "@odata.id" ("Part('<id>')").
ASSUMPTION: booleans are returned as "1" / "0" (as AML stores them); decimals and integers as JSON numbers; dates as
    ISO 8601 without an offset in the server's zone (UTC here), compared as date-times in $filter.
ASSUMPTION: the custom Part properties nf_asset_class, nf_harvestable and nf_cost_currency (cost is held in INR, the
    currency of the demo's supplier contracts) and the product classification "Product" are this customer's
    configuration.
ASSUMPTION: tokens are opaque (not JWTs) and live 3600 s; token errors follow IdentityServer (400 invalid_grant /
    invalid_client / invalid_scope / unsupported_grant_type); 401 without a valid bearer token, with the error body.
ASSUMPTION: error details: unknown ItemType or item 404, unknown property 400 (target AML), malformed query 400
    (target OData). The demo's instance path is /InnovatorServer under the /aras vendor prefix.
"""

from sim.mock import Mock
from sim.vendors.aras.api import router
from sim.vendors.aras.seed import ensure, reset

MOCK = Mock("bom", router, ensure, reset, "Aras Innovator")
