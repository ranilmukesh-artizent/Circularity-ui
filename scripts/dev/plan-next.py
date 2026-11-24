"""Pick the plan-9 tasks that can start now, for a lead running writers in parallel.

    python scripts/dev/plan-next.py                 # ready tasks, in plan order, file-disjoint, at most 6
    python scripts/dev/plan-next.py --max 4
    python scripts/dev/plan-next.py --upto 3        # only tasks of phases 0-3 (a run that stops after phase 3)
    python scripts/dev/plan-next.py --status        # done / in flight / blocked / left, per phase
    python scripts/dev/plan-next.py --simulate 4    # estimated wall-clock hours with 4 writers (--fast: quicker tasks)

A task is ready when:
  1. its box is not ticked and it is not in flight or blocked (docs/agents/plans/09-run/inflight.txt, blocked.txt:
     one task id per line, then optional text);
  2. every task in its "Depends on" is ticked;
  3. every task of its phase's prerequisite phases (PHASE_AFTER) is ticked;
  4. no earlier unticked task in plan order touches any of its logic files (so each logic file is changed in plan
     order), and no in-flight task touches them; append-like files (tests, smokes, facade, pack JSON, docs) and the
     registration files (APPEND_FILES) do not order tasks;
  5. it is not a barrier task (it adds a dependency or is a phase gate), unless nothing is in flight.
Host Python, no packages; reads files as UTF-8.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/agents/plans/09-agentic-platform.md"
RUN = ROOT / "docs/agents/plans/09-run"

# Phases that must be fully done before a phase starts. Tool fleet (3-5) and device (6) share core files, so rule 4
# orders those files; the three asset packs (9, 10, 11) run side by side after Compose (8).
PHASE_AFTER = {1: {0}, 2: {1}, 3: {2}, 4: {3}, 5: {4}, 6: {2}, 7: {2}, 8: {7},
               9: {8}, 10: {8}, 11: {8}, 12: {8}, 13: set(range(13))}
# Dependencies are added once, up front, by the lead (all plan-9 libraries in one rebuild), so tasks that list these
# files only check that their library is there; they do not serialize on them.
DEPENDENCY_FILES = ("pyproject.toml", "package.json", "package-lock.json", "requirements")
BARRIER_FILES = ("Dockerfile", "docker-compose")
# Registration files that tasks only append to (a field, a mock, a permission, a forbidden action, a log row). They do
# not order tasks; the lead merges both sides when two writers append at once.
APPEND_FILES = {
    "backend/di/services/canonical/fields.py", "docs/agents/decision-log.md", "source-sim/sim/core/registry.py",
    "backend/di/services/agents/forbidden.py", "backend/di/core/policy.py", "docs/agents/plans/09-licences.md",
    "backend/di/worker.py", "docs/agents/scripts.md", "backend/di/models/__init__.py", "backend/di/main.py",
    "docs/agents/plans/PROGRESS.md", "docs/backend-steps.md",
}
ID = r"P9-\d+\.\d+"


# Files that writers only append to in their own region (a test, a smoke step, a facade function, a pack entry, a
# doc row). They do not order tasks; the lead merges both sides. Logic files (services, pages, models) do.
APPEND_LIKE = re.compile(r"smoke-.*\.mjs$|\.test\.tsx?$|^backend/tests/|^tests/|frontend/src/api/.*\.ts$|packs/.*\.json$|\.md$")


def core(files: set[str]) -> set[str]:
    return {f for f in files if not APPEND_LIKE.search(f)}


def key(tid: str) -> tuple[int, int]:
    a, b = tid[3:].split(".")
    return int(a), int(b)


def parse() -> dict[str, dict]:
    text = PLAN.read_text(encoding="utf-8")
    tasks: dict[str, dict] = {}
    for m in re.finditer(rf"^- \[([ x])\] ({ID}) (.*)$", text, re.M):
        tasks[m.group(2)] = {"done": m.group(1) == "x", "title": m.group(3), "deps": set(), "files": set(),
                             "size": "M", "gate": "gate" in m.group(3).lower()}
    specs = re.split(rf"(?m)^(?=#### {ID} )", text[text.index("## Task specs"):text.index("## Story coverage matrix")])
    for blk in specs:
        m = re.match(rf"#### ({ID}) ", blk)
        if not m or m.group(1) not in tasks:
            continue
        t = tasks[m.group(1)]
        d = re.search(r"\*\*Depends on:\*\*([^\n]*)", blk)
        if d:
            t["deps"] = set(re.findall(ID, d.group(1))) - {m.group(1)}
        s = re.search(r"\*\*Size:\*\*\s*([SML])", blk)
        if s:
            t["size"] = s.group(1)
        f = re.search(r"\*\*Files:\*\*(.*?)(?=\n\*\*[A-Z]|\Z)", blk, re.S)
        if f:
            for p in re.findall(r"`([^`\s]+)`", f.group(1)):
                p = p.rstrip(",.;:")
                if "/" in p and "<" not in p and "*" not in p and p not in APPEND_FILES                         and not any(d in p for d in DEPENDENCY_FILES):
                    t["files"].add(p)
        t["barrier"] = t["gate"] or any(b in p for p in t["files"] for b in BARRIER_FILES)
    return tasks


def listed(name: str) -> set[str]:
    p = RUN / name
    if not p.exists():
        return set()
    return {ln.split()[0] for ln in p.read_text(encoding="utf-8").splitlines() if re.match(ID, ln.strip())}


def ready(tasks: dict, done: set, inflight: set, blocked: set, limit: int) -> list[str]:
    order = sorted(tasks, key=key)
    busy = set().union(*(core(tasks[t]["files"]) for t in inflight)) if inflight else set()
    picked: list[str] = []
    for i, tid in enumerate(order):
        t = tasks[tid]
        if tid in done or tid in inflight or tid in blocked:
            continue
        ph = key(tid)[0]
        if not t["deps"] <= done:
            continue
        if any(key(o)[0] in PHASE_AFTER.get(ph, set()) and o not in done for o in order):
            continue
        earlier = [o for o in order[:i] if o not in done]
        if any(tasks[o]["files"] & core(t["files"]) for o in earlier):
            continue
        if any(key(o)[0] == ph and o not in done and tasks[o]["gate"] for o in earlier):
            continue
        if t["gate"] and any(key(o)[0] == ph and o not in done for o in earlier):
            continue
        if core(t["files"]) & busy:
            continue
        if t["barrier"] and (inflight or picked):
            continue
        picked.append(tid)
        busy |= core(t["files"])
        if t["barrier"] or len(picked) + len(inflight) >= limit:
            break
    return picked


def simulate(tasks: dict, writers: int) -> None:
    mins = {"S": 15, "M": 30, "L": 50} if "--fast" in sys.argv else {"S": 25, "M": 50, "L": 80}
    merge, gate_full, gate_fast = 6, 75, 25
    full_gate_phases = {2, 8, 13}
    clock, done, running, lead_free = 0.0, set(), {}, 0.0
    while len(done) < len(tasks):
        for tid in ready(tasks, done, set(running), set(), writers):
            t = tasks[tid]
            if t["gate"]:
                dur = gate_full if key(tid)[0] in full_gate_phases else gate_fast
            else:
                dur = mins[t["size"]]
            running[tid] = clock + dur
        if not running:
            print("stuck: no task can start; check deps", sorted(set(tasks) - done)[:5])
            return
        tid = min(running, key=running.get)
        clock = max(running.pop(tid), lead_free) + merge   # the lead merges and re-tests one at a time
        lead_free = clock
        done.add(tid)
    print(f"writers {writers}: {len(tasks)} tasks, about {clock / 60:.1f} h (S {mins['S']} min, M {mins['M']}, "
          f"L {mins['L']}; lead merge {merge}; full gate {gate_full} at phases {sorted(full_gate_phases)}, "
          f"fast gate {gate_fast} elsewhere)")


def main() -> None:
    args = sys.argv[1:]
    tasks = parse()
    if "--simulate" in args:
        n = int(args[args.index("--simulate") + 1])
        simulate(tasks, n)
        return
    done = {t for t, v in tasks.items() if v["done"]}
    inflight, blocked = listed("inflight.txt"), listed("blocked.txt")
    if "--status" in args:
        for ph in sorted({key(t)[0] for t in tasks}):
            ids = [t for t in tasks if key(t)[0] == ph]
            print(f"phase {ph:2}: {sum(t in done for t in ids):3} done, {sum(t in inflight for t in ids)} in flight, "
                  f"{sum(t in blocked for t in ids)} blocked, {len(ids)} total")
        return
    limit = int(args[args.index("--max") + 1]) if "--max" in args else 6
    if "--upto" in args:
        last = int(args[args.index("--upto") + 1])
        tasks = {k: v for k, v in tasks.items() if key(k)[0] <= last}
        if all(v["done"] for v in tasks.values()):
            print(f"phases 0-{last} are done")
            return
    for tid in ready(tasks, done, inflight, blocked, limit):
        t = tasks[tid]
        flag = " [barrier: run alone, in the main tree]" if t["barrier"] else ""
        print(f"{tid} ({t['size']}) {t['title']}{flag}")
        for f in sorted(t["files"]):
            print(f"    {f}")


if __name__ == "__main__":
    main()
