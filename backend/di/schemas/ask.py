"""The request body of POST /api/ask (di.routes.ask; answered by di.services.ask.service)."""

from pydantic import BaseModel, Field


class AskObject(BaseModel):
    kind: str = Field(..., description="case, kpi, source, workflow, exception or event")
    id: str = Field(..., max_length=64)


class AskContext(BaseModel):
    page: str | None = Field(None, max_length=40)
    section: str | None = Field(None, max_length=40)
    case_id: str | None = Field(None, max_length=16)
    object: AskObject | None = None


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    context: AskContext = Field(default_factory=AskContext)
    conversation_id: str | None = Field(None, max_length=32)
