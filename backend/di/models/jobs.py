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
    # queued | running | done | failed | dead (out of attempts, 0018) | cancelled (0018)
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # --- 0018 (plan 2): priorities, dead letters, heartbeats, dedupe keys, the errors of past attempts
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")  # lower runs first
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        Index("ix_job_queue", "status", "run_after"),
        Index("ix_job_claim", "status", "priority", "run_after", "id"),
        Index("ux_job_dedupe", "dedupe_key", unique=True, postgresql_where=text("status IN ('queued','running')")),
        CheckConstraint("status IN ('queued','running','done','failed','dead','cancelled')", name="ck_job_status"),
    )
