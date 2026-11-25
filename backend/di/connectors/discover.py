"""Source Tables from what the source really sends (plan 6, task B5).

    discover(s, "workday")   → [{"n": "workers", "cols": [["worker_id", "Record key · text"], ...], "rows": "1.2K", ...}]
    suggest_fks(s, "workday", tables) → [["workers.dept_id", "departments.dept_id", "Suggested: 100% of ... match"]]

One table per resource landed in `raw_record`: its columns are the union of the payload keys of a sample of the newest
500 records, each with an inferred type (text, number, bool, date, datetime, object, list); the record's id field comes
first (the connection's `id_field` for the resource when it has one, else the key whose values are the records'
ext_id, else `id`). A foreign key is suggested where at least 90 % of a column's distinct sampled values are keys
(ext_id) of another table of the same source.

A sample from the test connection (P9-8.3): `sample_test` reads up to 500 records per resource from a connection in the
test environment into raw_record, marked dry (`request` starts with DRY), so this module's reads and the field mapping
suggestions (P9-8.2) see them; no canonical fact is written. Owns: that read. Never does: call another host than the
connection's, read a production connection, map or write facts.

Which sources: the ones created in the Connection Fabric (from the catalogue or by hand). The demo's 21 sources keep
their table models as the demo seeds them (workspace collection "table_models"), discovered or not, so the golden
screens do not change.

Kept with what people did (tables.update): a source's discovered model is materialised into "table_models" the first
time a person changes it, marked `"discovered": true`. Its tables a person added or edited carry `"manual": true` and
are kept as they are; the others are rediscovered on every read (keeping the position a person dragged them to);
foreign keys a person added stay, suggested ones a person removed (`fkOff`) are not suggested again.
"""

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import golden

SAMPLE = 500
FK_MATCH = 0.9
FK_MIN_VALUES = 2
CLUSTER = ["data", "Source tables"]
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def demo_ids() -> set[str]:
    return {x["id"] for x in golden.load("sources")["sources"]}


def _type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int | float):
        return "number"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "list"
    if isinstance(v, datetime):
        return "datetime"
    if isinstance(v, date):
        return "date"
    s = str(v)
    if _DATETIME.match(s):
        return "datetime"
    if _DATE.fullmatch(s):
        return "date"
    return "text"


def _infer(values: list[Any]) -> str:
    """One type for a column: the type of every non-null value, else the widest (datetime over date, text over all)."""
    kinds = {_type(v) for v in values if v is not None}
    if not kinds:
        return "text"
    if len(kinds) == 1:
        return kinds.pop()
    if kinds <= {"date", "datetime"}:
        return "datetime"
    return "text"


def _rows_label(n: int) -> str:
    """The table card's row count, as the demo writes it (950, 1.2K, 48K, 1.3M)."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        v = n / 1000
        return (f"{v:.1f}".rstrip("0").rstrip(".") if v < 10 else str(round(v))) + "K"
    v = n / 1_000_000
    return f"{v:.1f}".rstrip("0").rstrip(".") + "M"


def _name(resource: str) -> str:
    """A table name the Source Tables page accepts: letters, digits and underscores, starting with a letter."""
    n = re.sub(r"\W+", "_", resource).strip("_") or "records"
    return n if n[0].isalpha() else "t_" + n


def _id_fields(s: Session, source_id: str) -> dict[str, str]:
    """The connection's id field per resource (plan 6 A2/A3), when it has a connection row."""
    try:
        with s.begin_nested():
            res = s.execute(text("SELECT resources FROM source_connection WHERE source_id = :s"), {"s": source_id}).scalar()
    except Exception:  # noqa: BLE001 - no connection table or row: infer the id field from the records
        return {}
    out = {}
    for r in res or []:
        if isinstance(r, dict) and r.get("name") and r.get("id_field"):
            out[str(r["name"])] = str(r["id_field"])
    return out


def _samples(s: Session, source_id: str) -> dict[str, list[tuple[str, dict]]]:
    rows = s.execute(
        text(
            "SELECT resource, ext_id, payload FROM (SELECT resource, ext_id, payload, row_number() OVER "
            "(PARTITION BY resource ORDER BY fetched_at DESC, ext_id) AS rn FROM raw_record WHERE source_id = :s) x "
            "WHERE rn <= :n ORDER BY resource, rn"
        ),
        {"s": source_id, "n": SAMPLE},
    ).all()
    out: dict[str, list[tuple[str, dict]]] = {}
    for r in rows:
        if isinstance(r.payload, dict):
            out.setdefault(r.resource, []).append((r.ext_id, r.payload))
    return out


