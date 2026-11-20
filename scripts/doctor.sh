#!/usr/bin/env bash
# Checks that this machine can run the stack (`docker compose up -d --build`). Read-only: it starts, stops and changes
# nothing. Runs in plain bash on Linux, macOS, WSL and Git Bash on Windows:
#   bash scripts/doctor.sh
# Prints one OK / WARN / FAIL line per check and exits 1 if any check FAILs.
#
# Checks: docker CLI and daemon; Compose v2 (2.24+ for docker-compose.prod.yml); the published ports (free, or used by
# this project's own containers); the memory Docker can use; free disk; git line endings of *.sh / *.py.
set -u

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fails=0
ok()   { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }

# the compose project name: COMPOSE_PROJECT_NAME, else the folder name, normalised as Compose does
project=${COMPOSE_PROJECT_NAME:-$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}

# a port setting from the environment, else from .env (only *_PORT lines are read), else the default
port_setting() { # name default
  local v=${!1:-}
  if [ -z "$v" ] && [ -f "$ROOT/.env" ]; then
    v=$(grep -E "^$1=[0-9]+[[:space:]]*$" "$ROOT/.env" 2>/dev/null | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')
  fi
  printf '%s' "${v:-$2}"
}

# 1. docker CLI and daemon
if ! command -v docker >/dev/null 2>&1; then
  fail "docker: not found on PATH (install Docker Desktop, or Docker Engine with the Compose plugin on Linux)"
  echo "1 or more checks failed."; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  fail "docker: the daemon is not reachable (start Docker Desktop / 'sudo systemctl start docker'; on Linux, add yourself to the docker group or use sudo)"
  echo "1 or more checks failed."; exit 1
fi
ok "docker: $(docker version --format 'client {{.Client.Version}}, server {{.Server.Version}}' 2>/dev/null) ($(docker info --format '{{.OSType}}/{{.Architecture}}' 2>/dev/null))"

# 2. Compose v2
cv=$(docker compose version --short 2>/dev/null | sed 's/^v//')
if [ -z "$cv" ]; then
  fail "compose: 'docker compose' (v2) not available; the old 'docker-compose' v1 is not supported (install the Compose plugin)"
else
  major=${cv%%.*}; rest=${cv#*.}; minor=${rest%%.*}
  if [ "${major:-0}" -lt 2 ] 2>/dev/null; then
    fail "compose: version $cv; need v2"
  elif [ "${major:-0}" -eq 2 ] && [ "${minor:-0}" -lt 24 ] 2>/dev/null; then
    warn "compose: version $cv works for docker-compose.yml; docker-compose.prod.yml needs 2.24 or later (!reset/!override)"
  else
    ok "compose: version $cv"
  fi
fi

# 3. ports: free, or published by this project's containers. Each host port comes from its variable (environment or
# .env), as docker-compose.yml reads it.
port_open() { # true if something on this machine accepts connections on the port
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}
for spec in "web:WEB_PORT:5173" "api:API_PORT:8000" "source-sim:SIM_PORT:8100" "sftp:SFTP_PORT:2222" "postgres:POSTGRES_PORT:5432"; do
  svc=${spec%%:*}; rest=${spec#*:}; var=${rest%%:*}; def=${rest#*:}
  p=$(port_setting "$var" "$def")
  owners=$(docker ps --filter "publish=$p" --format '{{.Label "com.docker.compose.project"}}/{{.Names}}' 2>/dev/null)
  if [ -n "$owners" ]; then
    if printf '%s\n' "$owners" | grep -q "^$project/"; then
      ok "port $p ($svc): used by this project ($(printf '%s' "$owners" | head -n 1 | cut -d/ -f2))"
    else
      fail "port $p ($svc): published by another container ($(printf '%s' "$owners" | tr '\n' ' ')); stop it first"
    fi
  elif port_open "$p"; then
    fail "port $p ($svc): in use by another program on this machine; stop it first"
  else
    ok "port $p ($svc): free"
  fi
done

# 4. memory Docker can use (Docker Desktop: Settings > Resources; WSL: .wslconfig [wsl2] memory=)
mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null)
if [ -n "$mem" ] && [ "$mem" -gt 0 ] 2>/dev/null; then
  mb=$((mem / 1024 / 1024))
  if [ "$mb" -lt 2048 ]; then
    fail "memory: Docker has ${mb} MB; give it at least 4 GB"
  elif [ "$mb" -lt 3900 ]; then
    warn "memory: Docker has ${mb} MB; 4 GB or more is recommended (the api test suite and the web build need it)"
  else
    ok "memory: Docker has ${mb} MB"
  fi
else
  warn "memory: could not read the memory Docker can use"
fi

# 5. free disk where the repo is (Docker Desktop keeps images in its own disk image; check it in its settings)
free_kb=$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "$free_kb" ]; then
  gb=$((free_kb / 1024 / 1024))
  if [ "$gb" -lt 3 ]; then
    fail "disk: ${gb} GB free at $ROOT; the images and database need about 5 GB"
  elif [ "$gb" -lt 10 ]; then
    warn "disk: ${gb} GB free at $ROOT; 10 GB or more is recommended"
  else
    ok "disk: ${gb} GB free at $ROOT"
  fi
else
  warn "disk: could not read free space at $ROOT"
fi
droot=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)
if [ -n "$droot" ] && [ -d "$droot" ]; then
  dkb=$(df -Pk "$droot" 2>/dev/null | awk 'NR==2 {print $4}')
  if [ -n "$dkb" ]; then
    dgb=$((dkb / 1024 / 1024))
    if [ "$dgb" -lt 10 ]; then warn "disk: ${dgb} GB free for Docker at $droot"; else ok "disk: ${dgb} GB free for Docker at $droot"; fi
  fi
fi

# 6. git line endings: a CR in a .sh or .py file breaks it inside the Linux containers
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  crlf=$(git -C "$ROOT" ls-files --eol -- '*.sh' '*.py' 2>/dev/null | grep -c 'w/crlf')
  autocrlf=$(git -C "$ROOT" config --get core.autocrlf 2>/dev/null)
  if [ "${crlf:-0}" -gt 0 ]; then
    warn "git: $crlf .sh/.py files have CRLF line endings in the working tree (core.autocrlf=${autocrlf:-unset}); fix: git config --global core.autocrlf input, then clone the repo again"
  elif [ "$autocrlf" = "true" ]; then
    warn "git: core.autocrlf=true; *.sh is forced to LF by .gitattributes, but *.py is not. 'git config core.autocrlf input' is safer for this repo"
  else
    ok "git: .sh/.py files have LF line endings (core.autocrlf=${autocrlf:-unset})"
  fi
else
  warn "git: not a git checkout, line endings not checked"
fi

if [ "$fails" -gt 0 ]; then
  echo "$fails check(s) failed."
  exit 1
fi
echo "All required checks passed. Start the stack: docker compose up -d --build, then open http://localhost:$(port_setting WEB_PORT 5173)"
