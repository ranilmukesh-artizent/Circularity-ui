# Lane B browser smokes: handover to the lane A integrator (27 Nov 2026)

Lane B has finished every plan task of phases 3 to 6 and all their api, serial-only and source-sim tests are green (RUN-LOG, 27 Nov 01:35). What is left is the **final smoke pass**, which the lanes agreed lane A runs. Plan boxes **P9-3.22** and **P9-4.13** stay open until their smokes pass; tick them then.

## How to run a smoke (all five)

Before EVERY smoke: `bash scripts/dev/reset.sh`, then `bash scripts/dev/wait-idle.sh` (about 5 minutes together; the worker re-syncs every source after a reset and a smoke started too early fails at random). Then `node frontend/scripts/smoke-<name>.mjs http://localhost:5173`. Reset again afterwards. Host Node 26 and Chrome are enough. Git Bash forks fail often on the lane B machine: use PowerShell.

## State of each smoke

| Smoke | State | Notes |
|---|---|---|
| `smoke-rt1048` | **passes** (RT-1048 reached stage 10) | The script read the stage line after a fixed 2.5 s; it now waits for "Case at Stage N of 10". Not a product bug. |
| `smoke-pages` | not rerun since your 82dd9f6d | It failed on `#/integration/monitor` (403 for Engineer and Finance); your Monitor fix should clear it. |
| `smoke-p9-3` | steps 1 to 9 passed in runs; steps 10 to 17 unproven | `7df8bdf2` fixes steps 1 to 12; the working copy had a further unverified edit for steps 10 onwards (committed as work in progress). A full fresh run is needed. |
| `smoke-p9-4` | steps 1 and 2 pass; step 3 fails | "the estimate is a draft: it should be priced without a technician" (not diagnosed: script or product). Steps 4 to 7 have not run. |
| `smoke-p9-6` | never run | New in P9-6.20; its header lists the data assumptions (steps 4, 5, 7 and 8). |

## What the smokes taught us (read before debugging)

1. **First full sync.** `source.reconnect` of a source that is not live queues its first FULL sync at once. A manual `source.sync` afterwards reads only what is new. A script must have the ingest workflow published before that first sync, or put `mode: 'full'` on the connector and wait for the first sync to show in the history; `workflow.create` refuses a source that is not live ("Choose a system first"), so the workflow cannot simply be made first. `source.sync` is also dropped as a duplicate while the first sync still reads as running.
2. **Role access moved.** The Developer view no longer has the product pages (read `/api/screens/product/returned` as admin); the Approver gets "Page not found" on `#/agents` (read the Models panel as admin); planner.a (Customer A) cannot open tool-fleet-a cases until `access.requestTenant` is decided by an admin.
3. **Data.** Synthetic serials fail GR-07 (no contract line, or a contract owned by another programme); real Fleet North America lines: CMH-10972, CMH-11226, DCD-16500 (the measured life leaves refurbish open), BAT-14597. Only 5-digit serials count among the 18 returns; CMH-0001 to 0003 are extra rows.
4. **Timing.** After a sync or reset a case page can show "Loading..." for minutes; the first repairlog sync takes about 5.5 minutes in the worker and blocks everything else.
5. **Recycling** stops at "Waiting on Exit partner" until the Engineer attaches reporting evidence (`case.attachReporting`, G-REP-2); then Finance's confirm is refused with GR-06 as intended.
6. **Reruns on the same state** hit leftovers (an existing case, policy or submitted case): reset before every full run.

## Questions only the product owners can answer

- p9-3 step 9: a returned tool gets a fleet-wide renewal (FC-30101-R) instead of its own contract's (FC-30117-R). Should a case prefer its own contract's renewal?
- The worker's first repairlog sync (about 5.5 minutes) blocks every other job.
- Open review decisions (docs/agents/plans/09-work/review-phase-6.md): F3 (lot post bypasses the instruction queue), F6 (GR-D5 never fires on a received device), F8 (an ageing move leaves the old listing live).
