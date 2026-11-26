# Plan 9 final proof (P9-13.12)

Run on 27 Nov 2026 on Windows 11, Docker Desktop, Git Bash, host Node 26.12.1 (the repo asks for 24; the smoke ran).
Base: `66066b0c` on `feature/plan-09-recover`; the runs below are on `a088f6dd` (base plus one script fix, below). Each
script used its own compose project; the main stack was not touched.

## Fix found while running

`scripts/trial/build.sh`, zip step: Git Bash rewrote `docker run ... -w /d` to `D:/` ("the working directory 'D:/' is
invalid"). Fixed in `a088f6dd` with `MSYS_NO_PATHCONV=1` on that one command (other systems ignore it; the rest of the
script is unchanged).

## Results

| # | Command | Result |
|---|---|---|
| 1 | `bash scripts/dev/story-matrix.sh` (all phases) | pending writer 44 |
| 2a | `FRESH_SMOKE=1 bash scripts/dev/fresh-clone.sh` (dev images, project `circfresh`) | `fresh-clone (dev): PASSED (HEAD a088f6dd)`; fresh database ran every migration; `/api/screens/case/RT-1048` 200 (20526 bytes), 401 without a token; `admin: 70 routes, 0 failing`, `OK smoke-pages.mjs admin` |
| 2b | `bash scripts/dev/fresh-clone.sh --prod` (reported by the lead's 13.12 agent earlier on 27 Nov, not rerun here) | `fresh-clone (prod): PASSED (HEAD 66066b0c)`; stack healthy after 168 s; doctor, health, admin sign-in and RT-1048 OK (`FRESH_SMOKE=0`). The dev run also passed on `e15cd015`. |
| 3a | `bash scripts/trial/build.sh` | built `2026.11.26-a088f6dd`: `images.tar.gz` 404M, `.tar.gz` 407M, `.zip` 407M, no `.env` in the package |
| 3b | `bash scripts/trial/check.sh dist/circularity-trial-2026.11.26-a088f6dd.tar.gz` (project `circtrialcheck`, port 15190) | `trial check: PASSED (2026.11.26-a088f6dd)`: start, web 200, sign-in, RT-1048 case screen, `/api/health`, only the web port published, stop/start kept 128 cases, reset. Its own browser smoke was skipped (no host node in its environment); the fresh-clone smoke above covers it. |

## Image list

`trial/compose.yml` services: `postgres` (postgres:16-alpine), `source-sim`, `api`, `worker` (same image as api), `web`.
The package saves four images: `circularity-trial-api`, `-web`, `-source-sim`, and `postgres:16-alpine`. The dev
`docker-compose.yml` has the same five services plus `otel`, which the trial does not ship. No new container; no change
to `trial/compose.yml` was needed (OIDC stays off).

## Cleanup

The `circfresh` and `circtrialcheck` containers, networks and volumes were removed by the scripts; the three
`circularity-trial-*:2026.11.26-a088f6dd` images were deleted. `dist/` stays (git-ignored).

## Open

- Story matrix: pending writer 44.
- Re-run build and check if P9-13.13 changes `docs/guides/users/` (the package copies them).
