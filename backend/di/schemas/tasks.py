"""Request and response shapes of the task endpoints (di.routes.tasks, plan 2): a task is a background job."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    kind: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int | None = None  # lower runs first; default 100
    run_after: datetime | None = None  # not before this time
    dedupe_key: str | None = None  # one queued or running task per key: a second enqueue returns the first


class TaskPatch(BaseModel):
    action: Literal["retry", "cancel", "reprioritise"]
    priority: int | None = None  # for reprioritise


class Task(BaseModel):
    id: int
    kind: str
    payload: dict[str, Any]
    status: str  # queued | running | done | failed | dead | cancelled
    priority: int
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[Task]
    next_cursor: str | None
