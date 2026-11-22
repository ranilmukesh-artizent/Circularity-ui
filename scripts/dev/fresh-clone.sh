#!/bin/bash
# Fresh-clone test (plan 01b, step G5): proves the COMMITTED HEAD of this repo comes up from nothing on this machine.
# Clones HEAD into a temp dir (uncommitted changes are not included), starts the whole stack there as a separate
# Compose project (`circfresh`) on its own host ports, waits until every service is healthy, runs scripts/doctor.sh in
# the clone, signs in through the web port (the Vite dev proxy, or nginx with --prod) and reads a screen, and runs
# the browser smoke for one account when host Node and Playwright are there. It ALWAYS tears down: `down -v`, the
# images it built, the temp dir. Exits non-zero on any failure. It does not touch the main stack (other project name,
# ports, volumes and image names); it does share Docker's build cache.
#   bash scripts/dev/fresh-clone.sh           # dev images (docker-compose.yml)
#   bash scripts/dev/fresh-clone.sh --prod    # runtime images (docker-compose.prod.yml layered on)
# Host ports: FRESH_WEB_PORT 15173, FRESH_API_PORT 18000, FRESH_SIM_PORT 18100, FRESH_SFTP_PORT 12222,
# FRESH_POSTGRES_PORT 15432. The temp dir goes under TMPDIR (default /tmp); Docker must be able to bind-mount it.
# FRESH_SMOKE=0 skips the browser smoke, FRESH_SMOKE=1 fails when it cannot run (default: run it if possible).
# Plain bash 3.2+ on Linux, macOS and Git Bash; the host needs git, docker (Compose v2, 2.24+ for --prod) and curl.
set -u
set -o pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT=circfresh
prod=0
for arg in "$@"; do
  case $arg in
    --prod) prod=1 ;;
    -h | --help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (use --prod or --help)" >&2; exit 2 ;;
  esac
done

mode=dev
[ "$prod" -eq 1 ] && mode=prod

for tool in git docker curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "FAIL  $tool not found on PATH" >&2; exit 1; }
done

# Isolate the clone's Compose project from the caller's environment and from this checkout's .env (the clone has no
# .env: it is git-ignored). No language-model key: Ask uses its rule-based fallback.
unset COMPOSE_FILE COMPOSE_PROFILES COMPOSE_PATH_SEPARATOR GROQ_API_KEY GROQ_MODEL DI_JWT_SECRET DI_WEBHOOK_SECRET
export COMPOSE_PROJECT_NAME=$PROJECT
export WEB_PORT=${FRESH_WEB_PORT:-15173} API_PORT=${FRESH_API_PORT:-18000} SIM_PORT=${FRESH_SIM_PORT:-18100}
export SFTP_PORT=${FRESH_SFTP_PORT:-12222} POSTGRES_PORT=${FRESH_POSTGRES_PORT:-15432}
export BIND_ADDR=127.0.0.1 DI_ENV=dev ASK_PROVIDER=none DEV_POLLING=
WEB="http://localhost:$WEB_PORT" API="http://localhost:$API_PORT" SIM="http://localhost:$SIM_PORT"

# git refuses a repository owned by another user ("dubious ownership"), e.g. a Windows checkout read from WSL as root;
# trusting it for these read-only commands only (command-line config) is enough.
g() { git -c safe.directory="$REPO" -C "$REPO" "$@"; }
sha=$(g rev-parse --short HEAD) || { echo "FAIL  $REPO is not a git checkout" >&2; exit 1; }

TMP=$(mktemp -d "${TMPDIR:-/tmp}/circfresh.XXXXXX") || exit 1
CLONE="$TMP/repo"
FILES=(-f docker-compose.yml)
started=0
rc=1

compose() { (cd "$CLONE" && docker compose "${FILES[@]}" "$@"); }

