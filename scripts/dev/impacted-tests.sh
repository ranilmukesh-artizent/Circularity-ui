#!/bin/bash
# The backend test files a change can affect, from the import graph (host-only: git, find, awk; no Docker, ~1-3 s).
#   bash scripts/dev/impacted-tests.sh [base]      # base defaults to feature/plan-09-recover
# Changed files = `git diff --name-only <base>` (committed and uncommitted) plus untracked files. Prints, one per line
# and relative to backend/ (tests/test_x.py): the changed test files themselves; every test that refers to a changed
# backend/di module (`from di.a.b import`, `import di.a.b`, `from di.a import b`, relative imports, and dotted names in
# strings such as mock.patch("di.a.b.f")); and one level of importers: tests that refer to a di module that itself
# refers to a changed one. A changed non-.py file under backend/di counts as a change of every module in its folder.
# A change in the shared core (backend/di/core/, backend/migrations/, backend/tests/conftest.py,
# backend/di/services/agents/forbidden.py) prints the single line ALL instead: name the files yourself, or run a suite.
# Changes outside backend/ (frontend, docs, fixtures) select nothing; a changed fixtures/golden file is noted on stderr.
base=${1:-feature/plan-09-recover}
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
changed=$( { git diff --name-only "$base" 2>/dev/null; git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)
[ -n "$changed" ] || exit 0
if printf '%s\n' "$changed" | grep -Eq '^backend/(di/core/|migrations/|tests/conftest\.py$|di/services/agents/forbidden\.py$)'; then
  echo ALL
  exit 0
fi
printf '%s\n' "$changed" | grep -q '^fixtures/golden/' && echo "note: fixtures/golden changed; parity tests are not selected by import" >&2
changed_be=$(printf '%s\n' "$changed" | grep '^backend/' | while IFS= read -r f; do [ -e "$f" ] && echo "$f"; done)
[ -n "$changed_be" ] || exit 0
# non-.py files under backend/di: every .py module of their folder counts as changed
extra=$(printf '%s\n' "$changed_be" | grep '^backend/di/' | grep -v '\.py$' | while IFS= read -r f; do ls "$(dirname "$f")"/*.py 2>/dev/null; done)
# a changed non-test helper under backend/tests is found by its module name in the tests
helpers=$(printf '%s\n' "$changed_be" | grep -E '^backend/tests/[^/]+\.py$' | grep -v '/test_')
files=$(find backend/di backend/tests -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort)
tmp="${TMPDIR:-/tmp}/impacted.$$"
# The import edges ("src<TAB>dst", both files) are cached per checkout in $cache and rebuilt only for files newer than it.
cache="${TMPDIR:-/tmp}/di-impacted-$(printf '%s' "$REPO" | cksum | cut -d' ' -f1).edges"
printf '%s\n' "$files" > "$tmp.files"
grep -E '^backend/tests/[^/]+\.py$' "$tmp.files" | grep -v '/test_' > "$tmp.helpers"
if [ -f "$cache" ]; then
  find backend/di backend/tests -name '*.py' -newer "$cache" -not -path '*/__pycache__/*' | LC_ALL=C sort > "$tmp.scan"
else
  cp "$tmp.files" "$tmp.scan"
fi
if [ -s "$tmp.scan" ]; then
  # stage 1: edges of the files to scan. A di module is "known" from the full file list; names are resolved by the
  # longest known module prefix, so patch strings and lazy imports count as well as top-level imports.
  # shellcheck disable=SC2046
  awk -v modlist="$tmp.files" -v helperlist="$tmp.helpers" '
function modname(p,   m) {
  m = p; sub(/^backend\//, "", m); sub(/\.py$/, "", m); sub(/\/__init__$/, "", m); gsub(/\//, ".", m); return m
}
function ident(c) { return c ~ /[A-Za-z0-9_.]/ }
function resolve(name,   n) {
  while (name != "") {
    if (name in modfile) return modfile[name]
    n = match(name, /\.[^.]*$/); if (!n) return ""
    name = substr(name, 1, n - 1)
  }
  return ""
}
function edge(src, dst) { if (dst != "" && dst != src && !((src "\t" dst) in seen)) { seen[src "\t" dst] = 1; print src "\t" dst } }
function addnames(src, base, s,   k, parts, np, w) {
  gsub(/[()\\]/, " ", s); sub(/#.*/, "", s)
  np = split(s, parts, /[ ,\t]+/)
  for (k = 1; k <= np; k++) { w = parts[k]; if (w != "" && w != "as" && (base "." w) in modfile) edge(src, modfile[base "." w]) }
}
BEGIN {
  while ((getline p < modlist) > 0) if (p ~ /^backend\/di\//) modfile[modname(p)] = p
  while ((getline h < helperlist) > 0) { sub(/^backend\/tests\//, "", h); sub(/\.py$/, "", h); helper[h] = 1 }
}
FNR == 1 {
  pend = ""; pbase = ""; src = FILENAME; pkg = modname(src)
  if (src !~ /__init__\.py$/) { n = match(pkg, /\.[^.]*$/); pkg = n ? substr(pkg, 1, n - 1) : pkg }
}
{
  line = $0
  if (pend != "") { addnames(src, pbase, line); if (line ~ /\)/) pend = ""; next }
  rest = line
  while (match(rest, /di(\.[A-Za-z_][A-Za-z0-9_]*)+/) > 0) {
    tok = substr(rest, RSTART, RLENGTH)
    prev = (RSTART > 1) ? substr(rest, RSTART - 1, 1) : " "
    if (!ident(prev)) edge(src, resolve(tok))
    rest = substr(rest, RSTART + RLENGTH)
  }
  if (match(line, /^[ \t]*from[ \t]+[A-Za-z0-9_.]+[ \t]+import/)) {
    s = line; sub(/^[ \t]*from[ \t]+/, "", s)
    base = s; sub(/[ \t].*$/, "", base)
    names = s; sub(/^[^ \t]+[ \t]+import[ \t]*/, "", names)
    if (base ~ /^\./) {
      up = 0; while (substr(base, 1, 1) == ".") { up++; base = substr(base, 2) }
      pk = pkg; for (u = 1; u < up; u++) { n = match(pk, /\.[^.]*$/); pk = n ? substr(pk, 1, n - 1) : pk }
      full = (base == "") ? pk : pk "." base
      if (full in modfile) edge(src, modfile[full])
      base = full
    }
    addnames(src, base, names)
    if (names ~ /^\(/ && names !~ /\)/) { pend = 1; pbase = base }
  } else if (src ~ /^backend\/tests\// && match(line, /^[ \t]*(from|import)[ \t]+[A-Za-z_][A-Za-z0-9_]*/)) {
    s = line; sub(/^[ \t]*(from|import)[ \t]+/, "", s); sub(/[^A-Za-z0-9_].*$/, "", s)
    if (s in helper) edge(src, "backend/tests/" s ".py")
  }
}' $(cat "$tmp.scan") /dev/null > "$tmp.new"
  # keep the cached edges of files that were not rescanned (and still exist)
  if [ -f "$cache" ]; then
    awk -F'\t' 'FILENAME == ARGV[1] { skip[$0] = 1; next } FILENAME == ARGV[2] { have[$0] = 1; next } !($1 in skip) && ($1 in have)' \
      "$tmp.scan" "$tmp.files" "$cache" > "$tmp.keep"
  else : > "$tmp.keep"; fi
  cat "$tmp.keep" "$tmp.new" > "$cache"
fi
# stage 2: select the tests
{ printf 'CHANGED\n%s\n%s\n' "$changed_be" "$extra"; } > "$tmp.chg"
awk -F'\t' '
FILENAME == ARGV[1] { if ($0 != "" && $0 != "CHANGED") chg[$0] = 1; next }
FILENAME == ARGV[2] { have[$0] = 1; next }
{ if (!($1 in have) || !($2 in have)) next; s = $1; d = $2
  # one level of importers: di modules (not package __init__ re-exports) that refer to a changed module
  if ((d in chg) && s ~ /^backend\/di\// && s !~ /__init__\.py$/) d1[s] = 1
  e[++ne] = s "\t" d }
END {
  for (f in chg) if (f ~ /^backend\/tests\/test_[^\/]*\.py$/) out[f] = 1
  for (i = 1; i <= ne; i++) { split(e[i], a, "\t"); s = a[1]; d = a[2]
    if (s ~ /^backend\/tests\/test_[^\/]*\.py$/ && ((d in chg) || (d in d1))) out[s] = 1 }
  for (f in out) { o = f; sub(/^backend\//, "", o); print o }
}' "$tmp.chg" "$tmp.files" "$cache" | LC_ALL=C sort
rm -f "$tmp".*
