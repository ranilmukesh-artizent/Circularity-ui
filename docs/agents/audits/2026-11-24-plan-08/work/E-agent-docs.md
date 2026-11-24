# E: agent entry docs made current (24 Nov 2026, subagent A)

Edited only: AGENTS.md, CLAUDE.md, docs/agents/{dos-and-donts,scripts,history,testing}.md, .claude/SETUP_SOURCES.md.
No commits, no tests, no state-changing git or docker. All files UTF-8, LF (0 CR checked).

## Per file
- **AGENTS.md**: Map adds `services/agents/forbidden.py`, `docs/agents/audits/`, `docs/agents/research/` (`trial/` was
  there). Run: Docker Desktop + Git Bash first, WSL as the alternative (`<distro>`). Test table: full suite "the gate",
  ~32 min + 1; new rows parallel-suite.sh (~7 min, pre-check) and modeler/MVP smokes; private-DB exception under
  "One api pytest". Rules 10 (pipeline refuses forbidden non-read actions for agent-prepared calls), 11 (lock on the
  main DB; parallel-suite on private DBs; serial suite stays the gate), 13 (Git Bash or WSL). Current state: later UI
  gaps, audit link, F1–F11 fixed or decided, gate numbers; Next: per-agent credentials, catalogue MCP tools + OAuth
  (research link), plans 3–5, B18.
- **CLAUDE.md**: Docker Desktop (`docker context ls`: `desktop-linux *`; server linux 29.7.2; `wsl -l` has no
  Ubuntu-24.04, only Ubuntu-26.04 stopped + docker-desktop). New "Git Bash pitfalls" (MSYS_NO_PATHCONV, `</dev/null`,
  CRs, host Python cp1252 -> `encoding="utf-8"`, checked: `locale.getpreferredencoding()` = cp1252) and "Working with
  subagents" (disjoint files + report path, private DBs, node_modules junction before `git worktree remove`, read-only
  agent types, rule 15). Stale "being added by another agent" replaced (8 agents, 3 commands, .mcp.json exist).
- **dos-and-donts.md**: forbidden.py + add new person-only actions there; tenant checks for unscoped roles and group
  units (F8); no renumbering of a migration a shared DB ran; parallel only on private DBs; fresh-DB failures checked on
  base code; `git fetch` + `git log HEAD..origin/...` before big work; keep one version of a duplicated screen.
  Shell section rewritten for Docker Desktop; "both modes" smoke/invoke wording fixed (one mode since B17c).
- **scripts.md**: rows for parallel-suite.sh and test-times.txt (regeneration command); full-suite ~32 min;
  suite-shard is serial; migrate-reapply `[BASE]`; Docker Desktop note; frontend scripts add dump-po-golden,
  smoke-fabric/modeler/mvp, screenshot; npm lint/knip/preview; broken testing.md anchor fixed.
- **history.md**: section 8 gets its commit range (2a3ee00..5c20ddb, 69acbc4); new section 9 (95a45ed, 8fea98c,
  23c7f81, 2e985ff); Next renumbered to 10 with the agent items.
- **testing.md**: Docker Desktop intro; suites table at 24 Nov (api 140 files, 4,460 tests: 4,458 passed, 1 skipped,
  1 fixed in 8fea98c; sim 271; web 312 in 39 files; pre-check row); Parallel shards now scripts/dev/parallel-suite.sh
  (103 safe files in 4 shards, 37 serial-only, from `--list`) with known fresh-DB failures; smoke rows for modeler (17
  checks) and mvp (12 steps); last result from S-smokes; favicon 404 note; "before you claim done" updated.
- **.claude/SETUP_SOURCES.md**: CRLF/autocrlf sentence was stale; `.gitattributes` forces LF (`git ls-files --eol`).

## Verified / not verified
- Verified: every path named exists; `parallel-suite.sh --list` (runs nothing) gives 1+24+26+52 = 103 files and 37
  serial-only; the test-times regeneration one-liner, fed the 24 Nov junit via stdin in the api container, reproduces
  `test-times.txt` exactly (140 lines, no diff); branch equals origin (nothing unpushed).
- Not verified: the regeneration's `--junitxml=/tmp/...` through full-suite.sh (not run; same parser, file path instead
  of stdin); the "~7 min" and smoke timings (taken from the audit evidence); the node_modules junction and read-only
  agent-type notes (from the lead's brief).
- Left for others: `scripts/dev/full-suite.sh` header still says "16-25 min, ~3,450 tests" (script, not mine);
  learnings.md:173 still names Ubuntu-24.04 (B's file); dos-and-donts still mentions `engine()`/api mode (historical).
