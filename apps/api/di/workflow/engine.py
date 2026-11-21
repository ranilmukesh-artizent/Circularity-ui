"""The workflow engine (plan 6, tasks C5 and C7): runs a workflow graph's steps over real records.

    run_graph(s, wf, graph, trigger="Manual")            -> RunResult(states, counts, dur_ms, rows, failed, error, ...)
    run_graph(s, wf, graph, trigger="Test", dry=True)    -> the same, writing nothing, with before/after samples
    default_graph("erp")                                 -> the ingest graph a source syncs with when none is bound

**What each block does.** Steps run in `studio._order` (the canvas' run order). A step gets the union of its
predecessors' records (`out`; the same record arriving twice by two paths counts once); an error handler (`x_err`) gets
their rejected records instead, and a branch's else path goes to its second successor (and to an error handler after
it). Per node kind:
- `conn` reads the source through its adapter (`registry.adapter_for`: the Python adapter, or the configured one for a
  catalogue or hand-made source) on its connection (`connection.client_for`: the URL and stored secret a person set),
  per resource from the sync cursor (setting `mode` delta, `lookback_days`) or in full; every record read is kept in
  `raw_record`. It holds the source's sync lock (`sync:<id>`, as `di.connectors.sync.run_sync` does) for the rest of
  the run, so a run and a sync of one source never interleave.
- `map` turns a record into canonical facts: the adapter's `map` with the mapping a person saved over it (A4,
  `mapping.mapper`), exactly as a sync maps.
- a canonical fixed step (`FXD[ref].canon`: c_asset, c_out ...) writes the facts through `store.apply` per record, in a
  savepoint (a deadlock with a concurrent writer is tried again), holding facts that do not fit their model in
  `failed_record` (B1, `schema.split_facts`); records without facts pass through.
- an `xf` block with an implementation runs it (`di.workflow.steps.STEPS`, settings from `blocks.node_cfg`); a block
  without one (file arrival, unzip, envelope, ...) and every other kind (tool, act, wconn, the other fixed steps) passes
  its records on.
Records a step rejects that no error handler takes are held in `failed_record` by the engine (unless the step's
`on_failure` is `reject`), so a rejected record is never silently lost.

**States.** A step's state comes first from its predecessors (as the demo's wfEval): one failed or upstream failed ->
`upstream_failed`; one held or waiting -> `waiting`; a step that needs input with none -> `skipped`. Otherwise it runs:
`success`, or `failed` when it raised (after its retries) or its source cannot be read (no adapter, paused,
disconnected, deleted: not retried). A node with `fail: true` (the canvas' failure toggle) raises, so a person can
rehearse a failure. The run's status is `failed` if a step failed, else `warning` if records were held, else `success`.

**Retries (C7).** A step that raises is tried again `retries` times, waiting `backoff * 2**n` seconds (1 s, 2 s, 4 s ...);
`attempts[node]` is how many tries it took (the run table's Try column). The session is rolled back before a retry,
so a half-written step leaves nothing behind but what it committed (the canonical step commits every COMMIT_EVERY
records, as a sync does; re-applying the same facts changes nothing).

**Dry runs.** With `dry`, nothing is written (no raw records, cursors, canonical facts, held records or published
events): every try of a step runs in a savepoint that is rolled back, so the caller's transaction is untouched. Each
step's first SAMPLE_N records before and after it are returned in `samples`. `sample` limits the records read per
connector.

**Progress.** `on_step(entry)` is called after every state change with {step, state, states, counts} (the counts of the
finished steps), which the run job writes into the run record so the live canvas follows the run.

**Sync.** `di.connectors.sync.run_sync` runs a source's bound ingest workflow (or `default_graph`) through this engine
with a `Feed` it opened (its sync_run id, its client), so a sync and a run of the ingest workflow are one data path.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from di.workflow.blocks import node_cfg
from di.workflow.steps import STEPS
from di.workflow.steps.core import Rec, Reject, StepCtx, StepError, StepResult, digest

log = logging.getLogger("di.workflow.engine")
COMMIT_EVERY = 200
SAMPLE_N = 3
NOT_READ = ("paused", "disconnected", "unavailable")  # statuses people set: such a source is not read
FAILED = ("failed", "upstream_failed")
HELD = ("held", "waiting")


class Unreadable(StepError):
    """The source cannot be read at all (no adapter, paused, deleted): the step fails without retries."""


@dataclass
class Feed:
    """How a connector step reads one source in this run, and what it read (for the cursors and the sync's counts)."""

    source_id: str
    adapter: Any
    client: Any = None
    run_id: Any = None  # the sync_run id the client logs its calls under (None for a workflow run)
    full: bool = False
    conf: float | None = None
    remap: Callable | None = None
    own: bool = False  # opened by the engine: it closes the client and releases the lock
    lock: Any = None
    newest: dict[str, str | None] = field(default_factory=dict)
    delta: set[str] = field(default_factory=set)
    bad: set[str] = field(default_factory=set)  # resources with a record that could not be mapped or stored
    read: int = 0
    written: int = 0
    failed: int = 0
    first_error: str | None = None

    def note_failure(self, resource: str, msg: str, cursor_stays: bool = True) -> None:
        self.failed += 1
        if cursor_stays:
            self.bad.add(resource)
        self.first_error = self.first_error or msg[:500]


@dataclass
class RunResult:
    states: dict[str, str]
    counts: dict[str, dict]
    dur_ms: dict[str, int]
    rows: int
    failed: int
    error: str | None
    order: list[str] = field(default_factory=list)
    status: str = "success"
    note: str = ""
    attempts: dict[str, int] = field(default_factory=dict)
    samples: dict[str, dict] = field(default_factory=dict)
    held: int = 0
    error_kind: str | None = None  # a SourceError's kind ("auth", ...) when a connector failed on the source
    steps: int = 0  # state changes reported (progress entries)

    def public(self) -> dict:
        return {
            "states": self.states, "counts": self.counts, "dur_ms": self.dur_ms, "rows": self.rows, "failed": self.failed,
            "error": self.error, "order": self.order, "status": self.status, "note": self.note, "attempts": self.attempts,
            "samples": self.samples, "held": self.held,
        }  # fmt: skip


def _fxd() -> dict:
    from di.reads.reference import lists

    return lists()["FXD"]


def label(n: dict) -> str:
    try:
        from di.actions.workflows import label as wf_label

        return wf_label(n)
    except Exception:  # noqa: BLE001 - a label is only for messages
        return str(n.get("ref") or n.get("id"))


def default_graph(source_id: str) -> dict:
    """The ingest graph a source syncs with when no published ingest workflow is bound to it: New workflow's minimal
    ingest graph (connector, ingestion, validation, field mapping, its canonical step), or for a source the demo does
    not know (catalogue, hand-made) connector -> mapping -> Outcome."""
    from di.actions.workflow_builder import minimal_graph

    try:
        g = minimal_graph({"k": "min", "type": "ingest", "src": source_id})
    except (KeyError, LookupError, TypeError):
        g = {
            "nodes": [
                {"id": "r", "k": "conn", "ref": source_id, "x": 24, "y": 170},
                {"id": "m", "k": "map", "ref": source_id, "x": 230, "y": 170},
                {"id": "c_out", "k": "fixed", "ref": "c_out", "x": 436, "y": 170},
            ],
            "edges": [{"a": "r", "b": "m", "locked": False}, {"a": "m", "b": "c_out", "locked": False}],
        }
    for i, e in enumerate(g["edges"]):
        e.setdefault("id", f"e{i}")
    return g


def refused(graph: dict, nid: str, msg: str) -> RunResult:
    """A run that did not start because the graph has an error at `nid`: that step failed, every step after it
    upstream failed, the others skipped."""
    from di.reads.workflows import _analyze, _order

    by, succ, _ = _analyze(graph)
    order = _order(graph)
    states = dict.fromkeys(order, "skipped")
    down, st = set(), [nid]
    while st:
        for y in succ.get(st.pop(), []):
            if y not in down:
                down.add(y)
                st.append(y)
    for d in down:
        states[d] = "upstream_failed"
    if nid in by:
        states[nid] = "failed"
    zero = {i: {"in": 0, "out": 0, "rej": 0} for i in order}
    note = msg[:94] + "…" if len(msg) > 96 else msg
    return RunResult(states, zero, dict.fromkeys(order, 0), 0, 0, msg, order, "failed", note)


class _Run:
    def __init__(self, s: Session, wf: dict, graph: dict, *, trigger: str, dry: bool, sample: int | None,
                 feeds: dict[str, Feed] | None, on_step: Callable[[dict], None] | None, retries: int, backoff: float,
                 sleep: Callable[[float], None], run_id: Any, run_kind: str, now: datetime | None, full: bool):  # fmt: skip
        from di.reads.workflows import _analyze, _order

        self.s, self.wf, self.g, self.trigger, self.dry, self.sample = s, wf, graph, trigger, dry, sample
        self.feeds: dict[str, Feed] = dict(feeds or {})
        self.on_step, self.retries, self.backoff, self.sleep = on_step, max(0, int(retries or 0)), backoff, sleep
        self.run_id, self.run_kind, self.full = run_id, run_kind, full
        from di import clock

        self.now = now or clock.now()
        self.by, self.succ, self.pred = _analyze(graph)
        self.order = _order(graph)
        self.states: dict[str, str] = dict.fromkeys(self.order, "queued")
        self.counts: dict[str, dict] = {}
        self.dur: dict[str, int] = {}
        self.attempts: dict[str, int] = {}
        self.samples: dict[str, dict] = {}
        self.outs: dict[str, list[Rec]] = {}
        self.rejs: dict[str, list[Reject]] = {}
        self.side: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.error_kind: str | None = None
        self.held = 0
        self.steps = 0
        self.fxd = _fxd()

    # ------------------------------------------------------------ progress
    def emit(self, nid: str, st: str) -> None:
        self.steps += 1
        if self.on_step is not None:
            done = {k for k, v in self.states.items() if v not in ("queued", "running")}
            self.on_step({"step": nid, "state": st, "states": dict(self.states),
                          "counts": {k: dict(v) for k, v in self.counts.items() if k in done}})  # fmt: skip

    # ------------------------------------------------------------ the walk
    def upstream(self, n: dict) -> str | None:
        ps = [self.states.get(p) for p in self.pred[n["id"]]]
        if any(x in FAILED for x in ps):
            return "upstream_failed"
        if any(x in HELD for x in ps):
            return "waiting"
        if n["k"] == "fixed":
            f = self.fxd.get(n["ref"]) or {}
            needs = bool(f.get("in") and not f.get("start"))
        else:
            needs = n["k"] != "conn"
        if needs and (not ps or all(x == "skipped" for x in ps)):
            return "skipped"
        return None

    def gather(self, n: dict) -> list:
        """The node's input: its predecessors' records (an error handler: their rejects and else paths)."""
        nid, err = n["id"], n["k"] == "xf" and n["ref"] == "x_err"
        got: list = []
        seen: set[tuple] = set()
        for p in self.pred[nid]:
            pn = self.by[p]
            if err:
                got.extend(self.rejs.get(p, []))
                if pn["k"] == "xf" and pn["ref"] == "x_branch":
                    got.extend(self.side.get(p, {}).get("else", []))
                continue
            recs = self.outs.get(p, [])
            if pn["k"] == "xf" and pn["ref"] == "x_branch":
                plain = [x for x in self.succ[p] if not (self.by[x]["k"] == "xf" and self.by[x]["ref"] == "x_err")]
                if len(plain) > 1 and plain.index(nid) == 1:
                    recs = self.side.get(p, {}).get("else", [])
            for r in recs:
                k = (r.resource, r.ext_id, digest(r.data))
                if k in seen:
                    continue
                seen.add(k)
                got.append(r)
        return got

    def run(self) -> RunResult:
        try:
            for nid in self.order:
                self.node(self.by[nid])
            if not self.dry:
                if not any(v in FAILED for v in self.states.values()):
                    self.settle_cursors()
                self.s.commit()
        finally:
            self.close_feeds()
        return self.result()

    def node(self, n: dict) -> None:
        nid = n["id"]
        if st := self.upstream(n):
            self.states[nid] = st
            self.counts[nid] = {"in": 0, "out": 0, "rej": 0}
            self.dur[nid] = 0
            self.emit(nid, st)
            return
        self.states[nid] = "running"
        self.emit(nid, "running")
        inp = self.gather(n)
        t0 = time.monotonic()
        tries, res, err = 0, None, None
        while True:
            tries += 1
            try:
                res = self.attempt(n, inp)
                err = None
                break
            except Unreadable as e:
                err = e
                break
            except Exception as e:  # noqa: BLE001 - any failure of a step fails the step (after its retries)
                err = e
                log.warning("step %s of %s failed (try %s): %s", nid, self.wf.get("id"), tries, e)
                if not self.dry:
                    self.s.rollback()  # what this try half wrote goes; the steps before it committed
                if tries > self.retries:
                    break
                self.sleep(self.backoff * 2 ** (tries - 1))
        self.attempts[nid] = tries
        self.dur[nid] = round((time.monotonic() - t0) * 1000)
        if err is not None or res is None:
            from di.connectors.http import SourceError

            if isinstance(err, SourceError):
                self.error_kind = err.kind
            self.errors[nid] = str(err) or type(err).__name__
            self.states[nid] = "failed"
            self.counts[nid] = {"in": len(inp), "out": 0, "rej": 0}
            self.outs[nid], self.rejs[nid] = [], []
            if not self.dry:
                self.s.rollback()
            self.emit(nid, "failed")
            return
        for r in res.out:
            r.meta["node"] = nid
        self.outs[nid], self.rejs[nid], self.side[nid] = res.out, res.rejected, res.side
        held_direct = int(res.side.get("schema_held") or 0)
        took = len(res.out) + len(res.rejected) if n["k"] == "conn" else len(inp)  # a connector takes what it reads
        self.counts[nid] = {"in": took, "out": len(res.out), "rej": len(res.rejected) + held_direct}
        if n["k"] == "xf" and n["ref"] == "x_err":
            self.held += int(res.side.get("held") or 0)
        self.held += held_direct
        if self.dry or self.sample is not None:
            self.samples[nid] = {
                "before": [_show(r) for r in inp[:SAMPLE_N]],
                "after": [_show(r) for r in res.out[:SAMPLE_N]],
            }
        if res.rejected and not self.has_handler(nid) and str(res.side.get("on_failure") or "hold") == "hold":
            self.hold(nid, res.rejected)
        waiting = res.side.get("waiting") or []
        self.states[nid] = "waiting" if waiting and not res.out else "success"
        if not self.dry:
            self.s.commit()
        self.emit(nid, self.states[nid])

    def has_handler(self, nid: str) -> bool:
        return any(self.by[x]["k"] == "xf" and self.by[x]["ref"] == "x_err" for x in self.succ[nid])

    def hold(self, nid: str, rejects: list[Reject]) -> None:
        if self.dry:
            self.held += len(rejects)
            return
        from di.canonical.failed import hold

        for j in rejects:
            hold(
                self.s, run_kind=self.run_kind, reason=j.reason, run_id=self.run_id,
                source_id=j.rec.meta.get("source_id") or self.source_id(), step=nid, resource=j.rec.resource,
                ext_id=j.rec.ext_id, field=j.field, rule=j.rule, value=j.value, payload=j.rec.data,
            )  # fmt: skip
        self.held += len(rejects)

    def source_id(self) -> str | None:
        c = next((n for n in self.g["nodes"] if n.get("k") == "conn"), None)
        return c["ref"] if c else self.wf.get("src")

    # ------------------------------------------------------------ one step
    def attempt(self, n: dict, inp: list) -> StepResult:
        """One try of a step. A dry run's try runs in a savepoint that is always rolled back: whatever a step or the
        source client writes is undone, and the caller's own transaction (an action's) is left as it was."""
        if not self.dry:
            return self.step(n, inp)
        sp = self.s.begin_nested()
        try:
            return self.step(n, inp)
        finally:
            sp.rollback()

    def step(self, n: dict, inp: list) -> StepResult:
        if n.get("fail"):
            raise StepError(f"{label(n)} failed")
        k, ref = n["k"], n["ref"]
        if k == "conn":
            return self.read(n)
        if k == "map":
            return self.map(n, inp)
        if k == "fixed" and (self.fxd.get(ref) or {}).get("canon"):
            return self.store(n, inp)
        if k == "xf" and ref in STEPS:
            ctx = StepCtx(self.s, self.run_id, self.wf, n, self.source_id(), self.now, self.dry, None)
            return STEPS[ref](inp, node_cfg(n), ctx)
        return StepResult([_pass(r) for r in inp], [], {})

    # ------------------------------------------------------------ connector
    def feed(self, sid: str, n: dict) -> Feed:
        if sid in self.feeds:
            return self.feeds[sid]
        from di.connectors import connection, lifecycle, mapping
        from di.connectors.registry import ADAPTERS, adapter_for
        from di.db import engine

        row = self.s.execute(text("SELECT status, confidence FROM source_system WHERE id = :i"), {"i": sid}).first()
        if row is None or lifecycle.is_deleted(self.s, sid):
            raise Unreadable(f"{label(n)} has no connected feed")
        if row.status in NOT_READ:
            raise Unreadable(f"{label(n)} is {row.status}")
        adapter = adapter_for(self.s, sid)
        if adapter is None:
            raise Unreadable(f"{label(n)} has no connected feed")
        lock = engine.connect()
        got = lock.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('sync:' || :s))"), {"s": sid}).scalar()
        if not got:
            lock.rollback()
            lock.close()
            raise StepError(f"{label(n)} is syncing now")  # retried: the sync ends soon
        try:
            connection.check_credential(self.s, sid)
            client = connection.client_for(self.s, sid, adapter, None)
        except Exception:
            lock.rollback()
            lock.close()
            raise
        f = Feed(sid, adapter, client, None, self.full, float(row.confidence) if row.confidence is not None else None,
                 mapping.mapper(self.s, sid, sid in ADAPTERS), True, lock)  # fmt: skip
        self.feeds[sid] = f
        return f

    def close_feeds(self) -> None:
        for f in self.feeds.values():
            if not f.own:
                continue
            try:
                if f.client is not None:
                    f.client.close()
            finally:
                if f.lock is not None:
                    f.lock.rollback()
                    f.lock.close()

    def read(self, n: dict) -> StepResult:
        from di.connectors.sync import _cursor

        sid = n["ref"]
        f = self.feed(sid, n)
        cfg = node_cfg(n)
        want = set(cfg.get("resources") or [])
        full = f.full or cfg.get("mode") == "full"
        back = int(cfg.get("lookback_days") or 0)
        out: list[Rec] = []
        f.read = 0
        for res in f.adapter.resources():
            if want and res.name not in want:
                continue
            if res.delta:
                f.delta.add(res.name)
            since = None if (full or not res.delta) else _cursor(self.s, sid, res.name)
            if since and back:
                since = _minus_days(since, back)
            newest = f.newest.get(res.name) or (None if full or not res.delta else _cursor(self.s, sid, res.name))
            for rec in res.read(f.client, since):
                f.read += 1
                if not self.dry:
                    self.s.execute(
                        text(
                            "INSERT INTO raw_record (source_id, resource, ext_id, payload, request, fetched_at) "
                            "VALUES (:s, :r, :e, CAST(:p AS jsonb), :q, now()) ON CONFLICT (source_id, resource, ext_id) "
                            "DO UPDATE SET payload = EXCLUDED.payload, request = EXCLUDED.request, fetched_at = now()"
                        ),
                        {"s": sid, "r": rec.resource, "e": rec.ext_id, "p": json.dumps(rec.payload, default=str),
                         "q": rec.request},
                    )  # fmt: skip
                    if f.read % COMMIT_EVERY == 0:
                        self.s.commit()
                meta = {"source_id": sid, "request": rec.request, "changed": rec.changed, "cursor": rec.changed}
                out.append(Rec(rec.ext_id, rec.resource, rec.payload, None, meta))
                if rec.changed and (newest is None or rec.changed > newest):
                    newest = rec.changed
                if self.sample is not None and len(out) >= self.sample:
                    break
            f.newest[res.name] = newest
            if self.sample is not None and len(out) >= self.sample:
                break
        return StepResult(out, [], {"read": f.read})

    def settle_cursors(self) -> None:
        """Each delta resource's cursor moves to the newest change read, unless a record of it could not be mapped or
        stored (then the next sync reads it again)."""
        from di.connectors.sync import _set_cursor

        for f in self.feeds.values():
            for res, newest in f.newest.items():
                if res in f.delta and newest and res not in f.bad:
                    _set_cursor(self.s, f.source_id, res, newest)

    # ------------------------------------------------------------ mapping
    def map(self, n: dict, inp: list[Rec]) -> StepResult:
        from di.connectors.base import Record
        from di.connectors.registry import adapter_for

        sid = n["ref"]
        f = self.feeds.get(sid)
        if f is None:
            a = adapter_for(self.s, sid)
            if a is None:
                raise Unreadable(f"{label(n)}: no field mapping for {sid}")
            from di.connectors import mapping
            from di.connectors.registry import ADAPTERS

            row = self.s.execute(text("SELECT confidence FROM source_system WHERE id = :i"), {"i": sid}).first()
            conf = float(row.confidence) if row and row.confidence is not None else None
            f = Feed(sid, a, None, self.run_id, self.full, conf, mapping.mapper(self.s, sid, sid in ADAPTERS))
            self.feeds[sid] = f
        out, rejected = [], []
        for r in inp:
            rec = Record(r.resource, r.ext_id, r.data, r.meta.get("request"), r.meta.get("changed"))
            try:
                facts = f.remap(rec, f.adapter.map(rec)) if f.remap else f.adapter.map(rec)
                facts = [
                    x if x.resource else type(x)(**{**x.__dict__, "resource": rec.resource, "ext_id": rec.ext_id}) for x in facts
                ]
            except Exception as e:  # noqa: BLE001 - a record that cannot be mapped is rejected, not fatal
                msg = f"{rec.resource}/{rec.ext_id}: {type(e).__name__}: {e}"
                f.note_failure(rec.resource, msg)
                log.warning("map failed %s %s", sid, msg)
                rejected.append(Reject(r, None, "map", None, msg[:500]))
                continue
            out.append(Rec(r.ext_id, r.resource, r.data, facts, {**r.meta, "source_id": r.meta.get("source_id") or sid}))
        return StepResult(out, rejected, {"on_failure": "hold"})

    # ------------------------------------------------------------ canonical
    def store(self, n: dict, inp: list[Rec]) -> StepResult:  # noqa: ARG002 - every node step takes its node
        from di.canonical import store as canon
        from di.canonical.failed import hold
        from di.canonical.schema import split_facts

        out, rejected, written, held, done = [], [], 0, 0, 0
        for r in inp:
            if r.facts is None:
                out.append(_pass(r))
                continue
            sid = r.meta.get("source_id") or self.source_id() or ""
            f = self.feeds.get(sid)
            conf = f.conf if f else None
            bad: list = []
            failed = None
            for attempt in range(3):
                try:
                    with self.s.begin_nested():
                        good, bad = split_facts(list(r.facts))
                        if not self.dry:
                            written += (w := canon.apply(self.s, sid, good, conf))
                            if f:
                                f.written += w
                            for fact, why in bad:
                                hold(
                                    self.s, run_kind=self.run_kind, run_id=self.run_id, source_id=sid, step="canonical",
                                    resource=r.resource, ext_id=r.ext_id, field=f"{fact.model}.{fact.field}",
                                    rule="schema", value=fact.value, reason=why, payload=r.data,
                                )  # fmt: skip
                    failed = None
                    break
                except OperationalError as e:  # a deadlock with a concurrent writer: try the record again
                    failed = f"{r.resource}/{r.ext_id}: {str(e).splitlines()[0]}"
                    if "deadlock" not in str(e).lower() or attempt == 2:
                        break
                    time.sleep(0.05 * (attempt + 1))
                except Exception as e:  # noqa: BLE001 - a record that cannot be stored is rejected, not fatal
                    failed = f"{r.resource}/{r.ext_id}: {type(e).__name__}: {e}"
                    log.warning("store failed %s %s", sid, failed)
                    break
            if failed:
                if f:
                    f.note_failure(r.resource, failed)
                rejected.append(Reject(r, None, "store", None, failed[:500]))
                continue
            if bad:  # held in failed_record; the cursor moves on (the record is kept there to reprocess)
                held += 1
                if f:
                    f.note_failure(r.resource, f"{r.resource}/{r.ext_id}: {bad[0][1]}", cursor_stays=False)
            out.append(_pass(r))
            done += 1
            if not self.dry and done % COMMIT_EVERY == 0:
                self.s.commit()
        return StepResult(out, rejected, {"written": written, "schema_held": held, "on_failure": "hold"})

    # ------------------------------------------------------------ the result
    def result(self) -> RunResult:
        for nid in self.order:
            self.counts.setdefault(nid, {"in": 0, "out": 0, "rej": 0})
            self.dur.setdefault(nid, 0)
        rows = sum(self.counts[n["id"]]["out"] for n in self.g["nodes"] if n.get("k") == "conn" and n["id"] in self.counts)
        failed_nodes = [nid for nid in self.order if self.states.get(nid) == "failed"]
        rejected = sum(c["rej"] for c in self.counts.values())
        error = None
        note = ""
        if failed_nodes:
            nid = failed_nodes[0]
            error = self.errors.get(nid) or f"{label(self.by[nid])} failed"
            msg = error if error.startswith(label(self.by[nid])) else f"{label(self.by[nid])} failed: {error}"
            note = msg[:94] + "…" if len(msg) > 96 else msg
            status = "failed"
        elif self.held:
            status = "warning"
            at = next((self.by[i] for i in self.order if self.counts[i]["rej"]), None)
            note = f"{self.held} record{'s' if self.held != 1 else ''} held" + (f" at {label(at)}" if at else "")
        else:
            status = "success"
        return RunResult(
            dict(self.states), self.counts, self.dur, rows, rejected, error, list(self.order), status, note,
            dict(self.attempts), self.samples, self.held, self.error_kind, self.steps,
        )  # fmt: skip


