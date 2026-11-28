"""Response shapes of the Analytics "View data" reads (plan 11, writer G1): the rows behind a chart, and the open decisions by
age. What each field means: di.services.screens.analytics_rows and di.services.screens.analytics_open."""

from typing import Any, Literal

from pydantic import BaseModel

ColumnKind = Literal["text", "money", "number", "date", "days", "percent"]


class RowColumn(BaseModel):
    key: str
    label: str
    kind: ColumnKind
    unit: str | None = None


class RowsSum(BaseModel):
    """The figure the rows add up to: `value` over the `n` rows of the selection (before the search box)."""

    label: str
    value: float
    unit: str
    n: int


class RowsAnswer(BaseModel):
    title: str
    subtitle: str
    columns: list[RowColumn]
    rows: list[dict[str, Any]]
    total: int  # rows after the search box (the table's count)
    of: int  # rows of the selection before the search box (the figure's count)
    shown: int
    period: str
    tenants: list[str]
    totals: dict[str, float]  # money columns, over every row counted in `total`
    sum: RowsSum | None
    truncated: bool  # more rows than one export holds (`total` > the export cap)
    can_export: bool


class RowsRef(BaseModel):
    """What opens the rows behind a number: the query parameters of GET /api/screens/analytics/rows."""

    source: Literal["decisions", "cases"]
    chart: str
    key: str


class AgeRoute(BaseModel):
    id: str
    name: str
    n: int
    value: float
    rows: RowsRef


class AgeBand(BaseModel):
    key: str
    label: str
    n: int
    value: float
    rows: RowsRef
    routes: list[AgeRoute]


class OpenAge(BaseModel):
    as_of: str
    basis: str
    total: dict[str, float]
    routes: list[dict[str, str]]
    bands: list[AgeBand]
