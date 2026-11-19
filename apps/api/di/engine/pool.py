"""The pool optimiser (the demo's solvePool): allocate scarce assets across competing demand, each unit once.

It compares two answers:
- greedy: each asset in arrival order takes its best remaining destinations, as deciding one case at a time would
- optimal: an exact search over every allocation of units to destinations (pools are small)

A pool is {supplies: [{id, units, order}], dests: [{id, cap}], val: {supply id: {dest id: value per unit or None}}};
None means that supply cannot serve that destination.
"""


def solve_pool(pool: dict) -> dict:
    supplies = sorted(pool["supplies"], key=lambda s: s["order"])
    dests = pool["dests"]

    def val(s, d):
        return pool["val"][s["id"]].get(d["id"])

    # per-asset greedy
    cap_g = {d["id"]: d["cap"] for d in dests}
    g_alloc: dict[str, dict[str, int]] = {}
    g_tot = 0
    for s in supplies:
        left = s["units"]
        g_alloc[s["id"]] = {}
        for d in sorted((d for d in dests if val(s, d) is not None), key=lambda d: -val(s, d)):
            q = min(left, cap_g[d["id"]])
            if q > 0:
                g_alloc[s["id"]][d["id"]] = q
                cap_g[d["id"]] -= q
                left -= q
                g_tot += q * val(s, d)

    # exact search: every split of each supply's units across destinations, keeping only splits that place as many
    # units as the remaining capacity allows; the first best total found wins
    best = {"t": float("-inf"), "a": None}

    def splits(s, di, left, cap, cur):
        if di == len(dests):
            yield list(cur)
            return
        d = dests[di]
        if val(s, d) is None:
            yield from splits(s, di + 1, left, cap, [*cur, 0])
            return
        for q in range(min(left, cap[d["id"]]), -1, -1):
            yield from splits(s, di + 1, left - q, cap, [*cur, q])

    def rec(si, cap, acc, tot):
        if si == len(supplies):
            if tot > best["t"]:
                best["t"], best["a"] = tot, {k: dict(v) for k, v in acc.items()}
            return
        s = supplies[si]
        placeable = min(s["units"], sum(0 if val(s, d) is None else min(s["units"], cap[d["id"]]) for d in dests))
        for qs in splits(s, 0, s["units"], cap, []):
            if sum(qs) < placeable:
                continue
            nc, t, al = dict(cap), 0, {}
            for i, q in enumerate(qs):
                if q:
                    nc[dests[i]["id"]] -= q
                    t += q * val(s, dests[i])
                    al[dests[i]["id"]] = q
            acc[s["id"]] = al
            rec(si + 1, nc, acc, tot + t)
            del acc[s["id"]]

    rec(0, {d["id"]: d["cap"] for d in dests}, {}, 0)
    return {
        "greedy": {"alloc": g_alloc, "total": g_tot},
        "optimal": {"alloc": best["a"], "total": best["t"]},
        "uplift": best["t"] - g_tot,
        "supplies": supplies,
        "dests": dests,
    }