def _pass(r: Rec) -> Rec:
    """The record going on unchanged (a new holder, so the engine can stamp the step on it)."""
    return Rec(r.ext_id, r.resource, r.data, r.facts, dict(r.meta))


def _show(r: Any) -> dict:
    if isinstance(r, Reject):
        return {"ext_id": r.rec.ext_id, "resource": r.rec.resource, "rule": r.rule, "field": r.field, "reason": r.reason}
    out = {"ext_id": r.ext_id, "resource": r.resource, "data": r.data}
    if r.facts is not None:
        out["facts"] = [{"model": f.model, "key": f.key, "field": f.field, "value": f.value} for f in r.facts[:20]]
    return json.loads(json.dumps(out, default=str))


def _minus_days(cursor: str, days: int) -> str:
    try:
        d = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
    except ValueError:
        return cursor
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return (d - timedelta(days=days)).isoformat()


def run_graph(
    s: Session,
    wf: dict,
    graph: dict,
    *,
    trigger: str,
    dry: bool = False,
    sample: int | None = None,
    feeds: dict[str, Feed] | None = None,
    on_step: Callable[[dict], None] | None = None,
    retries: int = 0,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    run_id: Any = None,
    run_kind: str = "workflow",
    now: datetime | None = None,
    full: bool = False,
) -> RunResult:
    """Run the graph's steps over real records (see the module docstring). Commits as it goes unless `dry`."""
    return _Run(
        s, wf, graph, trigger=trigger, dry=dry, sample=sample, feeds=feeds, on_step=on_step, retries=retries,
        backoff=backoff, sleep=sleep, run_id=run_id, run_kind=run_kind, now=now, full=full,
    ).run()  # fmt: skip
