"""IBM Sterling Order Management 10.0 mock (the demo's SOURCES.oms; docs/BACKEND_STEPS.md, B5).

Base path /sterling/smcfs/restapi (sim/registry.py). Data model and seed: see seed.py.

Auth: OAuth 2.0 client credentials.
    POST /sterling/smcfs/restapi/oauth/token   (also /sterling/oauth2/token)
         grant_type=client_credentials, client via HTTP Basic or client_id/client_secret form fields
         demo client: di-connector / circularity-demo-sterling-secret   → {"access_token", "token_type": "Bearer", ...}
    Every other call needs `Authorization: Bearer <token>` (1 hour). Errors, Sterling style:
         {"errors": [{"ErrorCode": "YFS10001", "ErrorDescription": "...", "httpcode": 401}]}

Reads (getOrderList style; paging with PageNumber (1-based) and PageSize (default 50, max 200)):
    GET /order          sales orders (DocumentType 0001 unless given). Filters: OrderNo, EnterpriseCode, DocumentType,
                        BuyerOrganizationCode (CUSTOMER_A), ShipToKey, ItemID, SerialNo, Status (the order's
                        MinOrderStatus code, e.g. 1100), FromModifyts / ToModifyts (ISO 8601, inclusive; the delta read)
                        → {"TotalOrderList", "PageNumber", "PageSize", "IsLastPage": "Y"|"N", "LastOrderHeaderKey",
                           "Order": [...]}
    GET /order/{OrderHeaderKey}          one order (sales or return) with OrderLines.OrderLine[]
    GET /order/{OrderHeaderKey}/lines    → {"TotalLineList", "OrderLine": [...]}
    GET /return         return orders (DocumentType 0003), same filters plus ReceivingNode; SerialNo = asset id
    GET /return/{OrderHeaderKey}
Writes (JSON bodies):
    POST /order/allocate   {"OrderHeaderKey" | "OrderNo" [+ "EnterpriseCode", "DocumentType"], "PrimeLineNo",
                            "SubLineNo" (default 1), "SerialNo": the returned unit (asset id), "ShipNode" (default: the
                            node that received the return), "ProductClass" (default REFURB), "Reference"}
                           optional header Idempotency-Key: the same request again answers 200 instead of 409.
                           Reserves the unit to the line (OrderLineReservations) and moves it 1100 → 1500.
                           Refused: line already allocated (409 YFS10260), unit allocated elsewhere (409 YFS10261),
                           line needs a new unit / item (spec) or quantity mismatch / not a sales order (400 YFS10255),
                           unit not a received return (404 YFS10005), line not Created (409 YFS10270).
    POST /order/{OrderHeaderKey}/fulfil   {"PrimeLineNo", "SubLineNo", "Action": RELEASE | SHIP | DELIVER (default:
                           the next one), SHIP: "SCAC", "TrackingNo", "ShipDate"; DELIVER: "ProofOfDelivery":
                           {"ReceivedBy" (required), "DeliveryDate", "PODReference", "Remarks"}}
                           One step per call, in order; anything else is 409 YFS10270.
Status codes: 1100 Created, 1500 Scheduled (unit allocated), 3200 Released, 3700 Shipped, 3700.7777 Delivered (proof
of delivery), 3900 Return Received, 9000 Cancelled. Other errors: 400 YFC0101 bad input, 404 YFS10003 order,
404 YFS10004 order line. Times are rendered in IST (+05:30), as the demo's mapping shows ReqDeliveryDate.
Outbox events (source "oms", subject OrderHeaderKey): sterling.order.allocated, sterling.order.released,
sterling.order.shipped, sterling.order.fulfilled (delivered).
"""

from sim.mock import Mock
from sim.vendors.sterling import api, seed

MOCK = Mock("oms", api.router, seed.ensure, seed.reset, "IBM Sterling OMS")
