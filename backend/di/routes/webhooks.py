"""The /api/webhooks endpoints: change events from the source systems (di.connectors.webhook: signature, replay window,
dedupe, the delta sync and the triggers they queue).

    POST /api/webhooks/source-sim      the shared source-sim subscription (X-Sim-Signature)
    POST /api/webhooks/{source_id}     one source's own webhook (X-Signature, or X-Sim-Signature)
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request
from starlette.concurrency import run_in_threadpool

from di.connectors import webhook

router = APIRouter(prefix="/api/webhooks", tags=["Connectors"])


@router.post("/source-sim", status_code=202)
async def source_event(request: Request, x_sim_signature: Annotated[str | None, Header()] = None):
    body = await request.body()  # as received: the signature covers its exact bytes
    # the database work blocks, so it runs in the thread pool instead of on the event loop
    return await run_in_threadpool(webhook.source_sim_event, body, x_sim_signature)


@router.post("/{source_id}", status_code=202)
async def own_source_event(
    source_id: str,
    request: Request,
    x_signature: Annotated[str | None, Header()] = None,
    x_sim_signature: Annotated[str | None, Header()] = None,
):
    body = await request.body()  # as received: the signature covers its exact bytes
    return await run_in_threadpool(webhook.own_source_event, source_id, body, x_signature or x_sim_signature)
