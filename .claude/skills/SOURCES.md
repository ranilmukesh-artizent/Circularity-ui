# Skill sources

The skills in this directory are copied verbatim from public upstream repositories. Their text has not been modified. Each skill directory carries the upstream licence:

- `LICENSE.txt` (Apache 2.0) ships with each Anthropic skill.
- `LICENSE` (MIT) is a copy of obra/superpowers' repository-root licence. Upstream keeps it only at the repository root.

Fetched on 2026-11-20 from raw.githubusercontent.com at the pinned commits below.

| Upstream repo | Commit | Stars at fetch | Licence |
|---|---|---|---|
| https://github.com/obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` | ~322k | MIT, (c) 2025 Jesse Vincent |
| https://github.com/anthropics/skills | `e4bb5d960d87126ff3b3a8af1a104b7db67560ba` | ~198k | Apache 2.0 (per-skill `LICENSE.txt`) |
| https://github.com/vercel-labs/web-interface-guidelines | `main` on 26 Nov 2026 (raw `AGENTS.md`) | n/a | MIT, (c) 2025 Vercel Labs (`LICENSE` copied) |

## Installed

| Skill | Source | Upstream path | Licence | Why it fits this repo |
|---|---|---|---|---|
| test-driven-development | obra/superpowers @ `22f0b46` | `skills/test-driven-development/` | MIT | Red-green discipline for the pytest (api, source-sim) and vitest (web) suites and golden-file parity steps. |
| systematic-debugging | obra/superpowers @ `22f0b46` | `skills/systematic-debugging/` | MIT | Finds the root cause first across the web, api, Postgres, source-sim and Docker layers. |
| verification-before-completion | obra/superpowers @ `22f0b46` | `skills/verification-before-completion/` | MIT | Requires fresh test and golden-parity output before an agent claims a step is done. |
| writing-plans | obra/superpowers @ `22f0b46` | `skills/writing-plans/` | MIT | Turns a step (B17a, B18, ...) into bite-sized TDD tasks with exact files and tests. |
| requesting-code-review | obra/superpowers @ `22f0b46` | `skills/requesting-code-review/` | MIT | Sends a fresh-context reviewer over a step's git range before it is merged. |
| receiving-code-review | obra/superpowers @ `22f0b46` | `skills/receiving-code-review/` | MIT | Checks review feedback against the codebase instead of agreeing by reflex. |
| finishing-a-development-branch | obra/superpowers @ `22f0b46` | `skills/finishing-a-development-branch/` | MIT | Runs the suite, then asks the human whether to merge, open a PR or keep the branch. It never pushes on its own. |
| webapp-testing | anthropics/skills @ `e4bb5d9` | `skills/webapp-testing/` | Apache 2.0 | Playwright recon-then-act workflow for checking the Vite web app in a real browser. |
| mcp-builder | anthropics/skills @ `e4bb5d9` | `skills/mcp-builder/` | Apache 2.0 | MCP tool design, naming, annotations, errors and evals for the api's MCP server (FastMCP/Python guide included). |
| frontend-design | anthropics/skills @ `main` on 26 Nov 2026 | `skills/frontend-design/` | Apache 2.0 | Added 26 Nov 2026 at the user's request for the one-assistant and Modeler UI rework (`docs/agents/plans/10-unified-assistant-ux.md`). Guidance only, no scripts. Parity limit: it never changes a demo number or text, golden files or the extracted demo stylesheet; it works from the existing brand tokens. |
| web-interface-guidelines | vercel-labs/web-interface-guidelines @ `main` on 26 Nov 2026 | `AGENTS.md` (wrapped as `SKILL.md` with a front matter, text verbatim) | MIT | Added 26 Nov 2026 at the user's request: MUST/SHOULD/NEVER rules (keyboard, focus, forms, motion, dark mode) to build and review UI against. Guidance only; its `install.sh` was not used. |

## Rejected candidates

| Candidate | Source | Reason |
|---|---|---|
| executing-plans | obra/superpowers | Its bash scripts (`task-start`, `task-done`) call `../subagent-driven-development/scripts/*`, and it also requires `using-git-worktrees`, so it cannot run on its own. Bash is unreliable on this Windows host. |
| subagent-driven-development | obra/superpowers | Large bash-script machinery (workspace, ledger and brief scripts writing `.superpowers/`). It is heavy and fragile on Windows with Git Bash. |
| using-git-worktrees | obra/superpowers | It edits and commits `.gitignore` and runs installs in new worktrees. That fits poorly with Docker Compose in WSL and with the parallel-agent setup here. |
| brainstorming | obra/superpowers | An interactive design-dialogue workflow that writes specs under `docs/superpowers/`. `docs/**` is owned elsewhere, and the steps are already specified. |
| dispatching-parallel-agents, using-superpowers, writing-skills, diagnosing-superpowers | obra/superpowers | Meta skills for the superpowers plugin itself, or skill authoring. The user does not want new skills written. |
| skill-creator | anthropics/skills | The user does not want skills authored here. It is already available as a built-in plugin skill. Its scripts spawn nested `claude -p` runs and a local HTTP server. |
| web-artifacts-builder | anthropics/skills | Standalone artifact bundling. Not relevant (frontend-design was rejected here on 20 Nov for UI parity, then added on 26 Nov; see Installed). |
| claude-api | anthropics/skills | The LLM feature uses Groq, not the Claude API. |
| docx, pptx, xlsx, pdf, doc-coauthoring, internal-comms, brand-guidelines, theme-factory, canvas-design, algorithmic-art, slack-gif-creator, academy-guide, discernment-nudge | anthropics/skills | Document formats, art, brand or communications. Not relevant to this codebase. |
| "awesome-claude-skills" lists (ComposioHQ, travisvn, BehiSecc, hesreallyhim/awesome-claude-code) | various | These are link aggregators, not sources. The coding-workflow skills they recommend most are the superpowers and Anthropic ones above, so we took those from upstream. |

## Local changes

- `web-interface-guidelines/SKILL.md` = upstream `AGENTS.md` plus a front matter and one source line (26 Nov 2026).
- Third-party skills' licences and any compliance-sensitive agent behaviour should be reviewed by Kinective's Legal team before being relied on (research note `docs/agents/research/2026-11-ui-skills.md`).

- `mcp-builder/scripts/` was removed after install (20 Nov 2026): its evaluation script needs `ANTHROPIC_API_KEY` and sends the MCP server's tool results to an external API. The rest of the skill is verbatim; `reference/evaluation.md` still describes the removed script.

