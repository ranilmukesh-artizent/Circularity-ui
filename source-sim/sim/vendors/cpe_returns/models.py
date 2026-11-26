"""The CPE returns mock's tables (schema `cpe_returns`): the returns, the reset records, the lots and the forecast as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="cpe_returns")


def _table(name: str, key: str) -> Table:
    return Table(name, metadata, Column(key, String(40), primary_key=True), Column("doc", JSONB, nullable=False))


RETURN = _table("device_return", "serial")
RESET = _table("factory_reset", "serial")
LOT = _table("lot", "lot_id")
FORECAST = _table("forecast", "week")
