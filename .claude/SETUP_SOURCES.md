# Sources of third-party Claude Code configuration

Everything listed under "Installed" was copied verbatim (frontmatter and body unchanged) from the
public source named in the table. Nothing in these files was written for this repo. The only
difference from upstream is line endings: the files are in the working tree with CRLF because this
repo has `core.autocrlf=true`. Git stores them with LF on commit, which matches upstream.

Retrieved 2026-11-20. Upstream commits:

| Upstream repo | Commit | Commit date | Licence |
| --- | --- | --- | --- |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) (Anthropic's official Claude Code plugins) | `d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6` | 2026-11-19 | Apache-2.0 (repo `LICENSE` and each plugin's `LICENSE`, identical files) |
| [wshobson/agents](https://github.com/wshobson/agents) (Seth Hobson's plugin marketplace) | `42203085cfc5736204bf0f6d436dff7e1da0bf3f` | 2026-11-18 | MIT, Copyright (c) 2024 Seth Hobson |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) (npm `@playwright/mcp`) | tag `v0.0.84` | npm publish 2026-10-31 | Apache-2.0 |

Licence texts are copied next to the files that need them:

- `.claude/agents/LICENSE-anthropic-claude-plugins-official.txt` and `.claude/commands/LICENSE-anthropic-claude-plugins-official.txt`: Apache License 2.0, copied from the upstream `LICENSE`. Upstream has no `NOTICE` file.
- `.claude/agents/LICENSE-wshobson-agents.txt` and `.claude/commands/LICENSE-wshobson-agents.txt`: MIT licence with the copyright notice, as MIT requires.

Claude Code loads only `*.md` files from these folders, so it ignores the `.txt` licence files.

## Installed

### Subagents (`.claude/agents/`)

| File (agent `name`) | Source | Licence | Why |
| --- | --- | --- | --- |
| `code-explorer.md` (`code-explorer`) | [plugins/feature-dev/agents/code-explorer.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/feature-dev/agents/code-explorer.md) | Apache-2.0, Anthropic | Read-only agent (no Bash, Write or Edit) that traces a feature from entry point to storage. Good for the web → api → Postgres paths and for onboarding. Used by `/feature-dev`. |
| `code-architect.md` (`code-architect`) | [plugins/feature-dev/agents/code-architect.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/feature-dev/agents/code-architect.md) | Apache-2.0, Anthropic | Read-only agent that turns existing patterns into an implementation blueprint. Used by `/feature-dev`. |
| `code-reviewer.md` (`code-reviewer`) | [plugins/feature-dev/agents/code-reviewer.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/feature-dev/agents/code-reviewer.md) | Apache-2.0, Anthropic | Read-only reviewer that checks CLAUDE.md compliance and bugs, and reports only findings with confidence ≥ 80. Used by `/feature-dev`. Chosen over the `pr-review-toolkit` variant because its tools are read-only. |
| `pr-test-analyzer.md` (`pr-test-analyzer`) | [plugins/pr-review-toolkit/agents/pr-test-analyzer.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/pr-review-toolkit/agents/pr-test-analyzer.md) | Apache-2.0, Anthropic | Reviews whether the tests in a change cover its behaviour (pytest, vitest, Playwright). It has no `tools:` line, so it inherits the session's tools and permission rules. |
| `debugging-toolkit-debugger.md` (`debugging-toolkit-debugger`) | [plugins/debugging-toolkit/agents/debugger.md](https://github.com/wshobson/agents/blob/42203085cfc5736204bf0f6d436dff7e1da0bf3f/plugins/debugging-toolkit/agents/debugger.md) | MIT, Seth Hobson | Short root-cause debugger for errors and failing tests. `/smart-debug` calls it by this exact name, so the upstream name is kept. Inherits tools. |
| `python-development-fastapi-pro.md` (`python-development-fastapi-pro`) | [plugins/python-development/agents/fastapi-pro.md](https://github.com/wshobson/agents/blob/42203085cfc5736204bf0f6d436dff7e1da0bf3f/plugins/python-development/agents/fastapi-pro.md) | MIT, Seth Hobson | FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest and SSE: matches `backend` and `source-sim`. Inherits tools. Frontmatter sets `model: opus`. |
| `typescript-pro.md` (`typescript-pro`) | [plugins/javascript-typescript/agents/typescript-pro.md](https://github.com/wshobson/agents/blob/42203085cfc5736204bf0f6d436dff7e1da0bf3f/plugins/javascript-typescript/agents/typescript-pro.md) | MIT, Seth Hobson | Strict TypeScript and React, with Vitest named. Matches `frontend`. Inherits tools. Frontmatter sets `model: opus`. |
| `backend-development-security-auditor.md` (`backend-development-security-auditor`) | [plugins/backend-development/agents/security-auditor.md](https://github.com/wshobson/agents/blob/42203085cfc5736204bf0f6d436dff7e1da0bf3f/plugins/backend-development/agents/security-auditor.md) | MIT, Seth Hobson | Focused application-security review (OWASP Top 10, authn/authz, injection, secrets). Relevant to the API's JWT auth, access screens and MCP bearer gate. Inherits tools. |

### Slash commands (`.claude/commands/`)

| File (command) | Source | Licence | Why |
| --- | --- | --- | --- |
| `feature-dev.md` (`/feature-dev`) | [plugins/feature-dev/commands/feature-dev.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/feature-dev/commands/feature-dev.md) | Apache-2.0, Anthropic | Seven phases: discover, explore, ask clarifying questions, design, implement after approval, review, summarise. Uses the `code-explorer`, `code-architect` and `code-reviewer` agents above. |
| `commit.md` (`/commit`) | [plugins/commit-commands/commands/commit.md](https://github.com/anthropics/claude-plugins-official/blob/d7d32797e7e02708d0bb00ffe8b8f2397dc1aea6/plugins/commit-commands/commands/commit.md) | Apache-2.0, Anthropic | Makes one commit from the current diff. `allowed-tools` is limited to `git add`, `git status` and `git commit`. It does not push. Runs only when someone types `/commit`. |
| `smart-debug.md` (`/smart-debug`) | [plugins/debugging-toolkit/commands/smart-debug.md](https://github.com/wshobson/agents/blob/42203085cfc5736204bf0f6d436dff7e1da0bf3f/plugins/debugging-toolkit/commands/smart-debug.md) | MIT, Seth Hobson | Structured flow from hypotheses to root cause, fix and validation, for failing tests and errors. Uses `debugging-toolkit-debugger`. Treats `$ARGUMENTS` as data. |

### MCP servers (`.mcp.json`)

| Server | Config | Licence | Why |
| --- | --- | --- | --- |
| `playwright` | `npx -y @playwright/mcp@0.0.84 --browser chrome --isolated` ([README at v0.0.84](https://github.com/microsoft/playwright-mcp/blob/v0.0.84/README.md), [npm](https://www.npmjs.com/package/@playwright/mcp)) | Apache-2.0, Microsoft | Official Microsoft server that lets agents drive the installed Chrome to check the Vite app (http://localhost:5173 etc.). Pinned to 0.0.84 (published 2026-10-31, at least two weeks old; `latest` is 0.0.86). `--isolated` keeps the browser profile in memory, so no cookies or sessions persist on disk. No secrets are needed, and the README documents no telemetry. |

Claude Code asks each user to approve project-scoped `.mcp.json` servers before first use in interactive sessions.

## Considered and rejected

| Candidate | Source | Reason |
| --- | --- | --- |
| Circularity's own MCP server (`http://localhost:8000/mcp`) | this repo, `backend/di/mcp/server.py` | `BearerGate` returns 401 to any request without `Authorization: Bearer <JWT from /api/auth/login>`, and tools also need `X-Agent` / tenant headers. It cannot work without a token, so it was left out. The lead could add it with env expansion so no token sits in the file, for example `"type": "http", "url": "http://localhost:8000/mcp", "headers": {"Authorization": "Bearer ${CIRCULARITY_MCP_TOKEN}", "X-Agent": "${CIRCULARITY_MCP_AGENT}"}`. The JWT expires, though, so each developer would need to refresh it. |
| `code-review` command | anthropics/claude-plugins-official `plugins/code-review` | Same name as Claude Code's built-in `/code-review`. Needs the `gh` CLI (not installed here) and a GitHub inline-comment MCP tool. |
| `review-pr` command | anthropics/claude-plugins-official `plugins/pr-review-toolkit` | Calls four more agents (comment-analyzer, silent-failure-hunter, type-design-analyzer, code-simplifier). Not worth adding them all to keep the set small. Built-in `/code-review` and `/simplify` cover this. |
| `silent-failure-hunter` agent | same plugin | Hard-codes conventions from another codebase (`logForDebugging`, `logError`, Sentry `constants/errorIds.ts`) that do not exist here. |
| `code-reviewer` (pr-review-toolkit variant) | same plugin | Nearly the same as the feature-dev one but inherits every tool. The read-only variant was preferred. |
| `commit-push-pr`, `clean_gone` commands | `plugins/commit-commands` | Push to the remote, open PRs or delete branches. Too much for a shared default. |
| Agents/commands in `anthropics/claude-code` | [anthropics/claude-code](https://github.com/anthropics/claude-code) | Repo licence is "© Anthropic PBC. All rights reserved" (Commercial Terms), not an open licence. Its plugins moved to claude-plugins-official, which was used instead. |
| `python-pro`, `fastapi-developer`, `react-specialist`, `typescript-pro`, `postgres-pro`, `debugger`, `test-automator`, `security-auditor` | [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) @ `ed74d115` (MIT) | Every body tells the agent to "query the context manager" with a JSON protocol that does not exist in Claude Code, and includes invented progress numbers. Most grant `Write, Edit, Bash` explicitly. VoltAgent's `security-auditor` is read-only but covers compliance and organisational audits (SOC 2, interviews), not code. |
| `sql-pro`, `database-optimizer`, `database-architect` | wshobson/agents | Mostly cloud warehouse and HTAP content (Snowflake, BigQuery, replication). `python-development-fastapi-pro` already covers SQLAlchemy/Alembic on Postgres. |
| `test-automator` (backend-development) | wshobson/agents | Reasonable, but left out to stay within 8 agents. `pr-test-analyzer` plus the testing skills cover this. |
| `test-generate` command | wshobson/agents `plugins/unit-testing` | Generates placeholder tests (`assert result is not None`) and assumes Jest. This repo uses vitest. |
| `code-explain`, `onboard` commands | wshobson/agents | `code-explain` is a long generic tutorial template. `onboard` is an HR 30/60/90-day plan, not codebase onboarding. |
| `wshobson/commands` repo | [wshobson/commands](https://github.com/wshobson/commands) | Archived. The author points to wshobson/agents. |
| Commands listed in `hesreallyhim/awesome-claude-code` | [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) @ `6bd39d5c` | The list (CC BY-NC-ND 4.0) no longer has a slash-command category. Linked command repos often have no licence. Only openly licensed sources were used. |
| Hooks | — | Out of scope; the lead decides. |

No downloaded scripts were run. Upstream repos were shallow-cloned into a temporary folder and read only.

## Notes

- `python-development-fastapi-pro` and `typescript-pro` keep `model: opus` from upstream (verbatim); using them costs more per call.
- The app's own MCP server (`/mcp`) is not in `.mcp.json`: it needs a login JWT that expires.

