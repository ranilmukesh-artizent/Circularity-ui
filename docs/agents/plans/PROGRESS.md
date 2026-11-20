# Progress log

One line per step: date, plan and step, commit, the tests that gated it, result. Decisions taken without the user
(overnight run of 20–21 Nov 2026) are listed at the end for review.

| Date | Plan · step | Commit | Gate | Result |
|---|---|---|---|---|
| 2026-11-20 | 01b · A1 dev scripts exit with real status | `f15c0cd` | `selftest.sh` (passing 0, missing test 4, type error 2, clean 0) | done |
| 2026-11-20 | 01b · A2+A3 webhook subscription self-heals; health, async, SQL guards | `02a753c` | Phase A full suite: api 3,440 passed, source-sim 210 passed | done |
| 2026-11-20 | 01b · A4 "Try again" retries; network error code | `3c80c3e` | Phase A gate; web 15 tests | done |
| 2026-11-20 | 01b · A6 source-sim tests on their own database | `365f166` | source-sim 5× green (210) and Phase A gate | done |
| 2026-11-20 | 01b · C4 hash-locked Python deps | `e7246dc` | images rebuilt: pip check clean, same packages; 40 targeted api tests | done |
| 2026-11-20 | 01b · C5 CI, Dependabot, pre-commit, gitleaks | `1c5c67c` | actionlint clean; gitleaks full history: no leaks | done |
| 2026-11-20 | 01b · E5 part 1 web unit tests (111) | `7e10f43` | web suite 126 passed | done |
| 2026-11-20 | 01b · A5 ports on 127.0.0.1 | `3a5977f` | recreated; Windows reaches api, sim, web | done |
| 2026-11-20 | 01b · A5/A5b + C2 web toolchain majors, ESLint, dead code | `2337d46` | lint 0 errors (43 a11y warnings → E4); knip clean; tsc 0; 126 tests; build; smoke 0 failing | done |
| 2026-11-20 | 01b · C1 Python lint (shared ruff.toml, strict rules) | `a8323a7` | ruff check clean both services; api 687 + 957 targeted, source-sim 210 | done |
| 2026-11-20 | 01b · C1 ruff format (blame-ignored) | `4e5162c`, `a16db4b` | ruff format --check clean | done |
| 2026-11-20 | 01b · B3 web files named by convention (+ lint rule) | `a260188` | lint 0 errors, knip, tsc, 126 tests, build, smoke 0 failing | done |
| 2026-11-20 | 01b · B2 docs in kebab-case; README current | `c15daab` | grep old names (non-Python): none; 56 md files, 0 broken links | done (Python docstrings: sweep after Phase D) |
| 2026-11-20 | 01b · D3 metadata for all 19 tables | `fe0914d` | alembic check clean; scratch-db round trip; 10 tests | done |
| 2026-11-20 | 01b · B1+F1 demo to fixtures/demo; healthchecks | `c8a67a0` | goldens + assets.gen.ts regenerated: no change; all services healthy, `up --wait` 0; smoke 0 failing | done |
| 2026-11-20 | 01b · D1+D2 error envelope; settings and token hardening | `0d4d131` | api 439 + 207 targeted (1 sync-timing failure, passed on rerun), source-sim 13, web 131; full suite at the wave gate | done |
| 2026-11-20 | 01b · E1+E4 pure renders, session-scoped state; dialogs, Escape stack, keyboard access | `c084bfb` | staged tree alone: tsc 0, 141 tests, eslint 0 errors/0 warnings; smoke admin 70, planner-b 41, developer 39, wm-1 24, 0 failing; keyboard run on the RT-1048 approval | done |
| 2026-11-20 | 01b · F2 digest-pinned multi-stage images, non-root runtime, nginx + CSP | `6cd4218` | 6 targets build; runtime api/worker/sim on scratch DBs healthy; prod web: 68 pages, 0 CSP violations; compose config valid | done (services recreated at the wave gate) |
| 2026-11-20 | 01b · E3 every page a lazy chunk; vendor chunk | `ce6c42b` | staged tree alone: tsc 0, 141 tests, eslint, build (entry 1.05 MB → 142 kB); smoke 11 accounts 0 failing; deep links | done |
| 2026-11-20 | 01b · D4+D5 one copy of each read helper; screens are leaves; import contracts in CI | `24d43fa` | api gates 2776 / 2153 / 1877 / 2902 passed (2 single failures: DB state, SSE timing; rerun green); lint-imports 3 kept; ruff clean | done |
| 2026-11-20 | 01b · B2 (code) docstrings cite the renamed docs | `25954ea` | 108 files, only the doc-name strings change (checked per line) | done (3 source-sim files go with F4) |
| 2026-11-20 | 01b · G1+G2 quick start for any OS, `scripts/doctor.sh`; web runtime image self-contained | `f006757` | fresh `git archive` copy, no host Node: runtime image builds and serves (CSP, assets, sign-in 200); dev target builds; doctor exit 0 / 1 | done |
| 2026-11-20 | 01b · E2 one UI kit; area pieces named; no HTML-string builders | `22b199a` | jsdom old-vs-new markup identical (9/9); staged tree alone: tsc 0, 153 tests, eslint 0/0, knip, build; smoke admin 66, planner.b 41, warehouse1 24, 0 failing | done |
| 2026-11-21 | 01b · D6 shared test helpers; journal filters before LIMIT; one logging config; token calls not logged | `eff1f46` | full api suite 3,486 passed (with the change); staged tree alone: ruff, imports, 291 targeted passed | done |
| 2026-11-21 | 01b · F3 live stream with a short-lived ticket | `3fc0071` | staged tree alone: 50 api tests against a private api, ruff; web tsc 0, 154 tests, eslint; browser: `?ticket=` only, live messages arrive | done |
| 2026-11-21 | 01b · F4 source-sim fan-out and per-system reset | `0b0d9c2` | both new tests failed first; source-sim 213 passed; api connector tests 21 passed | done |
| 2026-11-21 | 01b · C3 (web) tsconfig split, noImplicitReturns/Override, typed Reference | `b5f8845` | staged tree alone: tsc -b 0, 154 tests, eslint, knip, build; smoke admin 66, planner-b 32, wm-1 24, 0 failing | done |
| 2026-11-21 | 01b · E6 useAction for writes; read cache on TanStack Query | `363a115` | staged tree alone: tsc -b 0, 168 tests, eslint, knip, build; smoke admin 70, planner-b 32, wm-1 24, 0 failing; refusal toasts equal the server's messages | done |
| 2026-11-21 | 01b · C3 (python) mypy, typed action contexts, Annotated dependencies | `84ed439` | mypy: no issues in 133 files; ruff clean; lint-imports 3 kept; full suite api 3,486 passed, source-sim 213 passed | done |
| 2026-11-21 | 01b · G3 portable dev scripts (lock in the api container), host ports from env, DEV_POLLING | see git log | selftest (lock + exit codes) passed; two api-test runs serialized; stack recreated, all healthy; second project on ports 18000/15173/18100/12222/15432 healthy; shellcheck clean; bash 3.2 syntax check | done |

