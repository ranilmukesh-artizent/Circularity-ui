# Plan 1b: best-practices refactor Implementation Plan

> **For agentic workers:** run through `scripts/dev/loop.ps1` (see `loop.md`), one step per iteration. Steps use
> checkbox (`- [ ]`) syntax. Each step names the findings it closes (ids below) and its own tests.

Gate: tests/test_screens_reference.py tests/test_actions.py tests/test_auth.py

**Goal:** bring the codebase to full-stack best practices before the feature plans (02–05), with no change to
behaviour or golden parity.

**Architecture:** six phases. A makes the gates trustworthy and fixes real bugs; B is the layout and naming the user
asked for; C adds the tooling that enforces the rest; D and E restructure backend and frontend behind that tooling;
F hardens containers and security. Each step is one commit; the full api + source-sim suites and the 11-account smoke
run at the end of each phase.

**Spec:** the three audits of 20 Nov 2026 (findings index at the end; ids F = backend, W = web, T/O/S/R/X/D = infra
and source-sim). User decisions: audit then refactor (not a rewrite); consistent file names; `index.html` out of the
repo root.

## Global Constraints

- No behaviour change: golden parity tests, the smoke run (11 accounts, same route counts) and `smoke-rt1048.mjs`
  stay green. Visible text and DOM/class names stay identical (the demo's stylesheet depends on them).
- Do not put pydantic `response_model` on golden-compared endpoints (coercion breaks parity, F6).
- Naming: React component modules `PascalCase.tsx`, route components `…Page.tsx`, hooks `useX.ts`, other TS modules
  `camelCase.ts`, Python `snake_case.py`, scripts and docs `kebab-case`, folders lower-case; root `README.md`,
  `AGENTS.md`, `CLAUDE.md` keep capitals; `scripts/golden/*.mjs` keep snake_case (they mirror fixture names).
- Renames are `git mv` + import/link fixes only, in their own commits, with nothing else changed.
- Dependency bumps only within the same major version unless a step says otherwise.

## Review Focus

1. A rename leaves a stale link or import → `tsc`, a markdown link check over `docs/`, `AGENTS.md`, `README.md`, and
   `grep` for the old name must all be clean.
2. Moving `index.html` changes a golden byte → regenerate every golden file and compare parsed JSON (testing.md).
3. A lint autofix changes behaviour (e.g. ruff `SIM`/`C4` rewrites, ESLint fixes) → autofix only safe rules; review
   the diff; full suite.
4. The source-sim test database split leaves api connector tests pointing at the wrong DB → they must still use the
   live sim (`localhost:8100`); only source-sim's own tests move.
5. Error-envelope change breaks the web client → `client.ts` error parsing tests cover `{ok:false,error}`, FastAPI
   422 and plain 500.

---

## Phase A: trustworthy gates and real bugs

- [x] **A1** dev scripts return pytest/tsc exit codes (`set -euo pipefail` in `lib.sh`, `PIPESTATUS`) [T4]. Test: a
  failing test file makes `api-test.sh` exit non-zero; `web-check.sh` exits non-zero on a type error.
- [ ] **A2** worker re-subscribes to source-sim webhooks in `periodic()` [O3]. Test: delete the subscription; within
  one periodic tick it is back (unit test calls `periodic()` with the sim subscription removed).
- [ ] **A3** api safety: `/api/health` returns no exception text [F12]; blocking DB calls inside `async def` handlers
  (`connectors/webhook.py`, `stream.py` principal) run in a thread [F10]; `integration.conflicts` `status` is a
  `Literal` (422 not 500) and `_update` asserts allowed columns [F15]. Tests per item.
- [ ] **A4** web client: "Try again" really retries (`retryFailed()` marks errored entries stale) [W-01];
  `postAction` turns a network failure into `{ok:false,error:{code:'network'}}` [W-02a]. Tests in `client.test.ts`.
- [ ] **A5** security bumps within major: vite 5.4.21, react-router-dom 6.30.6, vitest 2.1.9, @playwright/test 1.65.x
  [W-12]; compose publishes ports on `127.0.0.1` (overridable `BIND_ADDR`) [O4]. Gate: `npm audit --audit-level=high`
  clean, web checks, smoke.
- [ ] **A6** source-sim tests get their own database `sources_test` (set before `sim` is imported; conftest creates
  it), delete only their own subscriptions, `deliver` tolerates a vanished outbox row [T3]. Gate: source-sim suite 5×
  in a row green with the live service running; remove the "known flaky" notes from testing.md.

## Phase B: layout and naming (user request)

- [ ] **B1** move the demo: `index.html` → `fixtures/demo/index.html` (`git mv`). Update `extract-styles.mjs`,
  `golden-sandbox.mjs`, `dump-assets.mjs`, the compose mount and `LEGACY_HTML`, CI, `assets/products` path if needed,
  every doc. Gate: regenerate every golden file and `assets.gen.ts` → no change (parsed-JSON compare); web build.
- [ ] **B2** docs to kebab-case (the old upper-case names are in the git history): `docs/backend-steps.md`,
  `docs/plan-fullstack-poc.md`, `apps/web/porting.md`, the three `docs/reference/*` files →
  `cvl-user-journey-v1.1.pptx`, `ifs-process-inventory-and-di-pipeline-fit.pdf`,
  `agent-first-workbench-pr.md`; fold the README under `apps/` into `README.md` [D1]. Update every link and the many
  code docstrings that cite the backend steps doc. Gate: grep for old names → none; link check.
- [ ] **B3** web renames (table in the findings index, "Naming A"): `src/api.ts` → `src/api/health.ts`,
  `api/hooks.ts` → `api/useBackend.ts`, lower-case component modules → PascalCase, vague names → specific ones,
  page code out of `integration/index.tsx` and `product/index.tsx`, `workflows/graph.ts` → `src/api/workflowGraph.ts`,
  `audit/csv.ts` → `src/lib/csv.ts`, `e2e/shot.mjs` → `scripts/screenshot.mjs`. Do after C2 (dead code gone). Add
  `eslint-plugin-check-file` rules. Gate: tsc, vitest, smoke.
- [ ] **B4** line endings and editor config: `.gitattributes` `* text=auto eol=lf` with binaries marked, `.editorconfig`,
  `git add --renormalize` [X4]. Gate: golden regeneration unchanged; full suite.

## Phase C: tooling that enforces the rest

- [ ] **C1** Python lint: one root `ruff.toml` (both services `extend` it), add `BLE,S,ASYNC,RUF,SIM,C4,PT,DTZ,PERF,FAST,ARG`
  with per-file ignores for tests; fix or justify first-run hits; `ruff format` once (own commit, listed in
  `.git-blame-ignore-revs`); bump ruff [F21, X2].
- [ ] **C2** web lint: ESLint flat config (typescript-eslint recommended, react-hooks with `rules-of-hooks` as error,
  jsx-a11y), `npm run lint`; fix the 7 suppressed `exhaustive-deps` sites properly; knip removes the 15 dead exports;
  refresh stale docstrings [W-09, W-10, W-23].
- [ ] **C3** typing: mypy config, strict for core modules (config, db, auth, jobs, worker, state, clock, golden,
  stream, connectors/base, actions/pipeline, actions/registry), `check_untyped_defs` elsewhere; `ctx: CallContext`
  everywhere; `CurrentPrincipal`/`DbSession` `Annotated` aliases [F6]. Web: split tsconfig (app/node), add
  `noImplicitReturns`, `noImplicitOverride`; one typed `Reference` interface for `ref()` [W-08, W-07a].
- [ ] **C4** locked dependencies: `uv pip compile --generate-hashes` per service from the currently resolved versions,
  one shared constraints file, source-sim dev requirements split; `engines` + `.nvmrc` for Node 24 [X1, F22, D1].
- [ ] **C5** CI that tests the app: bring the compose stack up (`up --wait` after F1) and run the api suite in the
  api container; source-sim suite; vitest; ruff check + format check; mypy; ESLint; knip; `pip-audit`; `npm audit`;
  gitleaks; `permissions: contents: read`; concurrency group; SHA-pinned actions; pytest markers `parity`, `sim`,
  `slow`, `milestone`, `live` with `--strict-markers`; Dependabot for pip, npm, docker, actions; pre-commit with
  gitleaks and ruff [T1, T2, F19, W-11, S2, X3].

## Phase D: backend structure

- [ ] **D1** one error envelope: `di/errors.py` `ApiError`; handlers for it, `HTTPException`, validation errors and
  unhandled exceptions, all emitting `{ok:false,error:{code,message}}`; update the 21 tests that read `["detail"]`
  and `client.ts` parsing [F4].
- [ ] **D2** settings and auth hardening: `DI_ENV`; refuse default `jwt_secret`/`webhook_secret` outside dev; secrets
  as `SecretStr`; `Literal` settings; JWT `iss`/`aud` and required claims; source-sim subscription secret required;
  `.env.example` and compose pass-through [F7, F14, S1].
- [ ] **D3** table metadata for all ~19 tables in `di/models.py` (Core `Table`s matching the migrations); tests:
  `alembic check` clean and downgrade→upgrade round trip [F16]. Prerequisite of plan 03.
- [ ] **D4** consolidate duplicated helpers, one family per commit: account context; visible cases/rows;
  `can_see_case` used by auth, screens, stream, Ask (closes the warehouse gap in Ask suggestions) [F13]; provenance
  (`PMAP`: the Audit and Case copies differ, `str` vs `js_text`; pick what the golden files show, test both pages);
  expected returns; `cc_scope`/`aome_items`; shared constants [F2]. Screen golden tests per commit.
- [ ] **D5** dependency direction: move cross-imported domain functions from `di/screens/*` into `di/reads/`; screens
  become leaves; import-linter contracts in CI [F1].
- [ ] **D6** tests and small performance: shared `client`/login fixtures and golden helpers in `conftest.py`;
  `--durations=50` recorded in testing.md; the journal query filters in SQL before LIMIT [F20 steps 1–3, F17];
  one logging config for api and worker [F5].

Deferred with a reason: splitting the large screen modules [F3] and a request-scoped cache [F18] after D4–D5;
pytest-xdist with per-worker databases [F20 step 4] with plan 04 (env-before-import).

## Phase E: frontend structure

- [ ] **E1** render purity and session-scoped state: no in-place sorts of cached arrays, `enterCase` out of render,
  module-level page state reset on sign-in/out [W-04, W-05].
- [ ] **E2** one UI kit: the duplicated primitives (icon tile, status pill, KPI, segmented control, panel, spark, delta,
  ring, timeline, vendor logo, JSON view) move to `src/ui/kit/` one file each; area-only pieces get specific names
  ("Naming B" in the index); `Raw` and HTML-string builders replaced by components [W-16, W-15]. Gate: smoke plus
  screenshot comparison on the smoke routes.
- [ ] **E3** lazy-load each area (non-eager glob + `React.lazy`) [W-18]. Gate: bundle has per-area chunks; smoke.
- [ ] **E4** accessibility: focus trap and focus return in `Modal`/`Drawer` (`role="dialog"`, `aria-modal`), Escape
  through the overlay stack, keyboard access for clickable rows and images [W-20].
- [ ] **E5** tests: unit tests for `workflowGraph`, drafts, workflow actions, csv, case route resolution, view state;
  coverage with a floor; one render test per area against recorded answers [W-21].
- [ ] **E6** `useAction()` helper (pending state, refusal toasts with the demo's texts) and migrate call sites [W-02b];
  then back the read cache with TanStack Query (eviction, retry, scoped invalidation) behind the same facade; design
  note first [W-03].

## Phase F: containers and security

- [ ] **F1** healthchecks for source-sim, worker and web; health-gated `depends_on` [O2].
- [ ] **F2** images: pinned base images by digest, multi-stage `dev`/`runtime`, non-root runtime user, `npm ci` only,
  `.dockerignore` excludes `.env*`/`.git`/tests; a production web image serving `dist` with a CSP [O1, F23, W-13, W-14 CSP].
- [ ] **F3** live stream without the token in the URL: a short-lived single-purpose stream ticket (`aud="stream"`),
  token redacted from logs [F9, W-14].
- [ ] **F4** source-sim robustness: fan-out marks unmatched events delivered [R2]; per-system reset keeps other
  systems' faults [R3]. Webhook delivery outside the transaction [R1] and ASGI fault middleware [R4] go with plan 04.

## Phase G: runs on any machine (user request, 20 Nov 2026)

Target: any machine with Git and Docker (Docker Desktop on Windows or macOS, Intel or Apple Silicon; Docker Engine with
Compose v2 on Linux). The host needs no Node or Python to run, test or build the app, and nothing depends on WSL or a
user's paths.

Audit findings (20 Nov 2026):
- [G-a] The docs assume Windows + WSL.
- [G-b] The web runtime image needs host-generated `legacy.gen.css` and product photos, so it needs Node on the host.
- [G-c] `scripts/dev` uses host `flock` and GNU `timeout`, which macOS doesn't have.
- [G-d] Host ports other than postgres's are fixed.
- [G-e] File watching on Windows bind mounts needs polling.
- [G-f] Only `fixtures/` and `*.sh` are forced to LF (B4).
- [G-g] Nothing has proved an arm64 build.

Already fine: no `env_file` (`.env` optional), index digests are multi-arch, and the npm lock carries the linux
arm64/x64 musl native packages.

- [x] **G1** one quick start for every OS [G-a].
  - README: prerequisites, `docker compose up -d --build`, open :5173. WSL becomes one Windows option among others.
  - `scripts/doctor.sh` checks Docker, Compose v2, free ports, memory and git line-ending settings.
  - AGENTS.md "Run" generalised; CLAUDE.md keeps this machine's WSL notes.
- [x] **G2** self-contained images [G-b]. The web runtime stage generates the styles and photos itself (build context
  = repo root, so `fixtures/demo` is in the context). `docker compose -f docker-compose.yml -f docker-compose.prod.yml
  up --build` works on a fresh clone with no host Node.
- [ ] **G3** portable dev scripts [G-c, G-d, G-e].
  - The test lock and timeout run inside the api container, so they don't depend on host tools; the scripts run in
    plain bash on Linux, macOS and Git Bash.
  - Host ports come from env (`API_PORT`, `WEB_PORT`, `SIM_PORT`, `SFTP_PORT`, `POSTGRES_PORT`).
  - `DEV_POLLING=1` switches uvicorn (watchfiles) and Vite to polling.
  - Run it alone; it changes the lock every agent uses.
- [ ] **G4** = B4 line endings [G-f].
- [ ] **G5** proof [G-g].
  - CI gains an arm64 job (`ubuntu-24.04-arm`): `compose up --wait`, health checks and a short smoke.
  - A fresh-clone test: clone into a temp dir with another project name and ports, `up --wait`, sign in and smoke
    one account, `down -v`. It is documented as `scripts/dev/fresh-clone.sh`.

Deferred to B18's security review: login throttling and Ask rate limits [F11], timestamped webhook signatures [S3],
the POC's any-password sign-in.

---

## Findings index (20 Nov 2026 audits)

Backend: F1 inverted layering · F2 duplicated helpers (provenance copies diverge) · F3 large screen modules · F4 four
error shapes · F5 no api logging config · F6 not mypy-ready · F7 default signing secrets · F8 import-time side effects ·
F9 token in stream URL · F10 blocking I/O in async handlers · F11 no throttling · F12 health leaks exception text ·
F13 inconsistent object-level checks · F14 JWT claims · F15 unguarded f-string SQL · F16 ORM metadata covers 1 of ~19
tables · F17 journal filters after LIMIT · F18 recompute per request · F19 CI cannot run the suite · F20 monolithic
slow suite · F21 minimal ruff · F22 no lock · F23 Dockerfile gaps.

Web: W-01 retry never retries · W-02 actions/network errors not central · W-03 home-grown Suspense cache · W-04 side
effects in render · W-05 page state survives sign-out · W-07 server data cast not typed · W-08 stricter tsconfig ·
W-09 no linter · W-10 dead code · W-11 CI skips tests · W-12 10 vulnerable packages · W-13 dev server as root ·
W-14 token in URL, no CSP · W-15 HTML strings · W-16 cross-area imports, duplicated kit · W-17 large files (leave) ·
W-18 one 1.05 MB chunk · W-20 dialog focus, mouse-only rows · W-21 no page tests · W-22 keep demo CSS · W-23 stale docs.

Infra and source-sim: T1 CI api suite · T2 CI checks · T3 sim tests share live DB and loops · T4 scripts exit 0 ·
O1 images · O2 healthchecks · O3 subscription never retried · O4 ports on all interfaces · S1 dev secrets · S2 no
secret scanning · S3 replayable webhooks · R1 HTTP inside a transaction · R2 fan-out starvation · R3 reset wipes
faults · R4 BaseHTTPMiddleware · X1 no hash lock · X2 no type checker, duplicated ruff · X3 no update policy ·
X4 line endings · D1 stale READMEs.

Naming A (web, mechanical): `src/api.ts`→`api/health.ts`; `api/hooks.ts`→`api/useBackend.ts`;
`api/no-engine.test.ts`→`api/noEngine.test.ts`; `access/requests.tsx`→`AccessRequests.tsx`;
`analytics/charts.tsx`→`AnalyticsCharts.tsx`; `command/charts.tsx`→`CommandCharts.tsx`;
`command/sections.tsx`→`CommandPanels.tsx`; `case/tabs/{decide,early,execute}.tsx`→`{Decide,Early,Execute}Tabs.tsx`;
`case/drawers.tsx`→`CaseDrawers.tsx`; `product/chips.tsx`→`AssetChips.tsx`; `product/assetParts.tsx`→`AssetPanels.tsx`;
`product/ReturnedAssets.tsx`→`ReturnedAssetsPage.tsx`; `workflows/Page.tsx`→`WorkflowPage.tsx`;
`workflows/List.tsx`→`WorkflowList.tsx`; `case/Dialogs.tsx`→`CaseModals.tsx`; `workflows/Modals.tsx`→`WorkflowModals.tsx`;
`integration/Tables.tsx`→`SourceTables.tsx`; `case/Overview.tsx`→`CaseOverview.tsx`;
`integration/Overview.tsx`→`FabricOverview.tsx`; page code to `integration/IntegrationPage.tsx` and
`product/ProductPage.tsx`; `workflows/ops.ts`→`workflowActions.ts`; `workflows/draft.ts`→`draftStore.ts`.

Naming B (with E2): `home/kit.tsx`, `workflows/kit.tsx`, `integration/ui.tsx`, `case/kit.tsx` split into `src/ui/kit/*`
plus area files (`HomeHeader.tsx`, `WorkflowMenus.tsx`, `FabricContext.tsx`, `ConnectionTests.tsx`, `SourceMenu.tsx`,
`CaseBlocks.tsx`); `case/ui.tsx` → `CaseContext.tsx` + `caseActions.ts`.
