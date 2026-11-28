"""Plan 11, C1: the stored drafts of a pack's sample prompts. A stored draft is used for a sample prompt, goes through the same
checks as a live model answer, is marked `stored`, and never calls a model; any other text calls the model as before. No test
here calls a real model: the loop is a double, the stored file is written to a temporary folder."""

from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.config_agent import ModelDraft
from di.services.agents.loop import LoopResult
from di.services.modeler import compose as core
from di.services.modeler.pack import load_pack
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
ORG = "Customer A"
PACK = "tool_fleet"


class FakeLoop:
    """A loop double: returns `out` (a draft, or None for no model) and counts its calls."""

    def __init__(self, out: ModelDraft | None = None) -> None:
        self.out, self.calls = out, 0

    def run(self, s, spec, prompt, *, ctx, resume=None) -> LoopResult:
        self.calls += 1
        return LoopResult(output=self.out, model="fake" if self.out else None)


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        mine = "SELECT seq FROM action_journal WHERE action LIKE 'compose.%'"
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    yield
    runtime.set_loop(None)
    _clean()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(core, "STORED_DIR", tmp_path)
    return tmp_path


def _prompt() -> str:
    return load_pack(PACK).prompts[0]


def _stored(pack: str = PACK, draft_pack: str = PACK, prompt: str | None = None) -> None:
    draft = ModelDraft(pack=draft_pack, kpis=["Net recovered"], systems=["SAP"]).model_dump(mode="json")
    core.write_stored_draft(pack, load_pack(pack).version, prompt or _prompt(), draft, "2026-11-28T00:00:00+00:00")


def _start(body_text: str | None = None) -> dict:
    r = call("compose.start", {"org_unit_id": ORG, "text": body_text or _prompt(), "pack_key": PACK}, "planner-a")
    assert r.get("ok"), r
    return r["output"]


def _row(cid: int) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM composition WHERE id = :i"), {"i": cid}).mappings().one())


# ---------------------------------------------------------------- the pure part
def test_key_ignores_case_and_whitespace_but_not_words_or_version():
    k = core.draft_key("Sell  the tools\n today ", "1.0.0")
    assert k == core.draft_key("sell the tools today", "1.0.0")
    assert k != core.draft_key("sell the tools tomorrow", "1.0.0")
    assert k != core.draft_key("sell the tools today", "1.0.1")


def test_a_stored_draft_round_trips_and_misses_on_other_text_or_version(tmp_path: Path):
    core.write_stored_draft("p", "1.0.0", "Sell the tools", {"pack": "p"}, "t", tmp_path)
    core.write_stored_draft("p", "1.0.0", "Scrap the rest", {"pack": "q"}, "t", tmp_path)
    assert core.stored_draft("p", "1.0.0", "  sell THE tools ", tmp_path) == {"pack": "p"}
    assert core.stored_draft("p", "1.0.0", "Scrap the rest", tmp_path) == {"pack": "q"}
    assert core.stored_draft("p", "1.0.0", "Sell the tools now", tmp_path) is None
    assert core.stored_draft("p", "1.1.0", "Sell the tools", tmp_path) is None
    assert core.stored_draft("nope", "1.0.0", "Sell the tools", tmp_path) is None


def test_an_unreadable_stored_file_is_a_miss(tmp_path: Path):
    (tmp_path / "p.json").write_text("{not json", encoding="utf-8")
    assert core.stored_draft("p", "1.0.0", "x", tmp_path) is None


# ---------------------------------------------------------------- compose.start
def test_a_sample_prompt_uses_the_stored_draft_without_a_model(store: Path):
    _stored()
    loop = FakeLoop(ModelDraft(pack=PACK))
    runtime.set_loop(loop)
    out = _start(" ".join(_prompt().split()).upper())  # case and spacing do not matter
    row = _row(out["id"])
    assert loop.calls == 0
    assert row["steps"]["describe"]["draft_source"] == "stored" and row["reading"]["by_model"] is True
    assert row["change_set"]["by_model"] is True and row["change_set"]["kpis"] == ["Net recovered"]
    assert "stored draft" in out["log"]


def test_other_text_still_calls_the_model(store: Path):
    _stored()
    loop = FakeLoop(ModelDraft(pack=PACK, kpis=["Live"]))
    runtime.set_loop(loop)
    out = _start(_prompt() + " Also resell to staff.")
    row = _row(out["id"])
    assert loop.calls == 1 and row["steps"]["describe"]["draft_source"] == "model" and row["change_set"]["kpis"] == ["Live"]


def test_no_model_and_no_stored_draft_is_marked_rules(store: Path):
    loop = FakeLoop(None)
    runtime.set_loop(loop)
    row = _row(_start()["id"])
    assert loop.calls == 1 and row["steps"]["describe"]["draft_source"] == "rules" and row["reading"]["by_model"] is False


def test_a_stored_draft_is_checked_like_a_live_one(store: Path):
    _stored(draft_pack="device")  # names a pack that is not in the call: `_accept` refuses it
    loop = FakeLoop(None)
    runtime.set_loop(loop)
    row = _row(_start()["id"])
    assert loop.calls == 1  # the refusal sent it to the model; none answered
    assert row["steps"]["describe"]["draft_source"] == "rules"


def test_a_stored_draft_of_another_pack_version_misses(store: Path):
    draft = ModelDraft(pack=PACK).model_dump(mode="json")
    core.write_stored_draft(PACK, "0.0.0", _prompt(), draft, "t")
    loop = FakeLoop(ModelDraft(pack=PACK))
    runtime.set_loop(loop)
    assert _row(_start()["id"])["steps"]["describe"]["draft_source"] == "model" and loop.calls == 1


def test_an_answer_redrafts_with_the_model_and_updates_the_source(store: Path):
    _stored()
    loop = FakeLoop(ModelDraft(pack=PACK))
    runtime.set_loop(loop)
    out = _start()
    opt = out["change_set"]["question"]["options"][0]["id"]
    r = call("compose.answer", {"id": out["id"], "answer": opt}, "planner-a")
    assert r.get("ok"), r
    assert loop.calls == 1 and _row(out["id"])["steps"]["describe"]["draft_source"] == "model"