## Decisions taken without the user (to review)

- **A5b, web toolchain majors:** chosen versions are vite 8.3.6, vitest 5.1.0, @vitejs/plugin-react 6.2.1 and
  jsdom 31.0.0, all at least 2 weeks old.
  - The demo's stylesheet has two invalid `@container or (...)` rules. Browsers ignore them; Vite 8's CSS minifier
    rejected them, so `css.lightningcss.errorRecovery` drops them with a warning.
  - react-router stays on 6.x. Its 2 moderate advisories need v7, which changes the routing APIs; that upgrade is left
    for a separate step.
- **C5, gitleaks:** `.gitleaks.toml` allowlists the source-sim mocks' synthetic AWS demo keys (`AKIACIRCULARITY…`).
  With that, a full-history scan finds no leaks.
- **C2, CasePage effect:** fixing the suppressed hook dependencies changed one small behaviour. After a landing
  redirect that ends on the same stage, the page now sets its title and moves focus; before, it skipped both. This
  looked like a bug, so the change is kept.
- **C2, `_` parameters:** ESLint ignores unused names that start with `_`. The B17c engine removal left deliberate
  `_sc`/`_r` parameters so the functions keep their signatures.
- **C1, ignored rules:** FAST002 (`Annotated` dependencies) is left for C3. PERF401 is ignored on code the golden
  tests compare. source-sim's `sim/s4` ignores SIM300: its autofix would flip comparisons on upper-case SAP columns.
- **C1, possible bug, not fixed:** `HttpClient.raw(log_records=…)` in `apps/api/di/connectors/http.py` ignores
  its flag, so token calls are logged anyway. Left for Phase D. It is marked with a noqa.
- **Process:** twice, a commit swept in another agent's staged `git mv` renames. Both commits were unpushed; I split
  them again with `git reset --soft` and re-staged, which touches only the index. Commits now use
  `git commit -- <paths>`.
- **D2, tokens:** tokens now carry and require `iss`/`aud`, so browsers signed in before this change must sign in
  once more.
  - Outside `DI_ENV=dev` the api refuses to start with the shipped secrets.
  - Not fixed: the webhook subscription matches only on URL, so changing `DI_WEBHOOK_SECRET` needs the subscription
    deleted first.
- **D1:** existing `HTTPException` raises are kept; the handler turns them into the envelope. `ApiError` is
  available but not yet raised anywhere.
- **E1+E4, one commit:** four page files carry hunks from both steps, so they were committed together.
  - Photo tiles: the tile itself is now the button, so a click on its padding also enlarges the photo.
  - Linting: jsx-a11y runs its recommended rule set as errors. The C2 mapping had also switched on
    `control-has-associated-label`, which that set leaves off.
  - Left for later:
    - `draftOf()` (WorkflowPage) and `tiView()` (DecideTabs) still change module state during render.
    - Presenter mode in `api/home.ts` reads localStorage without a guard.
