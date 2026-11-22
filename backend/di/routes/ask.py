"""POST /api/ask, Ask Circularity: the answer streams as Server-Sent Events (di.services.ask.service lists the events)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from di.core.deps import CurrentPrincipal
from di.schemas.ask import AskBody
from di.services.ask.model import AskModel, get_model
from di.services.ask.service import answer_stream

router = APIRouter(tags=["ask"])


@router.post("/api/ask")
def ask(body: AskBody, p: CurrentPrincipal, model: Annotated[AskModel, Depends(get_model)]) -> StreamingResponse:
    """Ask Circularity: the answer streams as Server-Sent Events (see di.services.ask.service for the events)."""
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(answer_stream(body, p, model), media_type="text/event-stream", headers=headers)
