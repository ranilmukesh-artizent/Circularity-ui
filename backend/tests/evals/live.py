"""The live eval run (plan 9, P9-2.15; R16): the chain, configuration and injection datasets against each real model.

    python -m tests.evals.live      (through scripts/dev/evals-live.sh: behind the api test lock, worker stopped)

For each enabled provider model with a key (`router.eval_candidates`), the datasets of `suites.LIVE` run with that model in the
loop instead of the scripted ones (`scripted.use_live`). Every case still resets the demo's starting state and the evaluators
are the CI ones; only the model differs. The percent of cases that held is written to the model's row: `eval_prev` takes the old
`eval_score`, `eval_score` the new one, `eval_at` is now. `router.chain_for` then leaves out a model whose score fell more than
10 points. Prints each model's id and scores, never a key. Never part of the gate: a real model's answers are not repeatable.
The key stays in the environment the container already has (`key_ref` names the variable); this module never reads `.env`.
"""

import sys

from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions import hold
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.llm import router
from tests import starting
from tests.evals import scoring
from tests.evals.scripted import use_live
from tests.evals.suites import LIVE, run_suite


def _loop_for(ref: router.ModelRef) -> PydanticAILoop:
    return PydanticAILoop(lambda s, _run, _role: router.build_model(s, [ref]))


def _record(model_id: str, value: float) -> None:
    with SessionLocal() as s:
        s.execute(
            text("UPDATE llm_model SET eval_prev = eval_score, eval_score = :v, eval_at = now() WHERE id = :i"),
            {"v": round(value, 1), "i": model_id},
        )
        s.commit()


def main() -> int:
    with SessionLocal() as s:
        refs = router.eval_candidates(s)
    if not refs:
        print("no enabled model has a key in this environment: nothing to evaluate")
        return 1
    real = hold._case_state
    hold._case_state = lambda *a, **k: (real(*a, **k)[0], False)  # type: ignore[assignment] # as the tests: no synced conflicts
    try:
        for ref in refs:
            use_live(_loop_for(ref))
            reports = [run_suite(name) for name in LIVE]
            value = scoring.score(reports)
            _record(ref.id, value)
            parts = ", ".join(f"{r.name} {scoring.pass_rate(r):.0f}%" for r in reports)
            print(f"{ref.id} ({ref.model}): eval_score {value:.1f} ({parts})")
            for r in reports:
                for line in scoring.failed(r):
                    print(f"  not held: {line}")
    finally:
        use_live(None)
        hold._case_state = real
        starting.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
