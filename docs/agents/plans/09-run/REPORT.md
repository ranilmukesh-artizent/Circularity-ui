# Plan 9 run: report for the person

Rewritten by the lead as the run goes. Last update: 25 Nov 05:05 IST.

## Done (phase 0: 7 of 17)
- P9-0.1 decisions and licence list; P9-0.2 `gate-p9.sh`; P9-0.3 `story-matrix.sh`; P9-0.16 Studio decision workflows
  point to the Modeler; P9-0.6 carbon factors and a CO2e line in both valuers; P9-0.5 model chain with rate-limit
  fallback; P9-0.4 catalogue hygiene, `credentials.rotate` forbidden to agents.
- Each was re-tested by the lead on the main stack before its commit (counts in PROGRESS.md and the commit bodies).

## In flight
- P9-0.7, P9-0.11, P9-0.9, P9-0.10 (Sonnet writers).

## Blocked (needs you)
- None.

## For your review
- P9-0.4's writer ran a security auditor (against the brief). Its notes, to weigh at the phase-0 review:
  - an agent that sends `X-Circularity-Confirmed: true` skips the hold on `mapping.revert` and `tables.update` (the
    existing "confirmed means a person pressed it" rule);
  - an agent that omits the preparer header skips the agent gate (the known per-agent credentials gap, plan item
    P9-13.9);
  - `HELD_FOR_PERSON` and `NO_AGENT_READS` are exact-id lists not asserted at import like `FORBIDDEN_ACTIONS`.
- P9-0.6 changes only the CO2e figure on tool-fleet and device cards (report `docs/agents/plans/09-diffs/P9-0.6.md`).
- Several writers wrote tests after the code; the brief now requires the red run to be quoted.

## Decisions taken without you
- Telecom (phase 10) and medical rental (phase 11) depend on the phase 8 gate, so the three asset packs can run side
  by side.
- Libraries for phases 0-3 installed up front in one rebuild; `packaging` moved 26.3 -> 26.4 as uv required.

## Gates
- None yet (phase 0 gate after its last task).