cleanup() {
  local status=$rc img
  trap - EXIT INT TERM
  if [ "$started" -eq 1 ]; then
    if [ "$status" -ne 0 ]; then
      echo "== stack state and logs (failure)"
      compose ps -a
      compose logs --no-color --tail=80
    fi
    echo "== teardown"
    # --rmi local: the images Compose named after the project (dev); the --prod images carry our own tags
    compose down -v --remove-orphans --rmi local >/dev/null 2>&1 || echo "WARN  docker compose down failed" >&2
    if [ "$prod" -eq 1 ]; then
      for img in source-sim api worker web; do docker image rm -f "$PROJECT-$img:runtime" >/dev/null 2>&1; done
    fi
  fi
  # Files the dev containers wrote into the bind mounts can belong to root: remove those through a container.
  if ! rm -rf "$TMP" 2>/dev/null && [ -d "$TMP" ]; then
    img=$(sed -n 's/^ *image: *\(postgres[^ #]*\).*/\1/p' "$REPO/docker-compose.yml" | head -n 1)
    docker run --rm --entrypoint sh -v "$TMP:/t" "${img:-postgres:16-alpine}" -c 'rm -rf /t/repo /t/* 2>/dev/null; true' >/dev/null 2>&1
    rm -rf "$TMP" 2>/dev/null || echo "WARN  could not remove $TMP" >&2
  fi
  if [ "$status" -eq 0 ]; then echo "== fresh-clone ($mode): PASSED (HEAD $sha)"; else echo "== fresh-clone ($mode): FAILED (HEAD $sha)"; fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fail() { echo "FAIL  $*" >&2; exit 1; }  # rc stays 1; the EXIT trap tears down
pass() { echo "OK    $*"; }

echo "== clone HEAD $sha of $REPO into $CLONE (uncommitted changes are not included)"
git -c safe.directory="$REPO" -c safe.directory="$REPO/.git" clone --quiet --no-local "$REPO" "$CLONE" \
  || fail "git clone"
[ "$(git -C "$CLONE" rev-parse --short HEAD)" = "$sha" ] || fail "the clone is not at HEAD $sha"

if [ "$prod" -eq 1 ]; then
  # docker-compose.prod.yml names its images circularity-ui-*:runtime; give the clone's its own so the main
  # checkout's runtime images are not replaced (and the teardown can remove exactly these)
  cat >"$TMP/fresh-images.yml" <<EOF
services:
  source-sim: { image: "$PROJECT-source-sim:runtime" }
  api: { image: "$PROJECT-api:runtime" }
  worker: { image: "$PROJECT-worker:runtime" }
  web: { image: "$PROJECT-web:runtime" }
EOF
  FILES=(-f docker-compose.yml -f docker-compose.prod.yml -f "$TMP/fresh-images.yml")
fi

echo "== project $PROJECT ($mode): web $WEB_PORT, api $API_PORT, source-sim $SIM_PORT, sftp $SFTP_PORT, postgres $POSTGRES_PORT"
compose down -v --remove-orphans >/dev/null 2>&1  # leftovers of an interrupted run
started=1
t0=$SECONDS
compose up -d --build --wait --wait-timeout 900 || fail "docker compose up --wait (build or healthchecks)"
pass "stack up and healthy after $((SECONDS - t0))s: $(compose ps --format '{{.Service}}' | sort | tr '\n' ' ')"

echo "== health"
curl -fsS -m 10 "$API/api/health" | grep -q '"status":"ok"' || fail "api $API/api/health is not ok"
pass "api /api/health ok (database and source-sim reachable)"
curl -fsS -m 10 -o /dev/null "$SIM/health" || fail "source-sim $SIM/health"
pass "source-sim /health"
code=$(curl -sS -m 30 -o /dev/null -w '%{http_code}' "$WEB/") || fail "web $WEB/ unreachable"
[ "$code" = 200 ] || fail "web $WEB/ answered $code"
pass "web / 200"

echo "== doctor (in the clone)"
(cd "$CLONE" && bash scripts/doctor.sh) || fail "scripts/doctor.sh"

echo "== sign in and read a screen through the web port"
login=$(curl -fsS -m 30 -X POST "$WEB/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"demo"}') || fail "POST $WEB/api/auth/login"
token=$(printf '%s' "$login" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
[ -n "$token" ] || fail "no access_token in the sign-in response"
pass "signed in as admin"
screen=$(curl -fsS -m 60 -H "Authorization: Bearer $token" "$WEB/api/screens/case/RT-1048") \
  || fail "GET $WEB/api/screens/case/RT-1048"
case $screen in *'"RT-1048"'*) ;; *) fail "/api/screens/case/RT-1048 does not name RT-1048" ;; esac
pass "/api/screens/case/RT-1048 (the hero case, seeded): ${#screen} bytes"
code=$(curl -sS -m 30 -o /dev/null -w '%{http_code}' "$WEB/api/screens/case/RT-1048")
[ "$code" = 401 ] || fail "/api/screens/case/RT-1048 without a token answered $code, expected 401"
pass "/api/screens/case/RT-1048 without a token: 401"

echo "== browser smoke (admin)"
# The smoke runs from this checkout's frontend (the clone has no host node_modules) against the clone's web port.
smoke=${FRESH_SMOKE:-auto}
if [ "$smoke" = 0 ]; then
  echo "SKIP  browser smoke (FRESH_SMOKE=0)"
elif command -v node >/dev/null 2>&1 && [ -d "$REPO/frontend/node_modules/@playwright/test" ]; then
  (cd "$REPO/frontend" && node scripts/smoke-pages.mjs "$WEB" admin) || fail "smoke-pages.mjs $WEB admin"
  pass "smoke-pages.mjs admin"
elif [ "$smoke" = 1 ]; then
  fail "browser smoke: needs node on PATH and frontend/node_modules/@playwright/test (npm ci in frontend) and Chrome"
else
  echo "SKIP  browser smoke: no host node or no frontend/node_modules/@playwright/test here (npm ci in frontend; it uses the installed Chrome)"
fi

rc=0
