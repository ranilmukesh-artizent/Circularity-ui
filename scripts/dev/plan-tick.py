"""Plan 9 lead helper: after a writer's commit is cherry-picked and verified, tick its box, add its progress row,
clear it from inflight.txt, log it, and write the commit message (the writer's message, a "Verified by the lead" line,
the lead's trailer).

    python scripts/dev/plan-tick.py <task id> <writer sha> "<what the lead ran, with counts>" "<run-log note>"
    git add <the task's files> docs/agents/plans; git commit -F "$PLAN_MSG"   (default: <run folder>/.commit-msg.txt)

PLAN_RUN: the run folder (default docs/agents/plans/09-run; lane B: docs/agents/plans/09-run/lane-B). Its progress
rows go to <run folder>/PROGRESS.md when that file exists (a lane), else to docs/agents/plans/PROGRESS.md.
Fails closed: the message file is deleted first and written last, so a failed run never leaves a stale message; a
writer commit whose subject is over 72 characters or has no blank line after it is refused (rewrite the message).
Host Python, no packages.
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(os.environ["PLAN_RUN"]) if os.environ.get("PLAN_RUN") else ROOT / "docs/agents/plans/09-run"
RUN = RUN if RUN.is_absolute() else ROOT / RUN
MSG = Path(os.environ.get("PLAN_MSG") or RUN / ".commit-msg.txt")
tid, sha, gate, note = sys.argv[1:5]
MSG.unlink(missing_ok=True)


def write(path: Path, text: str) -> None:
    for _ in range(10):
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
            return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"could not write {path}")


plan = ROOT / "docs/agents/plans/09-agentic-platform.md"
s = plan.read_text(encoding="utf-8")
m = re.search(rf"^- \[ \] {re.escape(tid)} (.*)$", s, re.M)
if not m:
    raise SystemExit(f"{tid} not found unticked")
title = m.group(1)
write(plan, s.replace(m.group(0), f"- [x] {tid} {title}", 1))

row = f"| {datetime.now():%Y-%m-%d} | 09 · {tid} {title[0].lower() + title[1:]} | this commit | {gate} | done |\n"
lane_prog = RUN / "PROGRESS.md"
if lane_prog.exists():  # a lane keeps its own rows; the integrator folds them into PROGRESS.md
    write(lane_prog, lane_prog.read_text(encoding="utf-8").rstrip("\n") + "\n" + row)
else:
    prog = ROOT / "docs/agents/plans/PROGRESS.md"
    t = prog.read_text(encoding="utf-8")
    h = "\n## Decisions taken without the user (to review)"
    i = t.index(h)
    write(prog, t[:i].rstrip("\n") + "\n" + row + t[i:])

inf = RUN / "inflight.txt"
write(inf, "".join(ln for ln in inf.read_text(encoding="utf-8").splitlines(True) if not ln.startswith(tid + " ")))

log = RUN / "RUN-LOG.md"
write(log, log.read_text(encoding="utf-8") + f"| {datetime.now():%d %b %H:%M} | {tid} merged. {note} |\n")

msg = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%B", sha], capture_output=True, text=True,
                     encoding="utf-8", check=True).stdout.rstrip()
lines = msg.splitlines()
trailers = [ln for ln in lines if ln.startswith("Co-Authored-By:")]
body = [ln for ln in lines if not ln.startswith("Co-Authored-By:")]
while body and not body[-1].strip():
    body.pop()
if not body or not body[0].startswith(tid + ":"):
    raise SystemExit(f"writer commit {sha} does not start with {tid}:")
if len(body[0]) > 72 or (len(body) > 1 and body[1].strip()):
    raise SystemExit(f"writer commit {sha}: subject over 72 characters or no blank line after it; write the message")
out = "\n".join(body) + f"\n\nVerified by the lead: {gate}.\n\n" + "\n".join(
    trailers + ["Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"]) + "\n"
write(MSG, out)
print("ticked", tid, "-", title)
