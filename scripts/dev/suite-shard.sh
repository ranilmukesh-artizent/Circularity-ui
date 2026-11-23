#!/bin/bash
# Run one shard of the api suite, or the source-sim suite, so a long suite can be split across runs.
#   bash scripts/dev/suite-shard.sh 2 4          # every 4th file of the sorted tests/test_*.py, starting at the 2nd
#   bash scripts/dev/suite-shard.sh 2 4 --list   # only print that shard's files
#   bash scripts/dev/suite-shard.sh sim          # the source-sim suite
# The api shard runs through api-test.sh (the api test lock, worker stopped) with API_TEST_NO_X=1, so a failure does
# not hide the rest of the shard. Exits with the suite's status; 2 on bad arguments.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
usage() { echo "usage: suite-shard.sh <n> <m> [--list]   (1 <= n <= m)   |   suite-shard.sh sim" >&2; exit 2; }

if [ "$1" = sim ]; then
  filtered '^(FAILED|ERROR)|passed|failed|error' 40 docker compose exec -T source-sim pytest -q -p no:cacheprovider
  exit $?
fi

n=$1 m=$2
case $n in '' | *[!0-9]*) usage ;; esac
case $m in '' | *[!0-9]*) usage ;; esac
{ [ "$n" -ge 1 ] && [ "$n" -le "$m" ]; } || usage
case ${3:-} in '' | --list) ;; *) usage ;; esac

# The file list comes from the container, so it matches what pytest sees; sorted bytewise for a stable split.
all=$(docker compose exec -T api sh -c 'ls tests/test_*.py' | LC_ALL=C sort) || {
  echo "could not list tests/test_*.py in the api container" >&2
  exit 1
}
shard=$(printf '%s\n' "$all" | awk -v n="$n" -v m="$m" 'NF && (NR - n) % m == 0 && NR >= n')
if [ -z "$shard" ]; then
  echo "shard $n/$m: no test files" >&2
  exit 1
fi
if [ "${3:-}" = --list ]; then
  printf '%s\n' "$shard"
  exit 0
fi
echo "shard $n/$m: $(printf '%s\n' "$shard" | wc -l | tr -d ' ') of $(printf '%s\n' "$all" | wc -l | tr -d ' ') files"
# shellcheck disable=SC2046  # one file name per word (test file names have no spaces)
API_TEST_NO_X=1 bash "$REPO/scripts/dev/api-test.sh" $(printf '%s\n' "$shard")
