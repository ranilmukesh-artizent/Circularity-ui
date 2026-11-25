# Plan 9 run: report for the person

Rewritten by the lead as the run goes. Last update: 25 Nov 17:00 IST.

## Done
- **Phase 0: all 16 tasks and the gate, green.** Each task was re-tested by the lead on the main stack before its
  commit; the gate counts are in PROGRESS.md (api 4,591 passed, source-sim 271, web 329, both browser smokes, story
  matrix, selftest).
- Phase 0 review: 4 findings (`docs/agents/plans/09-work/review-phase-0.md`), 3 fixed in `28fe893`.

- **Phase 1: 12 of 15 merged**, each re-tested on the main stack (parallel suite of every non-serial api test, the
  serial files it touches, lint, web; smoke-pages for 11 accounts after the menu change): pack format v1 (I-1), gate
  catalogue (I-2/I-3), customer overlay (I-4), queue planner (I-5), one decider (I-6), pack versions with
  maker-checker, case process layer and My work (I-20), My work in the menu, standard valuer (I-21), match to the
  system of record, contract entitlement gate, carbon with provenance.

## In flight
- P9-1.13 pack-driven views. Then P9-1.14 and the phase 1 gate; phases 2 and 3 follow.

## Blocked (needs you)
- None.

## For your decision
- **Autopilot on case open (P9-0.9, off by default):** an auto-started run with autonomy `act` submits the decision
  for approval in the opener's name; a person still approves. Keep, or hold every write of an auto-started run as a
  proposal? (review finding 1)
- **Decision workflows in Studio:** Save and import refuse a new one; create and publish do not, because the demo's
  golden scenario creates and publishes one (parity). Changing that needs a decision-log row and a regenerated golden.
- P9-0.4's writer ran a security auditor against the brief; its notes (header-only agent identity, exact-id hold
  lists) are known gaps planned for P9-13.9.

## Decisions taken without you
- P9-1.5: under a flow with business rules, depot slots are planned with those rules (decision-log row); no seeded
  case changes.
- P9-1.1 invented pack data the research does not give (stage confidence 0.75, stage agent names, carbon `d_rule`,
  device exception owners and KPI texts); listed in its commit for review.
- Telecom (phase 10) and medical rental (phase 11) depend on the phase 8 gate, so the three asset packs can run side
  by side.
- Libraries for phases 0-3 installed up front in one rebuild; `packaging` moved 26.3 -> 26.4 as uv required.
- `org.importPack` no longer runs the graph checks at import (P9-0.7; a pack's workflows may name sources not
  connected yet); schema and importer checks still run, and publish runs the graph checks.

## Lessons the run applied
- A task can break another task's tests through shared pack data (P9-1.11's gate broke 2 overlay tests); the lead's
  parallel-suite run after every merge caught it, and the lead fixed the tests (`be9a839`).
- Writers now quote a red-first run, start no agents, and run checks in the foreground (timers flooded the lead).
- Browser smokes run after `wait-idle.sh` (the post-reset syncs delay the RT-1048 instruction).
