"""Manhattan Active Warehouse Management mock (the demo's SOURCES.wms; docs/BACKEND_STEPS.md, B5b).

Base /manhattan (sim/registry.py) stands for the tenant host (https://<tenant>.omni.manh.com); the paths below it are
Manhattan Active's component paths /<component>/api/<component>/<entity>/... .

Documentation followed (Manhattan's API reference is behind the customer/partner login; the public parts are the
conventions shown in Manhattan Active's developer portal and REST API overview):
    https://developer.manh.com/  (Manhattan Active Platform developer portal: REST conventions, OAuth token)
    https://www.manh.com/products/warehouse-management  (product scope: inventory, allocation, tasks, shipping)

Auth (Spring OAuth2, as Manhattan Active Platform):
    POST /manhattan/oauth/token  form grant_type=password&username=&password=  (or grant_type=client_credentials),
         client in HTTP Basic. Demo client di-connector / wms-demo-secret; demo user
         circularity.integration@northfield / wms-demo-password.
         -> {"access_token", "token_type": "bearer", "expires_in": 43199, "scope": "omni", "jti", ["refresh_token"]}
         Errors: 401 {"error": "unauthorized", ...} (client), 400 {"error": "invalid_grant", "error_description":
         "Bad credentials"} (user), 400 unsupported_grant_type.
    Every API call: Authorization: Bearer <token>, plus headers SelectedOrganization: NORTHFIELD and (facility-scoped
    calls) SelectedLocation: <FacilityId>. Bad/missing token: 401 {"error": "invalid_token", ...}.

Response envelope (every API call): {"header", "data", "messages": {"Message": [...], "Size"}, "success",
    "exceptions": [], "cloudComponent": "com-manh-cp-<component>", "cloudComponentHostName", "requestUri",
    "rootCause", "statusCode": "OK" | "BAD_REQUEST" | ...}. Errors carry success false and Message entries
    {"Type": "ERROR", "Code", "MessageKey": "com.manh.cp.<component>.<key>", "Description", "Args"}.

Search (POST <entity>/search, body {"Query": "<expr>", "Size": 1-1000 (default 100), "Page": 0-based,
    "Sort": [{"attribute", "direction"}]}; Query syntax in query.py: = != > >= < <= in, not in, like, is null,
    and/or, parentheses). data = the page's list; header = {"totalCount", "page", "size", "totalPages"}.
    Delta reads: Query "UpdatedTimestamp > '2026-10-07T09:00:00.000'".
    POST /facility/api/facility/facility/search            facilities (organization level)
    POST /item-master/api/item-master/item/search          items (organization level); GET .../item/itemId/{ItemId}
    POST /dcinventory/api/dcinventory/location/search      storage locations (SelectedLocation)
    POST /dcinventory/api/dcinventory/inventory/search     inventory; GET .../inventory/inventoryId/{InventoryId}
    POST /pix/api/pix/pix/search                           PIX (perpetual inventory transactions: RECEIPT,
                                                           INVENTORY_MOVE, SHIPMENT, INVENTORY_STATUS_CHANGE)
    POST /dcinventory/api/dcinventory/reservation/search   reservations; GET .../reservation/reservationId/{id}
    POST /dcorder/api/dcorder/order/search                 outbound/transfer orders; GET .../order/orderId/{OrderId}
    POST /task/api/task/task/search                        PICK and PACK tasks
    POST /shipment/api/shipment/shipment/search            shipments; GET .../shipment/shipmentId/{ShipmentId}
Writes (facility scoped by SelectedLocation):
    POST /dcinventory/api/dcinventory/reservation/save  {"ItemId", "Quantity", ["InventoryId", "OrderId",
         "ReferenceId", "ReservationId"]} -> RESERVED (id R-77101 ...). Allocates available stock (Allocated +=
         Quantity). Refused: not AVAILABLE (400 inventoryNotAvailable), already allocated (409 alreadyAllocated),
         short (400 insufficientInventory), unknown item (404).
    POST /dcinventory/api/dcinventory/reservation/cancel {"ReservationId"} -> CANCELLED, releases the allocation.
    POST /dcinventory/api/dcinventory/inventory/changeProductStatus {"InventoryId", "ProductStatusId" (AVAILABLE,
         HOLD, DAMAGED, QUARANTINE), "ReasonCode"}; refused while allocated (409). Writes a PIX.
    POST /dcorder/api/dcorder/order/save  {"OrderType": TRANSFER (warehouse move to DestinationFacilityId) |
         OUTBOUND (delivery to DestinationFacilityId or DestinationAddress), "ExternalReference" (the approved
         instruction), "CarrierId", "OrderLine": [{"ItemId", "OrderedQuantity", ["ReservationId" | "InventoryId"]}]}
         -> allocated (3000; consumes the reservation or allocates now), PICK tasks released. Then on the simulated
         clock: +2 h picked (7000: unit moved to <facility>-STAGE, PIX INVENTORY_MOVE, PACK task), +1 h packed (7200,
         oLPN), +1 h shipped (8000: OnHand and Allocated decremented at the source facility, PIX SHIPMENT,
         shipment with tracking number).
Outbox events (source "wms"): manhattan.reservation.created|cancelled|consumed, manhattan.inventory.statusChanged,
    manhattan.order.allocated|picked|packed|shipped.

Seed: one inventory record (InventoryId INV-<asset>, bin WH01-RT-09 style, InventoryAttribute1 = case id,
InventoryAttribute2 = owner) and one RECEIPT PIX per case; facilities WH01/WH02/RC01 and ST01-08.

ASSUMPTION: the exact entity field names (OnHand, Allocated, Available, ProductStatusId, InventoryAttribute1/2,
    PixId, TransactionType, ReservationId, ReservationStatus, FulfillmentStatus ...) follow Manhattan's PascalCase
    conventions; the field-level reference is not public.
ASSUMPTION: component paths for reservation, changeProductStatus, PIX search, task and shipment search follow the
    documented /<component>/api/<component>/<entity>/<action> pattern; their exact names are not public.
ASSUMPTION: search header keys (totalCount, page, size, totalPages), error MessageKeys and Codes are modelled.
ASSUMPTION: fulfilment status codes 3000/7000/7200/8000/9000 and the 2 h / 1 h / 1 h pick-pack-ship timings.
ASSUMPTION: ReservationId format R-77101.. (the demo's MAPPINGS.wms shows R-77102); UOM UNIT.
ASSUMPTION: the API stores no stock age; the client derives it from ReceivedDate.
"""

from sim.mock import Mock
from sim.vendors.manhattan import api, seed

MOCK = Mock("wms", api.router, seed.ensure, seed.reset, "Manhattan Active Warehouse Management")