- **F2:**
  - The dev web container still runs as root. Its existing `node_modules` volume is root-owned, so a non-root dev
    user would break dev. Only the runtime images are non-root.
  - `postgres:16-alpine` is not pinned by digest yet.
  - The Node image moves down one patch (24.22.3 → 24.22.2): the newer tag is under two weeks old.
  - CSP: `style-src-attr 'unsafe-inline'` is kept for Workflow Studio's `style="--h:…"` markup.
- **E3:** the plan said one chunk per area; it is one chunk per page.
  - Page ids are not folder names, and `pageFor()` must answer at once. So each area's index maps its ids to
    loaders, and `registry.tsx` wraps each loader in `React.lazy`.
  - The `vendor` chunk uses Vite 8's `rolldownOptions`, which replaces the deprecated `rollupOptions`.
- **D4+D5:** the plan asked for one commit per family; with seven families edited in the same files they went in
  one commit.
  - `can_see_case` stays a plain bool. A new `case_refusal()` gives the reason ("tenant"/"warehouse"), because a
    returned "tenant" string would be truthy.
  - Not merged yet: `di/actions/access.py` keeps its own DELEG/LEVELS/AUTO_TYPES, and a third `_median` remains in
    `screens/access.py`.
- **25954ea:** the commit subject starts with a stray byte-order mark (the PowerShell `Set-Content` encoding).
  Fixing it would need a force-push, so it stays.
- **G2:** the web Dockerfile is split in two.
  - Why: the classic builder (WSL's Docker has no buildx) runs every stage before the target, so one file can't serve
    both the `apps/web` context (dev) and the repo-root context (runtime).
  - `apps/web/Dockerfile` holds dev; `apps/web/Dockerfile.runtime` holds the production image.
  - A Windows-only `doctor.ps1` was not added: Git for Windows ships Git Bash, which runs `doctor.sh`.
- **E2:** the integration pill tabs now move with ← / → like the other tab bars. That is the only behaviour
  change.
  - Not merged: command's `cck`/`spk` tiles, and product's `Panel`/`Prov`/`Photo` (they differ from the case
    versions).
  - The live screenshot comparison was disturbed by other agents' DB resets, so a jsdom test that renders the old
    and new components with the same inputs decides instead.
- **D6:** `routers/actions.py` also held C3's in-progress typing. So the D6 commit got a version built from HEAD
  with only the journal change, and C3's hunks stay for C3's commit.
  - Token calls still write a fetch-log row, but with `HTTP <status>` instead of the response body.
  - The log level comes from the `DI_LOG_LEVEL` environment variable, not from settings.
- **F3:** `?access_token=` on the stream is removed outright, not kept for a release; nothing else used it.
  - The client now does its own reconnect with a backoff, because the browser's retry would reuse an expired
    ticket.
- **F4:** with `SIM_DEMO_FAULTS` on, resetting one system also clears custom faults on that system.
  - Not fixed: `test_adapter_aws_iot` depends on eam data that `test_connectors` deletes. In the full suite's
    alphabetical order it passes; run alone after `test_connectors`, it fails. Worth a follow-up.
- **Verification method from D6 on:** each commit's staged tree is exported and tested on its own (web: tsc, vitest,
  eslint, build; api: ruff and the touched tests in a one-off container against a private api), so other agents'
  uncommitted work can't hide a broken commit.
- **E6:** a network error or 5xx is now retried twice (0.5 s, then 1 s) before the page shows the error, so a real
  outage shows about 1.5 s later. A 4xx refusal still shows at once.
  - Buttons are not yet disabled while an action is pending.
  - Invalidation is still "everything" on every stream event; mapping event kinds to reads is a follow-up (see the
    design note).
- **G3:** when `DEV_POLLING` is unset, file watching uses watchfiles' own default (polling under a WSL2 kernel).
  `DEV_POLLING=1` forces polling and `0` turns it off. A strict "off" default would have broken hot reload on this
  machine's `/mnt/c` mount.
  - The api command now `exec`s uvicorn.
  - Not run on a real Mac or with Git Bash's Docker. The evidence is shellcheck, bash 3.2 syntax checks and WSL runs;
    G5's CI job adds a second platform.
- **PROGRESS.md itself** was untracked until 21 Nov; it is committed on its own.
- **api under load:** with two smoke runs and a pytest run at once, the single dev api process reached 128% CPU and
  its 3 s health check timed out.
  - `/api/health/live` took over 30 s; it does no database work.
  - Re-check at the wave gate. If it is still slow, look for open stream connections exhausting the thread pool.
- **Process:** an agent ran `git stash`/pop on the shared tree at 15:07 UTC. It wiped and then restored other agents'
  edits; the affected agents re-applied theirs. Every agent is now forbidden to use stash, reset or checkout.
