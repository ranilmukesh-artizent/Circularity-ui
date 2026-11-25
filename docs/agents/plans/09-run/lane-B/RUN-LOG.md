# Lane B run log

One line per event, newest last, times from `date`.

| Time | Event |
|---|---|
| 2026-11-25 17:31 | Lane B started on feature/plan-09-lane-b from origin/feature/plan-09-recover (bf3b967); branch pushed. |
| 2026-11-25 17:31 | Decision: 2 writers, not 3. The Docker VM has 8 GB (host 15.7 GB); raising it to 11 GB was refused by the session's permission check. |
| 2026-11-25 17:31 | Decision: writers use manual worktrees C:/Users/mahizhans/Documents/circ-wt/w<k> (branches lane-b-w<k>). The Agent tool's worktree isolation refuses here (drive-letter case), so it is not used. Machine notes for writers: lane-B/MACHINE.md. |
| 2026-11-25 17:31 | Dispatch P9-3.1 to w1 (sonnet), P9-6.1 to w2 (sonnet). |
| 2026-11-25 17:39 | P9-6.1 returned by w2 (fca1306). Decision: P9-3.21 parked in blocked.txt, since its Depends on (P9-3.6 ... P9-3.20) is not met although plan-next shows it ready. |
| 25 Nov 12:19 | P9-6.1 merged. bids gain buyerStatus (B05 unverified); /_sim/systems lists extras (windchill test 21+extras) |
| 2026-11-25 17:49 | Merged P9-6.1 as a293b6d and pushed (lead-verify ok, web 379, source-sim 60 passed). Nothing else ready until P9-3.1 lands (shared logic files). |
| 25 Nov 12:51 | P9-3.1 merged. EXTRA_SYSTEMS merged with P9-6.1 (both kept); 332 lines (320 + 12 BAT) |
| 2026-11-25 18:21 | Merged P9-3.1 (w1 5e8e1e2); conflict in registry.py and test_generic_specs.py, kept both. lead-verify ok, api 23, source-sim 98 passed. |
| 2026-11-25 18:21 | Dispatch P9-3.2 to w1, P9-3.4 to w2 (sonnet). |
| 2026-11-25 18:54 | Fix: plan-next.py read 'Depends on' only to the end of its first line (wrapped lists were ignored) and did not expand 'P9-a.b ... P9-a.c' ranges; both fixed. P9-3.21 back from blocked (now correctly waits). |
| 2026-11-25 18:54 | Decision (person asked for maximum parallelism): PLAN_DEPS_ONLY=1 for lane B. Phases 4 and 5 start on their tasks' own Depends on, not the whole previous phase; 'the Phase N task that ...' keeps phase N. Logic files are ordered within a track (tool fleet 3-5, device 6). 4 writers, wt-check runs take two slot locks (/tmp/wt-slot-0/1.lock). |
| 2026-11-25 18:54 | Dispatch P9-3.3 to w3, P9-4.1 to w4 (sonnet). |
| 2026-11-25 18:56 | Merged origin/feature/plan-09-recover (9 commits: P9-2.11, 2.12, 2.13, 2.18, 2.22, 8.1, plan-next fixes) as dc48cb2. Took lane A's Depends-on parsing fix and dropped mine; kept PLAN_DEPS_ONLY on top. |
| 2026-11-25 19:00 | P9-3.2 returned by w1 (7ce1748; cherry-picked as e815a69 for the next base); waits for the suite to finish before merge. Dispatch P9-6.2 to w1 on top of e815a69. |
| 2026-11-25 19:05 | P9-3.4 returned by w2 (eca5d15); waits for merge (check test_workflow_open_case on the main stack). Dispatch P9-3.5 to w2 on top of P9-3.2 + P9-3.4. |
| 2026-11-25 19:50 | Suite after the lane A merge: shard 1 2027 passed; shard 2 2249 passed, 2 failed (test_ask_chain: empty chain, chain of two; llm_model rows, suspected order dependence); lint ok, web 395. Re-run alone after the restart. |
| 2026-11-25 19:50 | P9-3.3 returned by w3 (08ff72e). Nothing ready for w3: each remaining task waits on P9-3.5, P9-4.1 or P9-6.2. Decision (person asked): WSL memory to 11 GB, restart when the check locks are held. |
| 2026-11-25 19:55 | P9-4.1 returned by w4 (7bd11ff). Dispatch P9-4.2 to w4 on top of it; the lead adds zen-engine==2.1.8 to the locks with the WSL restart rebuild. |
| 2026-11-25 19:58 | Merged origin/feature/plan-09-recover again (P9-2.14, 2.19, 8.8, 8.12, 8.17, phase 8 libraries) as 7324e9e and pushed, at the person's request. The lane is level with lane A. P9-3.21 waits through plan-next (lane A's range fix), not blocked.txt. Images rebuild at the WSL restart. |
| 2026-11-25 20:01 | Decision: zen-engine pinned at 2.1.7, not the spec's 2.1.8 (released 2026-11-20, under two weeks). Writer 4 told. |
| 25 Nov 14:34 | P9-3.2 merged. closed recall RC-2026-009 added; 30 serials without telematics |
| 25 Nov 14:34 | P9-3.3 merged. tool rows after the 48 industrial parts; illustrative rated lives for four classes |
| 25 Nov 14:34 | P9-3.4 merged. x_case gains reason_field and facts; smoke-p9-3 step 1 written, runs at the gate |
| 25 Nov 14:34 | P9-4.1 merged. sdesk reads New tickets only (40); 60-month nominal life |
| 2026-11-25 20:09 | Committed P9-3.2, 3.3, 3.4, 4.1 (one commit each, from the writers' commits); batch verify after the restart. WSL restarted with 11 GB (person's go-ahead); check locks held while the images rebuild (phase 8 libraries, zen-engine). |
| 2026-11-25 20:32 | P9-6.2 returned by w1 (dd5b3a1); sent back: dvlab landed rows in map() (a dry run would write); move to the reader via client.session as P9-4.1, and mark the mock-changing wipe test. P9-3.5 returned by w2 (d762559). Dispatch P9-6.3 to w3 (on 6.2) and P9-3.6 to w2 (on 3.5). |
| 2026-11-25 20:49 | P9-6.2 fixed by w1 (cd95b5f): dvlab lands rows from the reader via client.session; dry-run test added; the wipe-in-mock test moved to serial-only test_device_wipe_sim.py. w1 idle: nothing ready until P9-6.3, 3.6, 3.7 or 4.2. |
| 25 Nov 15:24 | P9-3.5 merged. grade_of takes now (pure core); evidence type in tool_fleet.json data.mappings; smoke step 1 org kind company |
| 25 Nov 15:24 | P9-6.2 merged. dvlab lands rows from the reader (dry run writes nothing); evidence types in valuer.params; wipe test serial-only |
