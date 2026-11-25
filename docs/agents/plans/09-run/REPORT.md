# Plan 9 run: report for the person

Rewritten by the lead as the run goes. Last update: 25 Nov 16:18 IST (times from `date`).

## Where it stands
- **Phase 0: done** (16 tasks and the gate). Review: 4 findings, 3 fixed in `28fe893`.
- **Phase 1: done** (14 tasks and the gate). Review: `docs/agents/plans/09-work/review-phase-1.md`; finding #2 (gates
  must be evaluated before the queue plan, R20, `cases/decide.py`) is queued as a fix task now that P9-2.1 is in.
- **Phase 2 (lane A): 8 of 17.** Merged: stage chain (I-7, P9-2.1), agent loop on Pydantic AI (I-8, 2.2), model
  router (I-9, 2.3), hold policy (I-10, 2.4), standing policy (I-11, 2.5), run tracing and the agent run view (I-12,
  2.6), exception assistant (2.10). Each re-tested by the lead with `lead-verify.sh` before its commit.
- **Lanes:** the plan runs in two lanes (`docs/agents/plans/09-lanes/`). Lane A (phases 2, 7, 8) here on
  `feature/plan-09-recover`; lane B (phases 3-6) by Mahizhan on `feature/plan-09-lane-b`, started from
  `lane-B-start.md`. Everything lane B needs from phase 2 (P9-2.1, 2.4, 2.5) is pushed. Lane B's branch is not on
  origin yet.

## In flight
- P9-2.7 configuration agent drafts pack changes (I-13, migration 0040), writer 1.
- P9-2.8 the queue stage waits for the queue plan, writer 2.
- Next: P9-2.9, 2.11-2.16, the phase 1 finding #2 fix, then the phase 2 gate (P9-2.17); then phases 7 and 8.

## Blocked (needs you)
- None.

## For your decision
- **Autopilot on case open (P9-0.9, off by default):** an auto-started run with autonomy `act` submits the decision
  for approval in the opener's name; a person still approves. Keep, or hold every write of an auto-started run as a
  proposal? (phase 0 review finding 1)
- **Decision workflows in Studio:** save and import refuse a new one; create and publish do not, because the demo's
  golden scenario creates and publishes one (parity). Changing that needs a decision-log row and a regenerated golden.
- **Invented pack data** (P9-1.1: stage confidence 0.75, stage agent names, carbon `d_rule`, device exception owners
  and KPI texts): listed in its commit; confirm or replace.
- **Docker memory:** cap the WSL VM at about 14 GB in `.wslconfig`? Until then the run keeps to 2-3 writers and 3
  test shards.
- **Legal:** contract, consent, chain-of-custody and gate wording, and `09-licences.md`, need review by Kinective's
  Legal team before they are relied on.
- P9-2.3 left open items for a later task: the runtime drops `model_route`, Ask has no budgets, `complete_json` uses
  `ASK_MODEL_CHAIN`.

## Decisions taken without you
- Telecom (phase 10) and medical rental (phase 11) depend on the phase 8 gate, so the three asset packs can run side
  by side.
- P9-1.5: under a flow with business rules, depot slots are planned with those rules (decision-log row); no seeded
  case changes.
- Libraries for phases 0-3 installed up front in one rebuild; `packaging` moved 26.3 -> 26.4 as uv required.
- `org.importPack` no longer runs the graph checks at import (P9-0.7); schema and importer checks still run, and
  publish runs the graph checks.
- Agent-chain tests pin the main stack's 428 synced source conflicts off with one shared fixture
  (`no_synced_conflicts`, `a2b5272`); the hold policy itself is unchanged.

## Lessons the run applied (also in `docs/agents/learnings.md`, 25 Nov)
- Per merge only the task's tests, lint and web (`lead-verify.sh`, 3-5 min); the full suite and smokes at gates.
  Running the full suite after every merge cost hours.
- `lead-verify.sh` prints each failure's error and line and keeps the log, so a broken test is traced in minutes.
- Writers quote a red-first run, start no agents, and run checks in the foreground.
- Browser smokes run after `wait-idle.sh`; new demo-state tables join `reset()`.
