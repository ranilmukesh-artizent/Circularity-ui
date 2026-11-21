# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Quality steps: validation, late and duplicate events, identity resolution (plan 6, task C4)."""

from datetime import timedelta

from di.workflow.steps.core import Rec, Reject, StepCtx, StepResult, as_list, clone, get, opt, parse_ts, present, rule_ok

# the settings each step reads (keys of di/workflow/blocks.py; "tenant_field" is not in the catalogue)
KEYS = {
    "x_val": {"required": "required", "rules": "rules", "on_failure": "on_failure"},
    "x_late": {"keys": "keys", "newest_by": "newest_by", "late_window": "late_window_min"},
    "x_ident": {"keys": "keys", "tenant_field": "tenant_field"},
}
# where a record's change time is when "newest wins by" is empty
CHANGE_TIME = ("updated_at", "modified_at", "last_modified", "LastModifiedDate", "SystemModstamp", "changed_at", "updated")


def x_val(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Required fields, then the rules in order; a record is rejected at its first failure, with the rule's name
    (present, type, regex, range, in) and a reason. `on_failure` (hold | reject) goes to side.on_failure: the error
    handler holds the rejects for reprocessing or counts and drops them."""
    k = KEYS["x_val"]
    required = as_list(opt(cfg, k["required"], []))
    rules = [{"field": f, "check": "present"} for f in required] + list(opt(cfg, k["rules"], []))
    out, rejected = [], []
    for r in recs:
        for rule in rules:
            ok, name, fname, value, reason = rule_ok(r, rule)
            if not ok:
                rejected.append(Reject(r, fname, name, value, reason))
                break
        else:
            out.append(clone(r))
    return StepResult(out, rejected, {"on_failure": opt(cfg, k["on_failure"], "hold")})


def _change_time(r: Rec, by: str):
    if by:
        return parse_ts(get(r, by))
    if r.meta.get("cursor"):
        return parse_ts(r.meta["cursor"])
    for f in CHANGE_TIME:
        if (t := parse_ts(get(r, f))) is not None:
            return t
    return None


def x_late(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Newest per key wins (key fields; empty: the record id), by the `newest_by` field (empty: the change time the
    record carries); a tie goes to the later arrival. The others are dropped (side.dropped), not rejected. A record
    that carries its arrival time (meta.received_at) more than the late window after its own time is rejected
    (rule `late_window`); records read by a sync carry none."""
    k = KEYS["x_late"]
    keys, by, window = as_list(opt(cfg, k["keys"], [])), opt(cfg, k["newest_by"], ""), opt(cfg, k["late_window"], 0)
    rejected: list[Reject] = []
    best: dict[tuple, tuple[int, Rec]] = {}
    for i, r in enumerate(recs):
        t = _change_time(r, by)
        got = parse_ts(r.meta.get("received_at"))
        if window and t and got and got - t > timedelta(minutes=window):
            rejected.append(
                Reject(r, by or None, "late_window", get(r, by) if by else None, f"arrived more than {window} min late")
            )
            continue
        key = (r.resource, *(str(get(r, f)) for f in keys)) if keys else (r.resource, r.ext_id)
        cur = best.get(key)
        if cur is None:
            best[key] = (i, r)
            continue
        ct = _change_time(cur[1], by)
        if t is None or ct is None or t >= ct:
            best[key] = (i, r)
    kept = sorted(best.values(), key=lambda p: p[0])
    out = [clone(r) for _, r in kept]
    return StepResult(out, rejected, {"dropped": len(recs) - len(out) - len(rejected)})


def x_ident(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Records that share any identity key value are one identity, inside one tenant only (the tenant field; records
    without one match nothing). Each record gets data.identity ("<tenant>/<smallest matching key value>", so two
    tenants never share one) and meta.identity."""
    k = KEYS["x_ident"]
    keys, tf = as_list(opt(cfg, k["keys"], [])), opt(cfg, k["tenant_field"], "tenant")
    parent = list(range(len(recs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[tuple, int] = {}
    for i, r in enumerate(recs):
        tenant = get(r, tf)
        if not present(tenant):
            continue
        for f in keys:
            v = get(r, f)
            if not present(v):
                continue
            j = owner.setdefault((str(tenant), f, str(v)), i)
            parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(recs)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        tenant = get(recs[members[0]], tf)
        vals = sorted({str(get(recs[i], f)) for i in members for f in keys if present(get(recs[i], f))})
        ident = f"{tenant}/{vals[0]}" if vals and present(tenant) else recs[members[0]].ext_id
        for i in members:
            c = clone(recs[i])
            c.data["identity"] = ident
            c.meta["identity"] = {"id": ident, "members": len(members)}
            out.append((i, c))
    out.sort(key=lambda p: p[0])
    return StepResult([c for _, c in out], [], {"identities": len(groups)})


STEPS = {"x_val": x_val, "x_late": x_late, "x_ident": x_ident}
