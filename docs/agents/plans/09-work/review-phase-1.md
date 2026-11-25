# Phase 1 review

Reviewer: one Opus `code-reviewer` over the phase 1 code (P9-1.1 … P9-1.14), 25 Nov 2026, reading the files at
`58c604b` (no tests run). The lead checked each finding in the code before acting.

| # | Finding | Lead's check | Action |
|---|---|---|---|
| 1 | SLA timers never fire: `open_item` queues `work.sla` at `clock.now() + due` (pinned workspace clock) but the queue claims on the database clock; `on_sla` says not due and never re-queues | Confirmed (`cases/process.py`, `core/jobs.py`) | Fix writer (P9-1.15 review fixes) |
| 2 | Gates run after the queue plan, so a gate-blocked route can win an order and leave it unfilled (R20) | Plausible from `cases/decide.py`; touches the decider P9-2.1 is extending | Separate fix after P9-2.1 merges |
| 3 | Second decision paths: `case.reevaluate` of a data-opened industrial case and `evidence.recordResult` use `_rebuild` (R19) | Confirmed (`actions/decisions.py`) | Fix writer |
| 4 | Overlay actions and the Customer layer panel use the pack file, not the pack version in force | Confirmed (`actions/overlays.py`, 5 calls to `load_pack`) | Fix writer |
| 5 | `pack.import` accepts the `industrial` key and a changed valuer kind | Confirmed (no refusal in `actions/packs.py`) | Fix writer |
| 6 | `overlay.approve` does not re-check the status after its row lock (race) | Likely | Fix writer |

Checked with no defect: agent refusals on overlays, pack versions and work items; maker-checker from the journal;
tenant checks on work items and My work; every new write through the pipeline; no wall-clock use in the core; no
`eval` in the amount grammar.