def _id_field(resource: str, recs: list[tuple[str, dict]], cols: list[str], given: dict[str, str]) -> str | None:
    if given.get(resource) in cols:
        return given[resource]
    best = None
    for c in cols:
        hits = sum(1 for ext, p in recs if p.get(c) is not None and str(p.get(c)) == ext)
        if recs and hits / len(recs) >= FK_MATCH and (best is None or hits > best[1]):
            best = (c, hits)
    if best:
        return best[0]
    return next((c for c in cols if c.lower() == "id"), None)


def discover(s: Session, source_id: str) -> list[dict]:
    """The tables the source's landed records show (see the module docstring); [] when nothing has landed."""
    samples = _samples(s, source_id)
    if not samples:
        return []
    counts: dict[str, int] = dict(
        s.execute(text("SELECT resource, count(*) FROM raw_record WHERE source_id = :s GROUP BY resource"), {"s": source_id})
        .tuples()
        .all()
    )
    given = _id_fields(s, source_id)
    tables = []
    for i, (res, recs) in enumerate(sorted(samples.items())):
        cols: list[str] = []
        for _, p in recs:
            cols.extend(k for k in p if k not in cols)
        key = _id_field(res, recs, cols, given)
        if key:
            cols = [key] + [c for c in cols if c != key]
        view = [
            [c, ("Record key · " if c == key else "") + _infer([p.get(c) for _, p in recs])]
            for c in cols
            if re.fullmatch(r"[A-Za-z_][\w$]*", c)
        ]
        tables.append(
            {
                "cl": CLUSTER[0], "cols": view, "desc": f"Discovered from the {res} records this source sends.",
                "n": _name(res), "rows": _rows_label(int(counts.get(res, len(recs)))), "x": 24 + (i % 4) * 230,
                "y": 58 + (i // 4) * 200, "auto": True, "resource": res, "key": key,
            }
        )  # fmt: skip
    return tables


def suggest_fks(s: Session, source_id: str, tables: list[dict]) -> list[list[str]]:
    """Foreign keys: a column whose distinct sampled values are ≥ 90 % keys (ext_id) of another table of the source."""
    samples = _samples(s, source_id)
    keys: dict[str, set[str]] = {}
    for t in tables:
        if t.get("key"):
            keys[t["n"]] = set(
                s.execute(
                    text("SELECT ext_id FROM raw_record WHERE source_id = :s AND resource = :r"),
                    {"s": source_id, "r": t["resource"]},
                ).scalars()
            )
    out = []
    for a in tables:
        recs = samples.get(a["resource"], [])
        for col, _ in a["cols"]:
            if col == a.get("key"):
                continue
            vals = {str(p[col]) for _, p in recs if p.get(col) is not None and not isinstance(p.get(col), dict | list | bool)}
            if len(vals) < FK_MIN_VALUES:
                continue
            for b in tables:
                if b is a or b["n"] not in keys:
                    continue
                share = len(vals & keys[b["n"]]) / len(vals)
                if share >= FK_MATCH:
                    out.append(
                        [f"{a['n']}.{col}", f"{b['n']}.{b['key']}", f"Suggested: {round(share * 100)}% of the values match"]
                    )
                    break
    return out


def merge(s: Session, source_id: str, stored: dict | None) -> dict | None:
    """The source's table model now: discovered tables, with what people did (stored) kept. None: nothing to show."""
    found = discover(s, source_id)
    if not found and not stored:
        return None
    stored = stored or {}
    old = {t["n"]: t for t in stored.get("t") or []}
    tables = []
    for t in found:
        prev = old.get(t["n"])
        if prev is not None and prev.get("manual"):
            tables.append(prev)
            continue
        if prev is not None:
            t = t | {"x": prev.get("x", t["x"]), "y": prev.get("y", t["y"])}
        tables.append(t)
    names = {t["n"] for t in tables}
    tables += [t for t in stored.get("t") or [] if t.get("manual") and t["n"] not in names]
    names = {t["n"] for t in tables}
    cols = {t["n"]: {c[0] for c in t["cols"]} for t in tables}

    def ok(ref: str) -> bool:
        tn, _, cn = ref.partition(".")
        return tn in names and cn in cols[tn]

    off = {tuple(f) for f in stored.get("fkOff") or []}
    fk = [f for f in stored.get("fk") or [] if not str(f[2] if len(f) > 2 else "").startswith("Suggested:")]
    fk = [f for f in fk if ok(f[0]) and ok(f[1])]
    have = {(f[0], f[1]) for f in fk}
    fk += [
        f
        for f in suggest_fks(s, source_id, [t for t in tables if t.get("auto")])
        if (f[0], f[1]) not in have | off and ok(f[0]) and ok(f[1])
    ]
    cl = stored.get("cl") or [CLUSTER]
    if not any(c[0] == CLUSTER[0] for c in cl):
        cl = [*cl, CLUSTER]
    return {"cl": cl, "t": tables, "fk": fk, "discovered": True, "fkOff": [list(f) for f in off]}


def configured_sources(s: Session) -> list[str]:
    """Sources created in the Connection Fabric that have landed records."""
    return list(
        s.execute(
            text(
                "SELECT id FROM source_system s WHERE NOT (id = ANY(:d)) AND id <> 'manual' "
                "AND EXISTS (SELECT 1 FROM raw_record r WHERE r.source_id = s.id) ORDER BY id"
            ),
            {"d": sorted(demo_ids())},
        ).scalars()
    )


def with_discovered(s: Session, stored: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """The table models the screens show: the stored ones (the demo's exactly as stored), a discovered source's
    merged with what it sends now, and a configured source's discovered model when nothing is stored for it."""
    demo = demo_ids()
    out: list[tuple[str, dict]] = []
    seen = set()
    for sid, m in stored:
        seen.add(sid)
        if m.get("discovered") and sid not in demo:
            merged = merge(s, sid, m)
            if merged is not None:
                out.append((sid, merged))
        else:
            out.append((sid, m))
    for sid in configured_sources(s):
        if sid not in seen and (found := merge(s, sid, None)) is not None:
            out.append((sid, found))
    return out


def materialize(s: Session, source_id: str) -> dict | None:
    """The model tables.update changes for a configured source with nothing stored yet: its discovered model."""
    if source_id in demo_ids():
        return None
    return merge(s, source_id, None)


# ---------------------------------------------------------------- a sample from the test connection (plan 9, P9-8.3)
DRY = "dry-run sample"  # raw_record.request of a row read by sample_test: quarantined, never mapped to a fact
PAGE_CAP = 25  # requests per resource
TIME_BUDGET_S = 60.0
_POSITIONAL = ("offset", "page_number")
TEST_ONLY = "Samples are read from the test connection only."


class _Stop(Exception):
    """The page cap or the time budget is spent: keep what was read."""


def open_client(s: Session, source_id: str, adapter: Any) -> Any:
    """A client on the connection's URL, signed in with its stored secret (a module function so tests can fake it)."""
    from di.connectors import connection

    connection.check_credential(s, source_id)
    return connection.client_for(s, source_id, adapter)


def _pin_host(client: Any) -> None:
    """Egress allow-list: this client calls the connection's own host only; a next link elsewhere is refused."""
    import httpx

    from di.connectors.http import SourceError

    base = httpx.URL(client.base_url)
    allowed = (base.scheme, base.host, base.port)

    def check(req: Any) -> None:
        u = req.url
        if (u.scheme, u.host, u.port) != allowed:
            raise SourceError("client", f"Refused a call to {u.host}: discovery reads {base.host} only.")

    client.http.event_hooks = {"request": [check]}


class _Reader:
    """One resource's reads: counts requests, honours the page cap and the time budget."""

    def __init__(self, adapter: Any, client: Any, res: dict[str, Any], deadline: float):
        self.adapter, self.client, self.res, self.deadline = adapter, client, res, deadline
        self.requests = 0
        self.kind, self.p = adapter.kind, adapter.paging
        self.size = max(1, int(self.p.get("max_size") or 100))
        self.selector = str(res.get("data_selector") or self.p["items_key"])

    def tick(self) -> None:
        import time

        if self.requests >= PAGE_CAP or time.monotonic() >= self.deadline:
            raise _Stop
        self.requests += 1

    def fetch(self, start: int, n: int) -> tuple[list[dict], int | None, str]:
        """The rows at position `start` (n of them for offset paging, a whole page for page_number), the total when the
        body names it, and the request URL."""
        from di.connectors.configured import _dig

        self.tick()
        p = self.p
        q = (
            {p["limit_param"]: n, p["offset_param"]: start}
            if self.kind == "offset"
            else {p["size_param"]: self.size, p["page_param"]: start // self.size + 1}
        )
        resp = self.client.request("GET", str(self.res["path"]), params=q)
        body = resp.json()
        found = _dig(body, self.selector) if isinstance(body, dict) else body
        rows = [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []
        self.client.note_records(len(rows))
        raw = _dig(body, str(p["total_key"])) if p.get("total_key") and isinstance(body, dict) else None
        return rows, int(str(raw)) if str(raw).isdigit() else None, str(resp.request.url)


def _positional(rd: _Reader, limit: int) -> tuple[list[tuple[dict, str]], bool]:
    """Half from the newest pages (position 0 on), half spread over the rest of the window when the body names a total,
    else the newest `limit`. Returns (row, url) pairs and whether the spread was used."""
    out: list[tuple[dict, str]] = []
    pos, total, done, spread = 0, None, False, False

    def head(goal: int) -> None:
        nonlocal pos, total, done
        while len(out) < goal and not done:
            n = min(rd.size, goal - len(out))
            rows, t, url = rd.fetch(pos, n)
            total = t if t is not None else total
            out.extend((r, url) for r in rows[:n])
            pos += len(rows)
            done = len(rows) < (n if rd.kind == "offset" else rd.size)

    try:
        head((limit + 1) // 2)
        if done:
            return out, False
        if total is None:  # no total: no window to spread over; the newest `limit`
            head(limit)
            return out, False
        window = total - pos
        want = min(limit - len(out), window)
        if want <= 0:
            return out, False
        m = -(-want // rd.size)
        sizes = [want // m + (1 if i < want % m else 0) for i in range(m)]
        slack, cum, spread = window - want, 0, True
        for i, n in enumerate(sizes):
            start = pos + cum + (slack * i // (m - 1) if m > 1 else slack // 2)
            if rd.kind == "page_number":
                start -= start % rd.size
            rows, _, url = rd.fetch(start, n)
            out.extend((r, url) for r in rows[:n])
            cum += n
    except _Stop:
        pass
    return out, spread


def _sequential(rd: _Reader, limit: int) -> list[tuple[dict, str]]:
    """Any other paging (links, cursors, a dependent resource): the adapter's own pages, stopped at `limit`."""
    out: list[tuple[dict, str]] = []
    urls: set[str] = set()
    try:
        for row, url in rd.adapter.pages(rd.client, rd.res, None):
            if url not in urls:
                rd.tick()  # one tick per page the adapter fetched
                urls.add(url)
            out.append((row, url))
            if len(out) >= limit:
                break
    except _Stop:
        pass
    return out


def _land(s: Session, source_id: str, resource: str, rows: list[tuple[str, dict, str]]) -> None:
    """Store the sample as raw records marked dry; a record a real sync landed is left as it is."""
    import json

    for ext, row, url in rows:
        s.execute(
            text(
                "INSERT INTO raw_record (source_id, resource, ext_id, payload, request, fetched_at) "
                "VALUES (:s, :r, :e, CAST(:p AS jsonb), :q, now()) ON CONFLICT (source_id, resource, ext_id) "
                "DO UPDATE SET payload = EXCLUDED.payload, request = EXCLUDED.request, fetched_at = now() "
                "WHERE raw_record.request LIKE :dry"
            ),
            {"s": source_id, "r": resource, "e": ext, "p": json.dumps(row, default=str), "q": f"{DRY}: {url}"[:2000],
             "dry": DRY + "%"},
        )  # fmt: skip


def sample_report(
    s: Session, source_id: str, limit: int = SAMPLE, time_budget_s: float = TIME_BUDGET_S, client: Any = None
) -> dict[str, dict[str, Any]]:
    """Read up to `limit` records per resource from the TEST connection into the raw store, marked dry; writes no fact.
    Returns {resource: {"read": n, "spread": bool}}. Raises ValueError outside the test environment, SourceError when
    the system fails or a next link leaves the connection's host. `client` is for tests (the fake host)."""
    import time

    from di.connectors import connection, registry

    if not connection.in_test(s, source_id):
        raise ValueError(TEST_ONLY)
    adapter: Any = registry.adapter_for(s, source_id)
    if adapter is None or not hasattr(adapter, "pages"):
        raise ValueError(f"{source_id} has no resources to read.")
    owned = client is None
    client = client or open_client(s, source_id, adapter)
    _pin_host(client)
    deadline = time.monotonic() + time_budget_s
    report: dict[str, dict[str, Any]] = {}
    try:
        for res in adapter.conn.resources or []:
            if not res.get("name") or not res.get("path"):
                continue
            rd = _Reader(adapter, client, res, deadline)
            if rd.kind in _POSITIONAL and "{resources." not in str(res["path"]):
                rows, spread = _positional(rd, limit)
            else:
                rows, spread = _sequential(rd, limit), False
            seen: dict[str, tuple[dict, str]] = {}
            for row, url in rows:
                seen.setdefault(adapter._ext_id(row, res.get("id_field")), (row, url))
            _land(s, source_id, str(res["name"]), [(e, r, u) for e, (r, u) in seen.items()])
            report[str(res["name"])] = {"read": len(seen), "spread": spread}
    finally:
        if owned:
            client.close()
    return report


def sample_test(
    s: Session, source_id: str, limit: int = SAMPLE, time_budget_s: float = TIME_BUDGET_S, client: Any = None
) -> dict[str, int]:
    """Resource → records read (see sample_report)."""
    return {r: v["read"] for r, v in sample_report(s, source_id, limit, time_budget_s, client).items()}
