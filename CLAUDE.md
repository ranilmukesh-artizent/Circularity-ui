@AGENTS.md

## Claude Code notes

- Shared project settings are in `.claude/settings.json`; personal ones go in `.claude/settings.local.json` (never
  commit it).
- This machine is Windows 11 with Docker Desktop (context `desktop-linux`): `docker` and `docker compose` work
  directly from PowerShell and Git Bash, so run `bash scripts/dev/*.sh` from the repo root in Git Bash (the Bash
  tool). These notes are about this machine, not a requirement of the repo (any machine with Git and Docker runs it,
  see README). On a machine whose Docker runs inside a WSL distro instead, run the scripts through a `.sh` file with
  `wsl -d <distro> -u root -- bash /mnt/c/<path>/scripts/dev/<script>.sh`.
- Use the PowerShell tool for git. Git Bash sometimes fails with "fork: Resource temporarily unavailable"; retry,
  or use PowerShell.
- Commit messages: write them to a file and use `git commit -F <file>`; PowerShell here-strings have broken them.

### Git Bash pitfalls

- `export MSYS_NO_PATHCONV=1` before a script or command that passes a container path (`/tmp/...`, `/app/...`).
  Without it Git Bash rewrites the path to a Windows one; `api-test.sh`'s lock on `/tmp/di-pytest.lock` failed that
  way. `parallel-suite.sh` sets it itself.
- In a loop, give every `docker` / `docker compose` call `</dev/null`. They read stdin and eat the rest of the
  loop's input.
- Output of Windows programs (host Python, PowerShell) ends lines with CRLF: strip it with `tr -d '\r'`, never with a
  literal CR in the script (Git Bash drops it).
- Host Python on Windows opens files as cp1252: pass `encoding="utf-8"` to every `open()`.

## Working with subagents

- Subagents share one database, one dev server and one working tree. Give each a disjoint set of files and a report
  path under the task's folder (e.g. `docs/agents/audits/<audit>/work/<letter>-<topic>.md`).
- api tests on the main database go through the lock (`scripts/dev/api-test.sh`), one at a time. Parallel api tests
  run only on private databases: `scripts/dev/parallel-suite.sh`, or a worktree with
  `docker compose run --rm --no-deps -e DI_DATABASE_URL=…/<own db> api …` (migrate it and run `ensure_sources`
  first; see the script). Keep browser checks read-only unless the lead runs them.
- A git worktree's `frontend/node_modules` may be a junction to the main tree's. Remove the junction with `rmdir`
  BEFORE `git worktree remove`, or the removal deletes the main tree's `node_modules`.
- Read-only agent types (`code-reviewer`, `code-explorer`, `Explore`) cannot write a report file or run git. Use
  `general-purpose` for a review that must write its report.
- Verify every subagent claim before you report it (AGENTS.md rule 15): rerun its test or read its log yourself.
- Agent tool worktrees (`isolation: "worktree"`) start from the default branch: brief each writer to
  `git merge --ff-only <your branch>` first. Writers check from their worktree with `scripts/dev/wt-check.sh <k>`
  (own database); the lead verifies a merge with `scripts/dev/lead-verify.sh` and keeps the full suite and smokes for
  phase gates (docs/agents/dos-and-donts.md, Tests).
- Writers run checks in the foreground: a background run watched by Monitor keeps waking the lead after the writer is
  done. Stop such a writer with TaskStop.

## Skills in this repo

Installed in `.claude/skills/` from public collections; `.claude/skills/SOURCES.md` says where each came from.
Don't edit them; apply these adaptations when you use them:

| Skill | From | Adaptation here |
|---|---|---|
| test-driven-development, systematic-debugging, verification-before-completion | superpowers | Test commands are `scripts/dev/*.sh` (api-test, full-suite, web-check), not `npm test`. |
| writing-plans | superpowers | Save plans under `docs/agents/plans/`, not `docs/superpowers/`. |
| requesting-code-review, receiving-code-review, finishing-a-development-branch | superpowers | Commit and push only when the user asks; branch `feature/fullstack-poc`. |
| webapp-testing | anthropics | Use the repo's Node Playwright with the installed Chrome (`channel: 'chrome'`, see `frontend/scripts/smoke-*.mjs`), not Python Playwright. Write outputs to the session scratchpad, never `/tmp` or `/mnt/user-data`. |
| mcp-builder | anthropics | Its `scripts/` folder was removed (its evaluation sent tool results to an external API). This repo's MCP server is Python (`backend/di/mcp/`), so use the Python guide. |
| frontend-design | anthropics | Work from the existing brand tokens (`frontend/src/styles/`, `frontend/src/layout/app.css`); never change a demo number or text, golden files or the generated demo stylesheet. Plan per `docs/agents/plans/10-unified-assistant-ux.md`. |
| web-interface-guidelines | vercel-labs | Review any frontend change against it; report file:line. |
| emil-design-eng | emilkowalski | Interaction polish and motion restraint only; skip its "Initial Response" line. No motion on actions people repeat all day. |

- A cross-reference like `superpowers:test-driven-development` means the project skill of the same name, without
  the prefix.
- Skills they mention that are not installed (subagent-driven-development, executing-plans, using-git-worktrees,
  brainstorming): do that step inline.
- "Your human partner" means the user.

Also installed (sources and licences in `.claude/SETUP_SOURCES.md`): `.claude/agents/` (8 subagents),
`.claude/commands/` (`/feature-dev`, `/commit`, `/smart-debug`) and `.mcp.json` (Playwright MCP).
