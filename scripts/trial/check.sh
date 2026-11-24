#!/bin/bash
# Clean-install check of a trial package (scripts/trial/build.sh makes one). Unpacks it into a temp dir, removes the
# package's images from Docker so start.sh must load them from images.tar.gz, then runs the customer's steps:
# start, sign in and read screens through the web port, check that only the web port is published, stop and start
# (data kept), reset, and optionally the browser smoke for one account. Always tears down: down -v and the
# temp dir. Runs as its own Compose project (circtrialcheck) on TRIAL_CHECK_PORT (15190); the main stack is untouched.
#   bash scripts/trial/check.sh [dist/circularity-trial-<version>.tar.gz]   (default: the newest in dist/)
# TRIAL_SMOKE=0 skips the browser smoke, 1 requires it (default: run it when host node and Playwright are there).
set -u
set -o pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG=${1:-$(ls -t "$REPO"/dist/circularity-trial-*.tar.gz 2>/dev/null | head -n 1)}
[ -n "$PKG" ] && [ -f "$PKG" ] || { echo "FAIL  no package; run scripts/trial/build.sh first" >&2; exit 1; }

export COMPOSE_PROJECT_NAME=circtrialcheck TRIAL_PORT=${TRIAL_CHECK_PORT:-15190} TRIAL_NO_BROWSER=1
unset COMPOSE_FILE COMPOSE_PROFILES GROQ_API_KEY
WEB="http://localhost:$TRIAL_PORT"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/circtrialcheck.XXXXXX") || exit 1
rc=1
started=0
DIR=""
VERSION=""

cleanup() {
  local status=$rc img
  trap - EXIT INT TERM
  if [ "$started" -eq 1 ]; then
    if [ "$status" -ne 0 ]; then
      (cd "$DIR" && docker compose -f compose.yml ps -a; docker compose -f compose.yml logs --no-color --tail=60)
    fi
    echo "== teardown"
    (cd "$DIR" && docker compose -f compose.yml down -v --remove-orphans >/dev/null 2>&1)
  fi
  rm -rf "$TMP" 2>/dev/null
  if [ "$status" -eq 0 ]; then echo "== trial check: PASSED ($VERSION)"; else echo "== trial check: FAILED ($VERSION)"; fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fail() { echo "FAIL  $*" >&2; exit 1; }
pass() { echo "OK    $*"; }

echo "== unpack $PKG"
tar -xzf "$PKG" -C "$TMP" || fail "tar -xzf"
DIR=$(ls -d "$TMP"/circularity-trial-* | head -n 1)
VERSION=$(cat "$DIR/VERSION")
for f in compose.yml start.sh start.cmd start.ps1 START-HERE.md images.tar.gz data/golden postgres-init guides/users/README.md; do
  [ -e "$DIR/$f" ] || fail "the package has no $f"
done
[ -e "$DIR/.env" ] && fail "the package ships a .env"
grep -rIl --exclude=images.tar.gz -E 'gsk_[A-Za-z0-9]{20,}' "$DIR" && fail "a key-shaped string is in the package"
pass "package $VERSION complete, no .env, no key-shaped strings"

echo "== remove the package's images, so start.sh must load them"
for img in api web source-sim; do docker image rm -f "circularity-trial-$img:$VERSION" >/dev/null 2>&1; done

started=1
(cd "$DIR" && bash start.sh) || fail "start.sh"
pass "start.sh: ready"
[ -f "$DIR/.env" ] || fail "start.sh wrote no .env"
grep -q '^DI_SECRET_KEY=.\{44\}$' "$DIR/.env" || fail ".env has no 44-character Fernet key"

echo "== the customer's view through the web port"
code=$(curl -sS -m 30 -o /dev/null -w '%{http_code}' "$WEB/") || fail "web $WEB/ unreachable"
[ "$code" = 200 ] || fail "web $WEB/ answered $code"
pass "web / 200"
login=$(curl -fsS -m 30 -X POST "$WEB/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"planner.a","password":"anything"}') || fail "sign in"
token=$(printf '%s' "$login" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
[ -n "$token" ] || fail "no access_token"
pass "signed in as planner.a"
screen=$(curl -fsS -m 60 -H "Authorization: Bearer $token" "$WEB/api/screens/case/RT-1048") || fail "case screen"
case $screen in *'"RT-1048"'*) ;; *) fail "the case screen does not name RT-1048" ;; esac
pass "RT-1048 case screen (${#screen} bytes)"
curl -fsS -m 10 "$WEB/api/health" | grep -q '"status":"ok"' || fail "/api/health not ok"
pass "/api/health ok"
published=$(cd "$DIR" && docker compose -f compose.yml ps --format json | grep -v '"Service":"web"' | grep -c '"PublishedPort":[1-9]')
[ "$published" = 0 ] || fail "a service other than web publishes a port"
pass "only the web port is published"

echo "== stop and start keep the data"
before=$(cd "$DIR" && docker compose -f compose.yml exec -T postgres sh -c 'psql -U circ -d di -tAc "select count(*) from case_record"' 2>/dev/null | tr -d '[:space:]')
(cd "$DIR" && bash stop.sh) || fail "stop.sh"
(cd "$DIR" && bash start.sh) || fail "start.sh after stop"
after=$(cd "$DIR" && docker compose -f compose.yml exec -T postgres sh -c 'psql -U circ -d di -tAc "select count(*) from case_record"' 2>/dev/null | tr -d '[:space:]')
[ -n "$before" ] && [ "$before" -gt 0 ] 2>/dev/null && [ "$after" = "$before" ] || fail "the cases changed over stop/start ($before -> $after)"
pass "stop/start kept the data ($after cases)"

echo "== reset"
(cd "$DIR" && bash reset.sh --yes) || fail "reset.sh"
code=$(curl -sS -m 30 -o /dev/null -w '%{http_code}' "$WEB/") || fail "web after reset"
[ "$code" = 200 ] || fail "web after reset answered $code"
pass "reset.sh: ready again"

echo "== browser smoke (admin)"
smoke=${TRIAL_SMOKE:-auto}
if [ "$smoke" = 0 ]; then
  echo "SKIP  browser smoke (TRIAL_SMOKE=0)"
elif command -v node >/dev/null 2>&1 && [ -d "$REPO/frontend/node_modules/@playwright/test" ]; then
  (cd "$REPO/frontend" && node scripts/smoke-pages.mjs "$WEB" admin) || fail "smoke-pages.mjs $WEB admin"
  pass "smoke-pages.mjs admin"
elif [ "$smoke" = 1 ]; then
  fail "browser smoke: needs host node and frontend/node_modules/@playwright/test"
else
  echo "SKIP  browser smoke: no host node/Playwright here (run: node frontend/scripts/smoke-pages.mjs $WEB admin)"
fi

rc=0
