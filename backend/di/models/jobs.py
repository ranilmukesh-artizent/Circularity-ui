"""The job queue di-worker claims from (migration 0001; di/core/jobs.py uses the ORM)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from di.models.base import Base

# --- 0001 job queue -------------------------------------------------------------------------------------------------


class Job(Base):
    """Background work for di-worker (sync, outbound instructions, webhooks).

    Claimed with FOR UPDATE SKIP LOCKED, so any number of workers can share the table.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_job_queue", "status", "run_after"),
        CheckConstraint("status IN ('queued','running','done','failed')", name="ck_job_status"),
    )
