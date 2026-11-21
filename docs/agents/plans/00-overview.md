# After B17: the work queue for agents

Status: proposed, 20 Nov 2026. Read `AGENTS.md` first. Each plan below is executed by the loop in `loop.md`, one task per
iteration, in this order. Do not start a plan before the previous one's phase gate is green.

| # | Plan | Delivers | Phase gate (must be green before the next plan) |
|---|---|---|---|
| 0 | `loop.md` | the Ralph-style loop that runs plans 1–5 | a dry run completes one task of plan 1 and stops cleanly |
| 1 | `01-b17c.md` | **done 20 Nov 2026:** the in-browser engine is deleted, RT-1048 runs end to end in the browser | web checks, smoke for 11 accounts, `smoke-rt1048.mjs` |
| 1b | `01b-refactor.md` (audit of 20 Nov 2026; user decision) | the codebase at full-stack best practices: trustworthy gates, layout and naming (`index.html` → `fixtures/demo/`), lint/type/CI, backend and frontend structure, container hardening; behaviour unchanged | full api + source-sim suites and smoke at each phase end |
| 2 | `02-queue-and-tasks.md` | a hardened job queue (priorities, scheduling, dead letters, stale-lock reaper, LISTEN/NOTIFY wake-up) and task CRUD | same |
| 3 | `03-crud-and-gzip.md` | a REST resource for every entity (`/api/v1/...`), writes through the action pipeline, gzip on JSON, never on streams | same + gzip/stream tests |
| 4 | `04-async.md` | async database access, async endpoints and an async worker, end to end | same + a concurrency smoke |
| 5 | `05-otel.md` | OpenTelemetry traces, metrics, logs; GenAI spans for Ask (Groq) and MCP spans; local Grafana LGTM | same + spans visible for a sample request |
| 6 | `06-fabric-production.md` (user request 21 Nov 2026: runs **next**, after plan 2 tasks 1–3) | the Connection Fabric for real: encrypted per-source credentials and URLs, a configured adapter for catalogue and hand-made sources, mappings that run, canonical checks, sticky conflicts, block settings, a workflow engine that processes records on its triggers | per phase: full suites, web checks, smoke for 11 accounts, RT-1048, and the phase's Chrome walk-through |

## Order and why

1. B17c first: the frontend must stop depending on the engine before the API changes shape (plans 3–4 would otherwise
   have to keep two backends in step).
2. Queue before CRUD: task CRUD (plan 3) exposes the queue's new states.
3. CRUD before async: convert endpoints once, after they exist.
4. OTel last: instrument the final async code paths once, not twice.

## Rules for every plan (in addition to `AGENTS.md`)

- One task = one commit = one short report line in `docs/agents/plans/PROGRESS.md` (date, plan, task, commit, tests run).
- Write the failing test first (`test-driven-development` skill). Run the task's own tests, then the plan's targeted set.
- The full suites run only at the phase gate (they take ~27 min); never two api pytest runs at once (`scripts/dev/api-test.sh` holds the lock).
- Behaviour visible to users must not change unless the task says so; the golden parity tests stay green.
- Stop and ask the user (write `BLOCKED.md`, see `loop.md`) when: a test outside the task fails and the cause is not the task;
  a task needs a decision the plan does not make; anything touches `.env`, secrets, or `git push --force`.
