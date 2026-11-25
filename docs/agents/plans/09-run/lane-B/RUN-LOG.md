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
