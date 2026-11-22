"""Optoro (OptiTurn returns platform) mock (the demo's SOURCES.rl; docs/backend-steps.md, B5b).

Optoro serves each API from its own host (auth.optiturn.com, asn.optiturn.com, orders.optiturn.com ...). Under the
registry's base /optoro each host is one path segment: /optoro/auth, /optoro/asn, /optoro/inventory, /optoro/returns.

Documentation followed (public OpenAPI descriptions on Optoro's developer portal):
    https://developer.optoro.com/content/api_overview          auth, versioning header, rate limits, error format
    https://developer.optoro.com/_bundle/openapi/auth/openapi.json            POST /oauth/token
    https://developer.optoro.com/_bundle/openapi/asn/openapi.json             POST /asns, PUT /asns/{asn-number}
    https://developer.optoro.com/_bundle/openapi/inventory_receipt/openapi.json   POST /inventory_receipt
    https://developer.optoro.com/_bundle/openapi/rmas/@5/openapi.yaml         RMA object (v5)
    https://developer.optoro.com/_bundle/openapi/disposition_update/openapi.json  disposition update payload
    https://developer.optoro.com/_bundle/openapi/final_disposition/openapi.json   final disposition payload
    https://developer.optoro.com/_bundle/openapi/drop_ship/@2023-08-15/openapi.yaml  list conventions (per_page,
        offset cursor, updated_at, next_page {offset, path, uri}, record_count header)
    https://developer.optoro.com/content/webhooks

Auth: POST /optoro/auth/oauth/token {"grant_type": "client_credentials", "client_id", "client_secret"} (JSON as
    documented; form-encoded and HTTP Basic client also accepted) -> {"access_token", "token_type": "Bearer",
    "expires_in": 90000, "scope": "read write", "created_at"}; bad client 401 {"error": "invalid_client",
    "error_description"}. Demo client di-connector / rl-demo-secret. Calls carry `Authorization: Bearer <token>`;
    the documented per-program api_key is also accepted as `X-Api-Key: rl-demo-key`. Unauthorised: 401, no body.
Errors: 422 {"message": "Validation Failed", "errors": [{"field", "code": missing_field|invalid_type|invalid}]},
    400 {"message"} for unparseable bodies, 404 {"message": "Not Found"}.

Writes (documented paths and bodies):
    POST /optoro/inventory/inventory_receipt  documented InventoryReceipt (required program_identifier, asn_number,
         from, to {identifier: integer warehouse id, type, original_identifier}, unit_identifier, sku,
         initial_condition N|TT|R|A|B|C|X, initial_channel, ot_user_login; reference {type: RMA, identifier}).
         201 new receipt (received_at = simulated now), 200 the same unit again. Receiving against an RMA marks the
         item RECEIVED / DELIVERED with warehouse_receipt_condition, sets receiving_complete, and delivers the ASN.
         Refused (422): unknown RMA, SKU not open on the RMA, bad condition or channel.
    POST /optoro/asn/asns (202), PUT /optoro/asn/asns/{asn-number} (202; refused 422 once delivered/cancelled or
         received against), documented AdvanceShipNotice body.
Writes (ASSUMPTION: Optoro creates RMAs in its returns portal and pushes dispositions as webhooks; the mock lets the
    client do both through the API, with the documented payloads):
    POST /optoro/returns/rmas  {"items": [{"sku", "order_identifier", "return_reason", ["secondary_identifier",
         "quantity", "exchange_order_identifier"]}], "return_method", ["rma_identifier", "warehouse_id"]}
         -> 201 RMA v5 object, status CREATED, items PENDING (a return authorisation).
    POST /optoro/returns/dispositions  {"optiturn_lp", "to_disposition", "to_condition", ["user_login"]}
         -> 201 disposition update (from_* = the unit's current channel and condition). Refused (422): unit not
         received, unknown channel/condition, no change, unit already finally disposed. On the simulated clock the
         unit is finally disposed after rts 1 day, refurbish 3 days, recycle 2 days, other channels 2 days
         (a final disposition record), unless a later disposition superseded it.
Reads (ASSUMPTION: the documented objects are pushed to the client; the mock also lists them, using the drop-ship
    list conventions: ?per_page= (default 20, max 100) &offset=<cursor> &updated_at=<ISO, changed after>;
    body {"<plural>": [...], "next_page": {"offset", "path", "uri"} | null}; header record_count):
    GET /optoro/returns/rmas[/{rma_identifier}]             filters status, sku, secondary_identifier
    GET /optoro/inventory/inventory_receipts[/{unit_identifier}]   filters sku, asn_number, rma_identifier
    GET /optoro/returns/dispositions, /optoro/returns/final_dispositions   filters optiturn_lp, sku
    GET /optoro/asn/asns[/{asn_number}]                     filters status, sku
Outbox events (source "rl"): optoro.rma.created|updated, optoro.inventory_receipt.created, optoro.asn.created|updated,
    optoro.disposition.updated, optoro.final_disposition.created.

Seed (values of the generic mock this replaces): per case one RMA (RT-1048: RMA-56509; created_at = authorisation,
    secondary_identifier = case id, order_identifier = lease contract, exchange_order_identifier = the replacement
    order SO-48102), one delivered ASN SHP-<n> (shipment_identifier = the TMS load LD-2<n>, carrier, freight), one
    receipt of unit LPNF<n> (RT-1048 received 2026-10-03T15:28:00-04:00) and, for graded units, one disposition
    update needs_testing -> rts (A, B), refurbish (C) or recycle (D -> condition X).

ASSUMPTION: refurbish and needs_testing are program-configured channels (the documented enum has neither; needs_testing
    appears in the documented example).
ASSUMPTION: rma_item.quantity, receipt.quantity/received_at/created_at/updated_at, ASN carrier_scac,
    estimated_arrival_date, delivered_at, freight, receptions, created_at/updated_at, from.name, and the disposition
    record id/updated_at are extensions; received_at and delivered_at are in the returns centre's local time (-04:00).
ASSUMPTION: the 202 body of ASN calls ({"message": "Accepted", "asn_number"}) and the 404 body.
"""

from sim.core.mock import Mock
from sim.vendors.optoro import routes, seed

MOCK = Mock("rl", routes.router, seed.ensure, seed.reset, "Optoro")
