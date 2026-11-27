# Phase 7 review (P9-7.9): replay, back-test, publish in steps

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-7.*` commits
`abd0a270` (7.1), `8d86cdaa` (7.2), `b9c28901` (7.3), `ce7a596f` (7.4), `a37b7dfe` (7.5), `64558e48` (7.6), `c1729881` (7.7, 7.8).
No test was run; every finding was checked by reading the code at the cited line. Focus: Review Focus 9 and 10, agents never
approve or widen, tenant boundary, money in Decimal.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P1 | The replay gate of a canary is matched on the draft's version number, not on its content. `flow.saveDraft` always sets `dver = ver + 1`, so a discarded or edited draft has the same `dver` as the one that was replayed. `done_replay(flow, dver)` then accepts the old run, and `rollout.startCanary` (guard `NEEDS_REPLAY`) starts a canary of rules nobody replayed. | `repositories/rollouts.py:259-267`; `services/actions/modeler.py:243`; `services/actions/rollout.py:199-200` | Yes (code; not run) | Needs code: store the draft's graph hash (or a draft save counter) on `replay_run` and match on it; refuse a start when the draft changed after the run. Test: replay, edit the draft, start a canary, expect `conflict`. |
| 2 | P2 | `rollout.full` has no evidence precondition: stage `canary`, status `shadow` and the maker rule are all it checks. A canary with 0 cases, a "Too few cases" note or a report breach can be published in full at once. The report is advice only. | `services/actions/rollout.py:349-363` | Yes | Needs a decision: refuse (or require a reason) while `sample_note` is set or a breach is open. |
| 3 | P2 | The automatic stop rules cover three rates only (exception, override, hold). A canary that loses money (mean net below the control, band95 below 0) never pauses. | `services/modeler/canary_stats.py:23-27`, `:98-110` | Yes | Add a `net_margin` rule using the band, with the same `min_cases`. |
| 4 | P2 | Money in the canary report and the replay measures is `float`: `::float` in SQL, `float(r["net"])`, bootstrap means. Numbers are not stored or posted from here, so the effect is display only, but it breaks the Global Constraint "money in Decimal". | `repositories/rollouts.py:294-295`; `services/modeler/canary_stats.py:50-51`, `:75-90`; `services/replay/run.py:481-485` | Yes | Accept and record in the decision log (statistics), or read `net` as `numeric` and sum in `Decimal`. |
| 5 | P2 | `rollout.report` and the stop check read only rollouts in `canary`/`paused`; after `rollback` or `full` the report is empty, so the comparison a person decided on is not kept. | `repositories/rollouts.py:283-305` | Yes | Keep the last report on the rollout row at `full` and `rollback`. |

## Checked, no findings

- Agents never run, prepare or widen a rollout: `rollout.` is in `FORBIDDEN_ACTIONS` (`services/agents/forbidden.py`); every write guard also refuses `ctx.preparer` (`rollout.py:138-145`). `rollout.autoPause` is risk `system` and the pipeline refuses it for any actor but SYSTEM (`pipeline.py:213`); it only pauses, never widens (`rollout.py:521-580`).
- Maker-checker on start, widen and full (`_maker`, journal rule), and for table canaries the makers of the market's tables (`rollout.py:148-155`, `:231`, `:291`).
- Tenant boundary: replay import, run, report and runs use `_org_ok` on the batch's org and on the flow (`actions/replay.py:95-101`, `:236-242`, `:272-278`, `:318-321`); rollout reads and writes go through `_reach`/`_read_guard` (`rollout.py:142`, `:399-409`).
- Review Focus 10 (canary share and region): assignment is a stable hash of case, flow and salt, exact region match, stored and sticky through approval; `out` cases never touch the canary (`services/modeler/rollout.py` `assign`, `repositories/rollouts.py:84-101`). Rollback deletes undecided assignments only (`:233-244`).
- Review Focus 9 (no future facts): `as_of_facts` drops and lists any reading dated after the decision or with no date; `assert_no_future` refuses (`services/replay/run.py:65-105`). `realised_value` is used only to measure, never as an input (`run.py:481`). The industrial pack is refused by a replay (`run.py:135`), so no demo number can move.
- Import refuses a header that looks personal (documented at `services/actions/replay.py:29`; the check itself was not read line by line).

## Needs code

- F1 (P1): bind the replay to the draft's content.
- F2-F5: decisions or small changes as listed.

Legal: none of the findings is accounting or reporting text.
