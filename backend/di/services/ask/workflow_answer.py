"""Ask's rule-based answer about a workflow or a run (plan 9, P9-2.23), for when no model answers or its answer is refused.

    answer(run, text, ui) -> {text, cards, result, next} | None     None when the question names no workflow or run

Owns: reading WF-nnn and RUN-xxxxx ids from the question (or the Workflow Studio page's open workflow), the reads
(`workflow.get`, `workflow.runGet`, through the same pipeline as the model's tools), and the plain-language answer built
from what they return: the failed step, the upstream error, the retries, the held records and the page's suggested fix.
It agrees with the page's Investigation panel because it reads the same run. A missing or hidden id is "There is no
workflow WF-999 you can see." (never a case, never "no access"). It points to Diagnose, Fix, Run now and Reprocess; it
never runs them.
Never does: write, or answer a question that names no workflow or run (the demo's intents answer those).
"""

import re
from typing import Any

WF_RX = re.compile(r"\bWF-\d+\b", re.I)
RUN_RX = re.compile(r"\bRUN-[A-Z0-9]{5}\b", re.I)
ABOUT_RUN = re.compile(r"\b(fail|failed|failing|why|error|fix|diagnose|run|stuck|held)\w*", re.I)
BUTTONS = (
    "On the page, Diagnose explains it, Fix applies the suggested settings, Run now tries again "
    "and Reprocess failed records sends the held ones back through."
)


def ids_of(text: str, ui: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(workflow ids, run ids) the question names; the page's open workflow when it names none and asks about a run."""
    wfs = list(dict.fromkeys(x.upper() for x in WF_RX.findall(text)))
    runs = list(dict.fromkeys(x.upper() for x in RUN_RX.findall(text)))
    obj = ui.get("object") or {}
    if not wfs and not runs and obj.get("kind") == "workflow" and obj.get("id") and ABOUT_RUN.search(text):
        wfs = [str(obj["id"]).upper()]
    return wfs, runs


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _retries(n: int) -> str:
    return "with no retries" if n == 0 else f"after {n} retr" + ("y" if n == 1 else "ies")


def _failed(d: dict[str, Any]) -> str:
    run, wf, bad = d["run"], d["workflow"], d["failed_step"]
    out = [f"Run {run['id']} of {wf['name']} ({wf['id']}) failed at {bad['label']} {_retries(d['retries'])}."]
    if d.get("error"):
        out.append(f"The upstream error: {d['error']}.")
    if run.get("records_read") is not None:
        out.append(f"The run read {run['records_read']:,} records.")
    after = [s["label"] for s in d["steps"] if s["state"] == "upstream_failed"]
    if after:
        out.append(f"{_plural(len(after), 'step')} after it did not run (upstream failed).")
    held = d["held"]["records"]
    if held:
        rules = "; ".join(f"{g['records']} on {g['field']} ({g['rule']}) at {g['step']}" for g in d["held"]["by_rule"][:3])
        out.append(f"It holds {held} records: {rules}.")
    out.append(
        f"Suggested fix: {d['suggested_fix']}"
        if d.get("suggested_fix")
        else "The page has no earlier settings to restore; check the connection to the source and try again."
    )
    return " ".join(out) + " " + BUTTONS


def _summary(d: dict[str, Any]) -> str:
    run, wf = d["run"], d["workflow"]
    bits = [f"Run {run['id']} of {wf['name']} ({wf['id']}) {run.get('state') or 'ended'}."]
    if run.get("records_read") is not None:
        bits.append(
            f"It read {run['records_read']:,} records"
            + (f" in {run['seconds']} seconds." if run.get("seconds") is not None else ".")
        )
    if d.get("error"):
        bits.append(f"Note: {d['error']}.")
    return " ".join(bits)


def _describe(d: dict[str, Any]) -> str:
    return _failed(d) if d.get("failed_step") else _summary(d)


def _refused(res: dict[str, Any]) -> dict[str, Any]:
    e = res["error"]
    return {
        "text": e["message"],
        "cards": [{"type": "cantdo", "data": {"what": e["message"], "code": e["code"], "suggest": []}}],
        "result": "refused",
    }


def answer(run: Any, text: str, ui: dict[str, Any]) -> dict[str, Any] | None:
    """`run` is fallback.Run (it makes each read through the pipeline as the signed-in person and keeps the calls)."""
    wfs, runs = ids_of(text, ui)
    if runs:
        res = run.call("workflow.runGet", {"id": runs[0]})
        return {"text": _describe(res["output"]), "cards": [], "result": "ok"} if res["ok"] else _refused(res)
    if not wfs:
        return None
    res = run.call("workflow.get", {"id": wfs[0]})
    if not res["ok"]:
        return _refused(res)
    last = res["output"].get("last_run") or {}
    if last.get("state") == "failed" and last.get("id"):
        got = run.call("workflow.runGet", {"id": last["id"]})
        if got["ok"]:
            return {"text": _describe(got["output"]), "cards": [], "result": "ok"}
    w = res["output"]["workflow"]
    tail = f" Its last run {last['id']} {last['state']}." if last.get("id") else " It has not run yet."
    return {"text": f"{w['name']} ({w['id']}) is {w['status']}, version {w['version']}.{tail}", "cards": [], "result": "ok"}
