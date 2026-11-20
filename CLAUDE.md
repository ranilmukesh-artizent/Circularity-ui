@AGENTS.md

## Claude Code notes

- Shared project settings are in `.claude/settings.json`; personal ones go in `.claude/settings.local.json` (never
  commit it).
- This machine is Windows. Use the PowerShell tool for git and for `wsl ... bash scripts/dev/*.sh`. Git Bash often
  fails here with "fork: Resource temporarily unavailable".
- Subagents share one database and one dev server. Give each a disjoint set of files. Serialize api tests through
  the lock (`scripts/dev/api-test.sh`), and keep browser checks read-only unless the lead runs them.
- Commit messages: write them to a file and use `git commit -F <file>`; PowerShell here-strings have broken them.

## Skills in this repo

Installed in `.claude/skills/` from public collections; `.claude/skills/SOURCES.md` says where each came from.
Don't edit them; apply these adaptations when you use them:

| Skill | From | Adaptation here |
|---|---|---|
| test-driven-development, systematic-debugging, verification-before-completion | superpowers | Test commands are `scripts/dev/*.sh` (api-test, full-suite, web-check), not `npm test`. |
| writing-plans | superpowers | Save plans under `docs/agents/plans/`, not `docs/superpowers/`. |
| requesting-code-review, receiving-code-review, finishing-a-development-branch | superpowers | Commit and push only when the user asks; branch `feature/fullstack-poc`. |
| webapp-testing | anthropics | Use the repo's Node Playwright with the installed Chrome (`channel: 'chrome'`, see `apps/web/scripts/smoke-*.mjs`), not Python Playwright. Write outputs to the session scratchpad, never `/tmp` or `/mnt/user-data`. |
| mcp-builder | anthropics | Its `scripts/` folder was removed (its evaluation sent tool results to an external API). This repo's MCP server is Python (`apps/api/di/mcp/`), so use the Python guide. |

- A cross-reference like `superpowers:test-driven-development` means the project skill of the same name, without
  the prefix.
- Skills they mention that are not installed (subagent-driven-development, executing-plans, using-git-worktrees,
  brainstorming): do that step inline.
- "Your human partner" means the user.

Being added by another agent (see `.claude/SETUP_SOURCES.md`): `.claude/agents/`, `.claude/commands/`, `.mcp.json`.
