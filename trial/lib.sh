#!/bin/bash
# Shared by start.sh, stop.sh, reset.sh and status.sh (macOS, Linux, WSL). Plain bash 3.2+; needs only Docker.
set -u
set -o pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1
VERSION="$(cat "$HERE/VERSION" 2>/dev/null || echo dev)"
IMAGES=(circularity-trial-api circularity-trial-web circularity-trial-source-sim)

fail() { echo "ERROR  $*" >&2; exit 1; }
say() { echo "==  $*"; }

need_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install Docker Desktop (Windows, macOS) or Docker Engine (Linux), then run this again."
  docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Start Docker Desktop (or the Docker service), wait until it is ready, then run this again."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is missing ('docker compose'). Update Docker Desktop, or install the compose plugin."
}

# The images ship in images.tar.gz; load them once (docker load reads the gzip itself).
load_images() {
  local missing=0 img
  for img in "${IMAGES[@]}"; do
    docker image inspect "$img:$VERSION" >/dev/null 2>&1 || missing=1
  done
  docker image inspect postgres:16-alpine >/dev/null 2>&1 || missing=1
  [ "$missing" -eq 0 ] && return 0
  [ -f "$HERE/images.tar.gz" ] || fail "images.tar.gz is missing from $HERE. Unpack the whole trial package again."
  say "Loading the app's images (first start only, about a minute)"
  docker load -i "$HERE/images.tar.gz" >/dev/null || fail "docker load failed. Is there enough free disk space (about 3 GB)?"
}

# base64url without padding, n random bytes
rand() { head -c "$1" /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }

# .env: generated secrets and the port, written once and kept (a reset keeps it too).
write_env() {
  [ -f "$HERE/.env" ] && return 0
  local fernet
  fernet="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n')"
  umask 077
  cat >"$HERE/.env" <<EOF
# Written by the start script on first start. Keep it private: it holds this installation's secrets.
# TRIAL_PORT: the port the app opens on (http://localhost:TRIAL_PORT). Change it if 5173 is taken, then start again.
TRIAL_PORT=${TRIAL_PORT:-5173}
BIND_ADDR=127.0.0.1
POSTGRES_PASSWORD=$(rand 24)
DI_JWT_SECRET=$(rand 48)
DI_WEBHOOK_SECRET=$(rand 48)
DI_SECRET_KEY=$fernet
# Optional: a free key from console.groq.com makes Ask Circularity answer with a language model.
GROQ_API_KEY=
EOF
  say "Wrote .env with new secrets for this installation"
}

port() { sed -n 's/^TRIAL_PORT=\([0-9]*\).*/\1/p' "$HERE/.env" 2>/dev/null | head -n 1; }

compose() { docker compose --project-directory "$HERE" -f "$HERE/compose.yml" "$@"; }

wait_ready() {
  say "Starting (the first start takes 1 to 3 minutes while the demo data is loaded)"
  compose up -d --wait --wait-timeout 900 || {
    compose ps -a
    fail "The app did not become ready. See the logs with: docker compose -f compose.yml logs --tail=80"
  }
  local url="http://localhost:$(port)"
  echo
  echo "Circularity is running:  $url"
  echo "Sign in with any of: admin, exec, planner.a, planner.b, planner.c, approver, engineer, finance, developer,"
  echo "warehouse1, warehouse2 (any password). START-HERE.md has a short tour."
}
