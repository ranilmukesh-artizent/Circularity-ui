# S: browser smokes and UI check on the combined code (feature/fullstack-poc @ 8fea98c), 24 Nov 2026

Stack: Docker, web :5173, api :8000. Run by `work/smokes.sh after` (reset before each smoke, reset at the end).
Nothing edited, nothing committed. Final `scripts/dev/reset.sh`: exit 0.

## Smokes (after vs baseline)

| Smoke | After | Key line after | Baseline |
|---|---|---|---|
| pages | exit 0 | 11 accounts, 0 failing routes on each (admin 69 routes) | exit 0, 0 failing |
| rt1048 | exit 0 | "RT-1048 reached stage 10 (every stage done)", page errors: none | exit 0, same line |
| modeler | exit 0 | "smoke-modeler: all checks passed" (17 ok lines) | exit 0, 17 ok lines |
| mvp | exit 0 | "smoke-mvp: all 12 steps passed", page errors: none | exit 0, 12 steps |

Logs: `evidence/after-smoke-{pages,rt1048,modeler,mvp}.log`. No re-run was needed: nothing failed and nothing was flaky.
Note: the route count per account in smoke-pages differs from the baseline (executive 33→34, planner-a 42→34,
developer 39→40, wm-1 24→29, wm-2 29→25). Not a regression: the script collects the links on the landing page
800 ms after sign-in, so the count depends on how much of Home has rendered by then (the wm-1/wm-2 numbers swap
between runs). Each route that was visited passed.

## UI check (Node Playwright, installed Chrome, read-only)

Script: `<scratchpad>/ui-check.mjs` (run from `frontend/`). Results: 3 of 3 screens render.

- a. admin, Analytics: the Org unit filter lists Workspace, Customer A, Customer B and Customer C. Choosing Workspace
  shows "Pilot report". It opens "Pilot report · Workspace" with Pilot mode off, Cases 128, Decisions submitted
  79, Decisions approved 38, Recommended net value $199,829, rules applied 0, Instructions held 0, routes
  (resale 35, redeploy 31, ...) and "No instruction has been held yet." There is no error. Screenshot: `evidence/after-ui-pilot-report.png`.
- b. developer, Connection Fabric > Source Map (List) > Market pricing tile: the drawer's Configuration tab shows
  "Org unit" (`#sd_org`), which is enabled, set to "Shared by every org unit", and lists Workspace and Customers A, B
  and C. Nothing was saved (the context was closed). Screenshot: `evidence/after-ui-source-drawer-org.png`.
  Cosmetic: the select is narrow, so its default text shows clipped as "Shared by every".
- c. planner.a, Home (#/home): renders the sidebar, the KPIs and the tasks, with 0 console errors and 0 page errors.
  Screenshot: `evidence/after-ui-home-planner-a.png`.

## Console errors

- admin session: one "Failed to load resource: 404 (Not Found)". No app or API response was 400 or higher (checked with
  a response listener in a second run). The 404 is `/favicon.ico`: curl returns 404, and the index has no icon link.
  smoke-pages filters out the same message (`favicon`), so it is benign.
- developer and planner.a sessions: none.
