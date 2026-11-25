"""The R8 diff report of a task that changes tool-fleet numbers (plan 9, P9-3.6; rerun by the later R8 tasks).

    python -m scripts.diff_tool_fleet save <file>                     decide every tool-fleet case, write {case_id: {route, net}}
    python -m scripts.diff_tool_fleet report <before> <after> <task>  write docs/agents/plans/09-diffs/<task>.md

`save` decides, through `decide_case` (the one decider, R19), every case of the tool-fleet test world: the sample world
(`tool_fleet.sample_queue()` in the prototype's live queue, keyed `sample:<id>`) and every open tool-fleet case of the database
it runs on (the cases the `fleet` seed opens once that source has synced, keyed by case id), each as its pack and flow decide
it now. The route is the id of the recommended route, `null` for none, and the net its net. An R8 task runs `save` into the
session scratchpad at S2 (before its change) and again at S5, then `report`. Never stash or check out old code to make the
"before": save it before the change.

`report` needs no database: it writes the table of the cases whose route or net changed (old and new route and net) and the
count that did not, to `docs/agents/plans/09-diffs/<task>.md` (the folder is made when it is missing; `--out <dir>` changes it).

Never does: write to the database, or open or move a case.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DIFFS = Path(__file__).resolve().parents[2] / "docs" / "agents" / "plans" / "09-diffs"
TOL = 0.005
Row = dict[str, Any]


def decide_all() -> dict[str, Row]:
    """{case id: {route, net}} for the sample world and every open tool-fleet case of the database."""
    from sqlalchemy import text

    from di.core.db import SessionLocal
    from di.repositories.live_rules import flow_version, live_pack
    from di.services.cases import store
    from di.services.cases.decide import decide_case
    from di.services.modeler.compile import FlowVersion
    from di.services.modeler.pack import load_pack
    from di.services.modeler.valuers import tool_fleet

    out: dict[str, Row] = {}
    pack = load_pack("tool_fleet")
    world = tool_fleet.sample_live_cases()
    for c in tool_fleet.sample_queue():
        d = decide_case(c, pack, FlowVersion(None, 0, ()), queue=world)
        out[f"sample:{c['id']}"] = {"route": d.route, "net": round(d.net, 2)}
    with SessionLocal() as s:
        ids = s.execute(
            text("SELECT id FROM case_record WHERE stage <> 'closed' AND data ->> 'template' = 'tool_fleet' ORDER BY id")
        ).scalars()
        for cid in list(ids):
            c = store.get(s, cid)
            if c is None:
                continue
            d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
            out[cid] = {"route": d.route, "net": round(d.net, 2)}
    return out


def changed(before: dict[str, Row], after: dict[str, Row]) -> tuple[list[tuple[str, Row | None, Row | None]], int]:
    """The cases whose route or net differ (a case in only one file counts as changed) and how many are the same."""
    rows, same = [], 0
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k), after.get(k)
        if b is not None and a is not None and b["route"] == a["route"] and abs(b["net"] - a["net"]) <= TOL:
            same += 1
        else:
            rows.append((k, b, a))
    return rows, same


def _cell(r: Row | None) -> str:
    return "not decided" if r is None else f"{r['route'] or 'no route'}, {r['net']:,.2f}"


def report_text(before: dict[str, Row], after: dict[str, Row], task: str) -> str:
    rows, same = changed(before, after)
    lines = [f"# {task}: tool-fleet numbers before and after", "", f"Cases decided: {len(set(before) | set(after))}. "
             f"Changed: {len(rows)}. Unchanged: {same}.", ""]  # fmt: skip
    if rows:
        lines += ["| Case | Before (route, net) | After (route, net) |", "|---|---|---|"]
        lines += [f"| {k} | {_cell(b)} | {_cell(a)} |" for k, b, a in rows]
    else:
        lines.append("No case changed.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="diff_tool_fleet")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("save").add_argument("file")
    r = sub.add_parser("report")
    r.add_argument("before")
    r.add_argument("after")
    r.add_argument("task")
    r.add_argument("--out", default=str(DIFFS))
    args = p.parse_args(argv)
    if args.cmd == "save":
        Path(args.file).write_text(json.dumps(decide_all(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    before, after = (json.loads(Path(f).read_text(encoding="utf-8")) for f in (args.before, args.after))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.task}.md").write_text(report_text(before, after, args.task), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
