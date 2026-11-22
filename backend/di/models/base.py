"""What every model module shares: the metadata on Base and the timestamp column helper."""

from sqlalchemy import (
    Column,
    DateTime,
    func,
)

from di.core.db import Base

metadata = Base.metadata


def ts(name: str, *, nullable: bool = True, now: bool = False) -> Column:
    """A timestamp with time zone; `now` = NOT NULL DEFAULT now()."""
    if now:
        return Column(name, DateTime(timezone=True), nullable=False, server_default=func.now())
    return Column(name, DateTime(timezone=True), nullable=nullable)


__all__ = ["Base", "metadata", "ts"]
