# Plan 9 run: report for the person

Rewritten by the lead as the run goes. Last update: 25 Nov 09:15 IST.

## Done
- **Phase 0: all 16 tasks and the gate, green.** Each task was re-tested by the lead on the main stack before its
  commit; the gate counts are in PROGRESS.md (api 4,591 passed, source-sim 271, web 329, both browser smokes, story
  matrix, selftest).
- Phase 0 review: 4 findings (`docs/agents/plans/09-work/review-phase-0.md`), 3 fixed in `28fe893`.

## In flight
- Phase 1: P9-1.1 pack format v1 (the base of every later phase; the rest of phase 1 waits on it).

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
- Telecom (phase 10) and medical rental (phase 11) depend on the phase 8 gate, so the three asset packs can run side
  by side.
- Libraries for phases 0-3 installed up front in one rebuild; `packaging` moved 26.3 -> 26.4 as uv required.
- `org.importPack` no longer runs the graph checks at import (P9-0.7; a pack's workflows may name sources not
  connected yet); schema and importer checks still run, and publish runs the graph checks.

## Lessons the run applied
- Writers now quote a red-first run, start no agents, and run checks in the foreground (timers flooded the lead).
- Browser smokes run after `wait-idle.sh` (the post-reset syncs delay the RT-1048 instruction).
