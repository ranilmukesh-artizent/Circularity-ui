"""The request body of POST /api/ask (di.routes.ask; answered by di.services.ask.service)."""

from pydantic import BaseModel, Field


class AskObject(BaseModel):
    kind: str = Field(..., description="case, kpi, source, workflow, run, flow, composition, exception or event")
    id: str = Field(..., max_length=64)
    label: str | None = Field(None, max_length=120, description="what the page calls it (shown, and told to the model as data)")


class AskContext(BaseModel):
    page: str | None = Field(None, max_length=40)
    section: str | None = Field(None, max_length=40)
    case_id: str | None = Field(None, max_length=16)
    object: AskObject | None = None
    org: str | None = Field(None, max_length=80, description="the org unit the page is about (the Modeler's)")


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    context: AskContext = Field(default_factory=AskContext)
    conversation_id: str | None = Field(None, max_length=32)
