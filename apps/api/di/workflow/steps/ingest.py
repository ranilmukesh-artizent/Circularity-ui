# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Ingestion steps: API gateway, event ingestion, file ingestion (plan 6, task C4).

They pass records through and record how they came in. The reading itself is the source's connector (the `conn`
node); these steps add what their block promises on top: the gateway's limits, the events' order and replay safety,
the file's checksum.
"""

from datetime import timedelta

from di.workflow.steps.core import Rec, Reject, StepCtx, StepResult, clone, digest, get, opt, parse_ts

# the settings each step reads (keys of di/workflow/blocks.py)
KEYS = {
    "x_gw": {"rate_limit": "rate_limit_per_min", "timeout": "timeout_s"},
    "x_evt": {"ordering_key": "ordering_key", "replay_window": "replay_window_min"},
    "x_file": {"path": "path", "checksum_required": "checksum_required"},
}


def x_gw(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Pass-through; each record carries the limits it came in under (meta.gw). 0: no limit."""
    k = KEYS["x_gw"]
    limit, timeout = opt(cfg, k["rate_limit"], 0), opt(cfg, k["timeout"], 30)
    out = []
    for r in recs:
        c = clone(r)
        c.meta["gw"] = {"rate_limit": limit, "timeout_s": timeout}
        out.append(c)
    side = {"requests": len(recs)}
    if limit:
        side["minutes_at_limit"] = -(-len(recs) // int(limit))  # how long the batch takes at the rate limit
    return StepResult(out, [], side)


def x_evt(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Events in order of the ordering key (stable; events without it keep their place after the others), exact
    replays (same id, same payload) dropped. With a replay window, an event that carries its arrival time
    (meta.received_at) more than the window after its own time is rejected (rule `replay_window`)."""
    k = KEYS["x_evt"]
    key, window = opt(cfg, k["ordering_key"], ""), opt(cfg, k["replay_window"], 0)
    seen: set[tuple[str, str]] = set()
    out, rejected, dups = [], [], 0
    for r in recs:
        sig = (r.ext_id, digest(r.data))
        if sig in seen:
            dups += 1
            continue
        seen.add(sig)
        if window and key:
            t, got = parse_ts(get(r, key)), parse_ts(r.meta.get("received_at"))
            if t and got and got - t > timedelta(minutes=window):
                rejected.append(
                    Reject(r, key, "replay_window", get(r, key), f"event arrived more than {window} min after its time")
                )
                continue
        out.append(clone(r))
    if key:
        have = [r for r in out if get(r, key) is not None]
        lack = [r for r in out if get(r, key) is None]
        have.sort(key=lambda r: _sortable(get(r, key)))
        out = have + lack
    return StepResult(out, rejected, {"duplicates": dups})


def _sortable(v):
    t = parse_ts(v) if isinstance(v, str) else None
    if t is not None:
        return (1, t.timestamp(), "")
    if isinstance(v, int | float) and not isinstance(v, bool):
        return (1, float(v), "")
    return (2, 0.0, str(v))


def x_file(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Pass-through with the record's checksum (sha256 of its payload) in meta.file. When checksums are required, a
    checksum the record carries (meta.checksum) must match, and a record that came from a file (meta.file) must carry
    one; otherwise it is rejected (rule `checksum`). Records read from an API carry no file and pass."""
    k = KEYS["x_file"]
    path, required = opt(cfg, k["path"], ""), bool(opt(cfg, k["checksum_required"], True))
    out, rejected = [], []
    for r in recs:
        mine, theirs = digest(r.data), r.meta.get("checksum")
        if required and theirs is not None and theirs != mine:
            rejected.append(Reject(r, None, "checksum", theirs, "checksum does not match the payload"))
            continue
        if required and theirs is None and r.meta.get("file") is not None:
            rejected.append(Reject(r, None, "checksum", None, "the file carried no checksum"))
            continue
        c = clone(r)
        c.meta["file"] = {**(c.meta.get("file") or {}), "path": path, "checksum": mine}
        out.append(c)
    return StepResult(out, rejected, {})


STEPS = {"x_gw": x_gw, "x_evt": x_evt, "x_file": x_file}
