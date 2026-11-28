"""The batched model rerank of `mapping.suggest` (mapping_rerank v2): many fields in one request, within a wall-clock budget.

Every loop here is a fake `AgentLoop` (no provider, R16): it reads the prompt's JSON and answers as the test says. Covered:
a batch of three answered; an answer outside the candidates dropped; the budget used after the first chunk leaves the later
fields deterministic, the least sure asked first; no model -> nothing asked and `stopped == "no_model"`; a late request is not
waited for; the action's `model` summary.
"""

import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors.mapping_suggest import canonical_fields, model_fields, profile, suggest
from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents import mapping_rerank, runtime
from di.services.agents.loop import LoopResult
from di.services.agents.mapping_rerank import CHUNK, Ask, BatchAnswer, FieldAnswer, make_reranker
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
CANON = canonical_fields()
SID = "insp"
RES = "audits_batch"
SAMPLE = [{"SERNR": f"MTR-{2041 + n}", "CUKY": "USD", "grade_text": "B"} for n in range(4)]


class FakeLoop:
    """An AgentLoop whose model is `answer(fields) -> [FieldAnswer] | None` (None: no model); it keeps the fields it was sent."""

    def __init__(self, answer: Callable[[list[dict[str, Any]]], list[FieldAnswer] | None]) -> None:
        self.answer, self.sent = answer, []

    def run(self, s: Any, spec: Any, prompt: str, *, ctx: Any, resume: Any = None) -> LoopResult:
        assert spec.version == "2" and spec.output_type is BatchAnswer and ctx.run_id
        fields = json.loads(prompt.split("\n", 1)[1])
        got = self.answer(fields)
        if got is None:
            return LoopResult(output=None, model=None)
        self.sent.append([f["field"] for f in fields])
        return LoopResult(output=BatchAnswer(answers=got), model="fake")


def _top(fields: list[dict[str, Any]]) -> list[FieldAnswer]:
    return [FieldAnswer(field=f["field"], target=f["candidates"][0]["target"], rule="copy", why="Fits by name.") for f in fields]


def _clean() -> None:
    with SessionLocal() as s:
        runs = "SELECT id FROM agent_run WHERE playbook = 'mapping_rerank'"
        s.execute(text(f"DELETE FROM agent_run_message WHERE run_id IN ({runs})"))  # noqa: S608 - fixed text
        s.execute(text("DELETE FROM agent_run WHERE playbook = 'mapping_rerank'"))
        s.execute(text("DELETE FROM raw_record WHERE source_id = :s AND resource = :r"), {"s": SID, "r": RES})
        s.commit()


@pytest.fixture(autouse=True)
def fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mapping_rerank, "_model_wait", lambda: None)  # never wait for a real model's minute window
    _clean()
    yield
    runtime.set_loop(None)
    _clean()


def _ctx() -> CallContext:
    with SessionLocal() as s:
        return CallContext(actor=SYSTEM, session=s)


def _asks(sample: list[dict[str, Any]] = SAMPLE) -> list[Ask]:
    profiles = [profile(sample, f) for f in sample[0]]
    return [Ask(p.name, p, shown, score) for p, shown, score in model_fields(profiles, CANON)]


def _runs() -> int:
    with SessionLocal() as s:
        return int(s.execute(text("SELECT count(*) FROM agent_run WHERE playbook = 'mapping_rerank'")).scalar_one())


def test_batch_of_three_fields_answered_in_one_request():
    loop = FakeLoop(_top)
    runtime.set_loop(loop)
    asks = _asks()
    got = make_reranker(_ctx()).precompute(asks)
    assert len(loop.sent) == 1 and sorted(loop.sent[0]) == sorted(a.key for a in asks)  # one request for the three
    assert set(got.answers) == {"SERNR", "CUKY", "grade_text"} and got.stopped is None
    assert got.summary() | {"seconds": 0} == {"asked": 3, "answered": 3, "fields": 3, "seconds": 0, "stopped": None}
    assert _runs() == 1  # one agent_run for the batch
    profiles = [a.profile for a in asks]
    props = suggest(profiles, SAMPLE, CANON, rerank=got.lookup(lambda p: p.name))
    assert all(p.proposed_by == "model" and p.reason == "Fits by name." for p in props)
    base = suggest(profiles, SAMPLE, CANON)
    # the model agreed with the top candidate: the same pick, and the confidence is the curve's plus the agreement bonus
    assert [p.candidates for p in props] == [b.candidates for b in base]
    assert all(
        p.target in (None, b.candidates[0][0]) and b.confidence <= p.confidence <= b.confidence + 0.05
        for p, b in zip(props, base, strict=True)
    )


def test_batch_answer_outside_the_candidates_is_dropped_for_that_field_only():
    def answer(fields: list[dict[str, Any]]) -> list[FieldAnswer]:
        out = _top(fields)
        for a in out:
            if a.field == "CUKY":
                a.target = "asset.not_a_field"
            if a.field == "grade_text":
                a.why = "It is 99 % certain."  # a number that is not in the profile
        return [*out, FieldAnswer(field="not_sent", target=None, why="Unknown.")]

    runtime.set_loop(FakeLoop(answer))
    asks = _asks()
    got = make_reranker(_ctx()).precompute(asks)
    assert set(got.answers) == {"SERNR"} and got.summary()["asked"] == 3 and got.summary()["answered"] == 1
    profiles = [a.profile for a in asks]
    by = {p.field: p for p in suggest(profiles, SAMPLE, CANON, rerank=got.lookup(lambda p: p.name))}
    base = {p.field: p for p in suggest(profiles, SAMPLE, CANON)}
    assert by["SERNR"].proposed_by == "model"
    assert by["CUKY"] == base["CUKY"] and by["grade_text"] == base["grade_text"]  # no repair round: the rules stand


