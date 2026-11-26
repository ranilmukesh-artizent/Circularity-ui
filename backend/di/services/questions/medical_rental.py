"""Worked analytics questions of the medical_rental pack (plan 9, P9-11.16; the shape of P9-6.17, DV-13).

Each question is a pure function of typed rows returning `di.services.device.analytics.Answer`, wrapped in a
`WorkedQuestion` whose compute loads only the rows its `Scope` allows (R21) and registered with `analytics.register`.
Imported by `di.services.questions`, so the action `device.question` and Ask's `device_question` tool answer it by id.

    turnaround_by_cause(depots, devices)  WQ-MR-1 "Why did turnaround slip at the East depot?": the slowest depot's waiting days
                                          by cause, its decontamination lines against the other depots', the rise in returns,
                                          and its three longest-waiting devices (rows from `mr_turnaround`, the canonical store)
    retired_earliest(rows)                WQ-MR-2 "Which device models are retired earliest?": average age at retirement per
                                          class, youngest first, with the youngest retired devices (the pack's replay rows)

Every number is counted here (R16); the sentence is worded by `analytics.word` (model first, numbers checked, template
fallback). The replay rows are the pack's shared sample history (no org unit owns them), so the scope does not filter them.
Read only; synthetic data.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy.orm import Session

from di.services.cases import mr_turnaround as mt
from di.services.device import analytics
from di.services.device.analytics import Answer, Scope, WorkedQuestion
from di.services.modeler.replay_samples import medical_rental as replay

CAUSE_LABEL = {"decon_queue": "the decontamination queue", "service": "the service queue", "transport": "transport"}
MAX_EXAMPLES = 3


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def turnaround_by_cause(depots: Sequence[mt.DepotFact], devices: Sequence[mt.DeviceWait]) -> Answer:
    qid = mt.QUESTION_ID
    if not depots:
        return Answer(qid, "No turnaround records yet.", {"kind": "bar", "series": []}, [])
    focus = max(depots, key=lambda d: (d.avg_days, d.depot))
    name = mt.depot_label(focus.depot)
    causes = sorted(focus.by_cause.items(), key=lambda kv: (-kv[1], kv[0]))
    chart = {"kind": "bar", "series": [{"name": f"{name} waiting days", "points": [{"x": c, "y": v} for c, v in causes]}]}
    others = [d.lines for d in depots if d.depot != focus.depot and d.lines is not None]
    head = f"{name} has {_plural(focus.lines, 'decontamination line')}" if focus.lines is not None else f"{name} is slowest"
    if focus.lines is not None and others:
        head += f" against {round(sum(others) / len(others))} elsewhere"
    if focus.prior_returns and focus.returns > focus.prior_returns:
        head += f", after returns rose {round((focus.returns - focus.prior_returns) / focus.prior_returns * 100)}%"
    sentence = f"{head}: most waiting is in {CAUSE_LABEL.get(causes[0][0], causes[0][0])}." if causes else head + "."
    mine = sorted(
        (d for d in devices if d.depot == focus.depot), key=lambda d: (-d.waiting.get("decon_queue", 0), -d.own_days, d.tag)
    )
    examples = [
        {"tag": d.tag, "depot": d.depot, "checked_in_on": d.checked_in_on.isoformat(), "own_days": d.own_days,
         "waiting_days": dict(d.waiting)}
        for d in mine[:MAX_EXAMPLES]
    ]  # fmt: skip
    return Answer(qid, sentence, chart, examples)


def _turnaround_compute(s: Session, scope: Scope | None, _as_of: date) -> Answer:
    orgs = None if scope is None or scope.orgs is None else sorted(scope.orgs)
    return turnaround_by_cause(*mt.read(s, orgs))


def retired_earliest(rows: Sequence[Mapping[str, str]]) -> Answer:
    qid = "retired_earliest"
    by: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        if r.get("actual_route") == "retire":
            by[r["class"]].append((int(r["fact.age_years"]), r["item_id"]))
    order = sorted(((c, sum(a for a, _ in v) / len(v), len(v)) for c, v in by.items()), key=lambda x: (x[1], x[0]))
    points = [{"x": c, "y": round(a, 1)} for c, a, _ in order]
    chart = {"kind": "bar", "series": [{"name": "Average age at retirement (years)", "points": points}]}
    if not order:
        return Answer(qid, "No device has been retired in this history.", chart, [])
    cls, avg, n = order[0]
    sentence = f"{cls.replace('_', ' ').capitalize()} devices are retired earliest, at {round(avg, 1)} years on average across {n} retirements."
    young = sorted((age, item) for age, item in by[cls])[:MAX_EXAMPLES]
    return Answer(qid, sentence, chart, [{"item_id": i, "class": cls, "age_years": a} for a, i in young])


def _retired_compute(_s: Session, _scope: Scope | None, _as_of: date) -> Answer:
    return retired_earliest(replay.rows())


analytics.register(
    WorkedQuestion(mt.QUESTION_ID, "Why did turnaround slip at the East depot?", "bar", _turnaround_compute, "medical_rental")
)
analytics.register(
    WorkedQuestion("retired_earliest", "Which device models are retired earliest?", "bar", _retired_compute, "medical_rental")
)
