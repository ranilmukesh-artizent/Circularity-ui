# Writer C, section E: markdown in every assistant answer (28 Nov 2026)

## Install state and what I did
- Found: `frontend/package.json` had `react-markdown` 10.1.0 and `remark-gfm` 4.0.1 (exact); the lockfile already carried them.
- The `web` container uses a named volume for `/app/node_modules` (`docker-compose.yml`: `web_node_modules`), and both packages were already in it (versions 10.1.0 and 4.0.1; a dynamic `import()` of both succeeds in the container).
- The host `frontend/node_modules` lacked them. I ran `npm install --no-audit --no-fund --ignore-scripts` in `frontend/` (host Node 26.12.1): "added 94 packages", lockfile unchanged by it. Both now resolve on the host too. No container rebuilt or restarted. No other package added.
- The lockfile diff against HEAD is large (1517 insertions, 75 deletions) because of the unified/remark dependency tree; I did not touch it.

## How the answer arrives (E3)
It grows while it streams: `turns.ts` `applyAskEvent` appends each `delta` event to `data.text`; the `final` event replaces it with the full text (and a `reset` clears it). So the component gets partial text. `final` being null is the "still arriving" signal, passed as `streaming`.

## Component
- `Markdown` (`<Markdown text streaming? />`), `React.memo`, react-markdown + remark-gfm (`singleTilde: false`, so "~5 days to ~8" is not struck through). No rehype-raw, no `dangerouslySetInnerHTML`. Raw HTML is shown as escaped text (not dropped, so a model's `<customer_id>` placeholder stays readable).
- Links: `safeHref` keeps `http`, `https`, `mailto`, `#/…` (checks the form with control characters and whitespace removed, so `java\nscript:` fails). External: `target="_blank" rel="noopener noreferrer"`; hash links stay in the tab; everything else renders as its text. Images: never loaded, alt text as a link to the source (plain alt text when the source is not allowed).
- Headings: h1/h2 become `h3`, h3 `h4`, h4 to h6 `h5` (class `md-h`, small sizes).
- Tables in a focusable scroll region (`role="region"`, label "Table"); code blocks with a bar (language, Copy button, "Copied" for 1.6 s, `aria-live="polite"` status), scrollable focusable `pre`; the bar is always present, so nothing shifts when a block arrives. Task-list checkboxes are disabled with an accessible label.
- `settle(text)` (pure, `markdownText.ts`), applied only while streaming: holds back a lone list/heading/quote marker, one or two backticks, a table with no matching delimiter row yet, closes an open `**`, backtick or link URL, drops a trailing emphasis marker. Text in an open code fence is untouched (the renderer closes the fence itself). A finished answer is never settled, so final wording is unchanged.
- Error boundary falls back to the plain text (`md-plain`), and retries when the text changes.
- `markdown.css`: tokens only (`--ink`, `--ink2`, `--muted`, `--line`, `--line2`, `--panel*`, `--f-display`, `--f-mono`); type scale of `panel.css`; first/last child margin 0; `overflow-wrap: anywhere`; tabular numbers in tables; no new colours, shadows, gradients, emoji or all-caps.

## Surfaces found
Converted (free model prose):
1. Assistant dock and Modeler pinned column (one `AskTurn`): `layout/assistant/modes/ask.tsx` answer text, streaming and final, including the rule-based fallback answers (same wording).
2. Agent run view reading summary: `pages/agents/RunView.tsx` (`reading.summary`).
3. Journey timeline reading summary: `pages/agents/JourneyTimeline.tsx`.
4. Case Decide tab "Drafted rationale": `pages/case/tabs/DecideTabs.tsx` (`c.packet.rationale`).
5. Mapping suggestions reason, only when `proposed_by === 'model'` (rule and memory reasons stay plain): `pages/integration/MappingSuggestions.tsx`.

Looked at, not converted:
- `ChangeTurn.tsx`, `PreviewCard.tsx`, `SetupMode.tsx`: all text there is rule-built or structured (match lines, counts, change-set lines), not free model prose. What the person typed (`as-user`) stays plain.
- Short structured fields (reading findings and concerns, `run.reason`, validation lines): short rule/structured strings; left plain.
- Not mine, name only: `pages/workflows/WorkflowBuilder.tsx` (workflow draft reply and `RedirectNote`, another writer's file), `pages/modeler/compose/*` (reading and description text, another writer), `pages/setup/**`.

## Files
- New: `frontend/src/components/Markdown.tsx`, `markdown.css`, `markdownText.ts`, `Markdown.test.tsx`.
- Edited (one line plus an import each): `layout/assistant/modes/ask.tsx` (replaced `<div className="as-text">`), `pages/agents/RunView.tsx`, `pages/agents/JourneyTimeline.tsx`, `pages/case/tabs/DecideTabs.tsx`, `pages/integration/MappingSuggestions.tsx`. `frontend/package.json` and lockfile already carried the two packages.

## Checks
- `docker compose exec -T web npx vitest run src/components src/layout/assistant`: `Test Files 17 passed (17)`, `Tests 128 passed (128)`.
- `docker compose exec -T web npx tsc --noEmit -p .`: no output, exit 0 (so no type errors in other writers' files at that moment).
- Extra, cheap: `npx vitest run src/pages/agents src/pages/integration src/pages/case`: 45 files, 286 tests passed. `eslint` on my files and the edited ones: clean except `MappingSuggestions.tsx:104` (`jsx-a11y/no-noninteractive-tabindex`), which is older code, not my change.

## Tests (Markdown.test.tsx)
Headings, nested list, GFM table, inline and block code, link attributes; script, `<img onerror>` and `javascript:` link produce no element or `on*` attribute; sample answer truncated at every length, streaming and not, never throws or hits the fallback; one-line text is one paragraph with the same text; `settle` cases; `safeHref` cases.

## Not done or unsure
- Not seen in a browser (not allowed); the CSS is unchecked at 360 px, in dark mode and on a phone. The `.as-text` rule in `panel.css` is now unused by `ask.tsx` (left in place).
- `settle` does not handle every unfinished construct (for example an unclosed `_emphasis_` or an unclosed nested list level); these simply show as raw characters until closed.
- `li:has(> input[type=checkbox])` in the CSS relies on `:has()` (fine in current browsers).
- Plan 11 text says "links open in a new tab"; in-app `#/…` links stay in the same tab, as the brief asked.