def _many(n: int) -> list[Ask]:
    """n fields with scores falling from the first to the last (the last is the least sure)."""
    sample = [{f"serial_no_{i}": f"MTR-{k}{i}" for i in range(n)} for k in range(3)]
    asks = _asks(sample)
    return [Ask(a.key, a.profile, a.candidates, 1.0 - i / 100) for i, a in enumerate(asks)]


def test_budget_used_after_the_first_chunk_leaves_the_rest_deterministic():
    now = [0.0]

    def answer(fields: list[dict[str, Any]]) -> list[FieldAnswer]:
        now[0] += 30.0  # the request took longer than the whole budget
        return _top(fields)

    loop = FakeLoop(answer)
    runtime.set_loop(loop)
    asks = _many(CHUNK + 3)
    got = make_reranker(_ctx(), budget_s=25.0, clock=lambda: now[0]).precompute(asks)
    assert len(loop.sent) == 1 and got.stopped == "budget"
    least_sure = [a.key for a in asks[::-1][:CHUNK]]
    assert loop.sent[0] == least_sure and set(got.answers) == set(least_sure)  # the least sure fields were read first
    assert got.summary() == {"asked": CHUNK, "answered": CHUNK, "fields": CHUNK + 3, "seconds": 30.0, "stopped": "budget"}
    rerank = got.lookup(lambda p: p.name)
    assert all(rerank(a.profile, a.candidates) is None for a in asks[:3])  # not reached: the deterministic proposal


def test_every_field_is_asked_in_chunks_when_the_budget_allows():
    loop = FakeLoop(_top)
    runtime.set_loop(loop)
    got = make_reranker(_ctx()).precompute(_many(CHUNK + 3))
    assert [len(c) for c in loop.sent] == [CHUNK, 3] and got.stopped is None and len(got.answers) == CHUNK + 3
    assert _runs() == 2


def test_no_model_asks_nothing_and_all_is_deterministic():
    loop = FakeLoop(lambda _fields: None)
    runtime.set_loop(loop)
    asks = _many(CHUNK + 3)
    got = make_reranker(_ctx()).precompute(asks)
    assert got.summary() | {"seconds": 0} == {"asked": 0, "answered": 0, "fields": CHUNK + 3, "seconds": 0, "stopped": "no_model"}
    assert loop.sent == [] and _runs() == 0  # one try, then no more asking; no run is kept


def test_a_late_request_is_not_waited_for():
    def answer(fields: list[dict[str, Any]]) -> list[FieldAnswer]:
        time.sleep(4.0)
        return _top(fields)

    runtime.set_loop(FakeLoop(answer))
    t0 = time.monotonic()
    got = make_reranker(_ctx(), budget_s=2.5).precompute(_asks())
    assert time.monotonic() - t0 < 3.5 and got.stopped == "budget" and got.answers == {}
    time.sleep(2.5)  # the request ends in its own thread before the fixture tidies its run


def test_a_model_that_fails_twice_in_a_row_stops_the_asking():
    seen: list[int] = []

    def answer(_fields: list[dict[str, Any]]) -> list[FieldAnswer]:
        seen.append(1)
        raise RuntimeError("the provider is down")

    runtime.set_loop(FakeLoop(answer))
    got = make_reranker(_ctx()).precompute(_many(3 * CHUNK))
    assert len(seen) == 2 and got.stopped == "error" and got.answers == {} and _runs() == 0


def _seed() -> None:
    rows = [{"audit_id": f"audit_{n}", "grade_text": "Grade B", "media_count": 10 + n} for n in range(6)]
    with SessionLocal() as s:
        for n, r in enumerate(rows):
            s.execute(
                text("INSERT INTO raw_record (source_id, resource, ext_id, payload) VALUES (:s, :r, :e, CAST(:p AS jsonb))"),
                {"s": SID, "r": RES, "e": f"b{n}", "p": json.dumps(r)},
            )
        s.commit()


def test_mapping_suggest_action_reports_what_the_model_read():
    _seed()
    loop = FakeLoop(_top)
    runtime.set_loop(loop)
    out = call("mapping.suggest", {"source_id": SID, "resource": RES}, "developer")["output"]
    m = out["model"]
    assert (
        len(out["rows"]) == 3 and m["fields"] == 3 and m["stopped"] is None and m["asked"] == m["answered"] == len(loop.sent[0])
    )
    assert out["by_model"] is (m["answered"] > 0) and isinstance(m["seconds"], float)
    assert all(r["proposed_by"] == "model" for r in out["rows"] if r["field"] in loop.sent[0])
    runtime.set_loop(FakeLoop(lambda _fields: None))  # no model: the same rows by the rules, and the summary says so
    out = call("mapping.suggest", {"source_id": SID, "resource": RES}, "developer")["output"]
    assert out["model"] | {"seconds": 0} == {"asked": 0, "answered": 0, "fields": 3, "seconds": 0, "stopped": "no_model"}
    assert out["by_model"] is False and all(r["proposed_by"] in ("rule", "memory") for r in out["rows"])
