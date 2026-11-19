"""Oracle Transportation Management (OTM) mock: the demo's SOURCES.tms (docs/BACKEND_STEPS.md, B5b). OTM replaces
the demo's fictional "ShipLane TMS" (VENDOR_OVERRIDES in sim/registry.py); the seeded values are unchanged.

Documentation followed
    REST API for Oracle Transportation Management (otmra), 26A:
      https://docs.oracle.com/en/cloud/saas/transportation/26a/otmra/Collections.html     (q, paging, orderBy)
      https://docs.oracle.com/en/cloud/saas/transportation/26a/otmra/op-shipments-get.html (shipment fields, children)
      https://docs.oracle.com/en/cloud/saas/transportation/26a/otmra/op-trackingevents-get.html (tracking events)

Base: /otm (the vendor host) + /logisticsRestApi/resources/v2 (also served under /logisticsRestApi/resources-int/v2).
Auth: HTTP Basic with an OTM user (DOMAIN.USER): NORTHFIELD.DI_CONNECTOR / otm-demo-password, or OAuth 2.0 client
    credentials from the identity domain: POST /otm/oauth2/v1/token, client di-connector / tms-demo-secret (HTTP
    Basic or form) → {"access_token", "token_type": "Bearer", "expires_in": 3600}.
    401 without or with bad credentials (WWW-Authenticate: Basic realm="OTM", or Bearer error="invalid_token").

Reads (GET; media type application/vnd.oracle.resource+json;type=collection | singular):
    /locations  /serviceProviders  /rateOfferings  /xLanes  /rateGeos  /orderReleases  /shipments
    /{resource}/{gid}            one object, e.g. /shipments/NORTHFIELD.LD-21048 (a GID with '>' is URL-encoded)
    /{resource}/{gid}/{child}    a child collection: shipments: refnums, stops, statuses, orderReleases,
                                 trackingEvents; rateGeos: costs; orderReleases: refnums, statuses;
                                 serviceProviders: servprovAliases; locations: roles
    Query: q (eq ne co sw ew pr gt ge lt le in, and/or/not, parentheses; dotted paths into children, e.g.
    q=refnums.shipmentRefnumValue eq "RT-1048"), limit (default 25, max 500), offset, totalResults=true, orderBy
    (field:asc|desc), expand (child names or all), fields. Collection body: items, [totalResults], count, hasMore,
    limit, offset, links (self, next, prev). Children are left out unless expanded (links rel=child name them).
    Delta reads: q=updateDate gt "<last updateDate seen>".
Writes:
    POST /orderReleases (the transport booking of an approved instruction) {orderReleaseXid, sourceLocationGid,
        destLocationGid, earlyPickupDate {value}, lateDeliveryDate {value}, totalWeight {value, unit KG|LB},
        totalShipUnitCount, servprovGid (optional preferred carrier), refnums {items: [{orderReleaseRefnumQualGid,
        orderReleaseRefnumValue}]}} → 201 + Location. Validation: 400 on a missing/duplicate id, unknown location or
        carrier, bad dates/weight. Business rules (the bulk-plan agent on ORDER RELEASE - CREATED): when the lane has
        an active rate record on RC-2026.2, the release is planned (PLANNING_PLANNED - FINAL) into a direct shipment
        LD-5nnnn: carrier NLTL Northline 3PL unless one is given, rate geo and charges of the lane (dedicated LCV from
        150 kg, part load below), loadedDistance, ETD = earlyPickupDate (or now + 2 h when that has passed), ETA =
        ETD + lane transit hours, tender accepted, ENROUTE_NOT STARTED; refnums are copied (MOVE_TYPE defaults to
        OUTBOUND). Without a rate record (or on a partner lane) it stays PLANNING_NEW and no shipment is built.
    Scheduled on the simulated clock (sim/scheduler.py): at ETD tracking event AF (departed, ENROUTE_STARTED), at ETA
        X1 (arrived), at ETA + 30 min D1 (delivered, ENROUTE_COMPLETED) with the proof of delivery POD-5nnnn signed by
        "Receiving · <location>". Every change stamps updateDate with simulated time.
Outbox events (source "tms"): otm.orderRelease.created | planned | planningFailed, otm.shipment.created,
    otm.shipment.tenderAccepted, otm.shipment.departed | arrived | delivered. Every otm.shipment.* event carries
    shipmentGid, shipmentXid, orderReleaseGids / orderReleaseXids (the order releases on the shipment, i.e. the
    caller's orderReleaseXid) and refnums [{shipmentRefnumQualGid, shipmentRefnumValue}], so a caller can match it
    to the booking it sent.
ASSUMPTION: the event payloads are this deployment's integration events (OTM publishes via its own integration
    layer, whose message shape is configured per implementation); the REST resources are unchanged.
Errors: application/vnd.oracle.resource+json;type=error {"type", "title", "status", "detail", "o:errorCode"}.

Conventions of this deployment (refnum qualifiers and flexfields an OTM implementation configures itself):
    shipment refnums CASE_REF (RT-1048), ITEM_ID (MTR-2041), RMA, ITEM_DESC, MOVE_TYPE (RETURN_COLLECTION =
    inbound, anything else outbound); shipment attribute1 equipment ("Dedicated LCV 1.5 t with tail-lift"),
    attribute2 rate basis ("34 km · minimum charge ₹3,600"); location attribute1 kind, attribute2 Manhattan facility
    id (WH01, ST03), attribute3 demo site; serviceProvider attribute1 role; rateOffering attribute1 contract
    (NL-MSA-2025-11), attributeNumber1-7 rate card terms (per km, loading, minimum, docket, part-load minimum,
    detention free minutes, detention USD/h); rateGeo attribute1 FTL | PARTNER.

ASSUMPTION: the q grammar beyond the documented operators (literal forms, how typed values compare) follows the
    documented examples; typed values compare by their "value".
ASSUMPTION: currencyType is {"value", "currency"} and amountType {"value", "unit"}; dateTimeType {"value",
    "timezone"} is documented. Times are shown in the location's offset (IST, timezone Asia/Calcutta).
ASSUMPTION: insertDate / updateDate are shown as dateTimeType in UTC to the millisecond.
ASSUMPTION: error bodies follow the Oracle REST error schema (type, title, status, detail, o:errorCode); OTM's own
    error codes were not available, so o:errorCode is left out.
ASSUMPTION: the identity-domain token endpoint is /oauth2/v1/token on the same host; scopes are not checked.
ASSUMPTION: tracking-event status codes are the X12 214 codes in domain PUBLIC (PUBLIC.AF, PUBLIC.X1, PUBLIC.D1);
    the POD number is the D1 event's externalEventReference and the signer its ssContactName.
ASSUMPTION: planning happens synchronously in the POST (real OTM runs it in an agent, seconds later).
ASSUMPTION: lane distance and transit hours are kept on the xLane (attributeNumber1/2), as the demo pins them.
"""

from sim.mock import Mock
from sim.vendors.otm import api, seed

MOCK = Mock("tms", api.router, seed.ensure, seed.reset, "Oracle Transportation Management")
