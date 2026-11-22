"""GET /api/stream, the live updates as Server-Sent Events (di.services.stream: sources, fan-out, wire format)."""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from di.services import stream as live

router = APIRouter(tags=["live updates"])


@router.get("/api/stream")
async def stream(
    request: Request,
    ticket: Annotated[str | None, Query(description="a stream ticket from POST /api/auth/stream-ticket, for EventSource")] = None,
    last_event_id: Annotated[int | None, Query(description="resume after this event id")] = None,
    authorization: Annotated[str | None, Header()] = None,
    last_event_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    # checked once, here: the stream keeps running after a ticket expires (a reconnect fetches a new one)
    p = await run_in_threadpool(live.principal, authorization, ticket)  # a database read: off the event loop
    resume = last_event_id
    if resume is None and last_event_header and last_event_header.isdigit():
        resume = int(last_event_header)
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return StreamingResponse(live.events(p, resume, request.is_disconnected), media_type="text/event-stream", headers=headers)
