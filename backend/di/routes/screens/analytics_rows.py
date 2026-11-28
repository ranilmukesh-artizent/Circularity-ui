"""The "View data" reads of Analytics (plan 11, writer G1): the rows behind a chart, their CSV, and the open decisions by age.
What they serve and who may read them: di.services.screens.analytics_rows and di.services.screens.analytics_open."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from di.core.deps import CurrentPrincipal, DbSession
from di.schemas.analytics_rows import OpenAge, RowsAnswer
from di.services.actions.pipeline import ERROR_STATUS, Actor, CallContext, invoke
from di.services.screens import analytics_open as open_svc
from di.services.screens import analytics_rows as svc

router = APIRouter(prefix="/api/screens/analytics", tags=["screens: analytics"])

Source = Annotated[Literal["decisions", "cases"], Query()]
Days = Annotated[int, Query(ge=0, le=730)]
Dir = Annotated[Literal["asc", "desc"], Query(alias="dir")]
Q = Annotated[str, Query(max_length=100)]


@router.get("/rows", response_model=RowsAnswer)
def rows(
    p: CurrentPrincipal,
    session: DbSession,
    source: Source,
    chart: str,
    key: str = "all",
    tenant: str = "",
    cls: str = "",
    route: str = "",
    from_: Annotated[int, Query(alias="from")] = 0,
    to: int = 11,
    model: str = "",
    tenant_filter: str = "All",
    org: str = "",
    days: Days = 0,
    sort: str = "",
    dir_: Dir = "desc",
    q: Q = "",
    limit: int = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    p.require_page("analytics")
    f = svc.Filters(tenant, cls, route, from_, to, model, tenant_filter, org, days)
    return svc.rows(session, p, source, chart, key, f, sort, dir_, q, limit, offset)


@router.get("/rows.csv")
def rows_csv(
    p: CurrentPrincipal,
    session: DbSession,
    source: Source,
    chart: str,
    key: str = "all",
    tenant: str = "",
    cls: str = "",
    route: str = "",
    from_: Annotated[int, Query(alias="from")] = 0,
    to: int = 11,
    model: str = "",
    tenant_filter: str = "All",
    org: str = "",
    days: Days = 0,
    sort: str = "",
    dir_: Dir = "desc",
    q: Q = "",
) -> Any:
    """The CSV, written to the journal first: the export is the action analytics.export (every write goes through the
    pipeline), which refuses an agent and the roles without the chart's section. The file is built only after it ran."""
    p.require_page("analytics")
    params: dict[str, Any] = {
        "source": source, "chart": chart, "key": key, "tenant": tenant, "cls": cls, "route": route, "from": from_, "to": to,
        "model": model, "tenant_filter": tenant_filter, "org": org, "days": days, "sort": sort, "dir": dir_, "q": q,
    }  # fmt: skip
    ctx = CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session, preparer=p.agent_id)
    result = invoke("analytics.export", params, ctx)
    if not result["ok"]:
        session.rollback()
        code = result["error"]["code"]
        return JSONResponse(result, status_code=422 if code == "validation_error" else ERROR_STATUS.get(code, 400))
    s = svc.export_selection(session, p, params)
    session.commit()
    return StreamingResponse(
        svc.csv_lines(s), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="circularity-{s.chart.id}.csv"'},
    )  # fmt: skip


@router.get("/open-age", response_model=OpenAge)
def open_age(p: CurrentPrincipal, session: DbSession, tenant_filter: str = "All", org: str = "") -> dict[str, Any]:
    p.require_page("analytics", "pipeline")
    return open_svc.open_age(session, p, tenant_filter, org)
