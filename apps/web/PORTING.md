# Porting a screen from the demo (fixtures/demo/index.html) to React

The React app reproduces the static demo (`fixtures/demo/index.html`) screen by screen. The demo stays the specification until a screen is ported.

## How the app is built

| Layer | Where | Rule |
|---|---|---|
| Backend | `di-api` (`apps/api`) | Each area's screen endpoints (`/api/screens/<area>`) serve what the pages show; their docstrings map the facade exports |
| API facade | `src/api/*.ts` | Typed, synchronous functions over di-api through the Suspense read cache in `src/api/client.ts`. Each area has its own file (`src/api/product.ts`, `src/api/integration.ts` …) |
| Changes | `invoke(actionId, input)` in `src/api/actions.ts` | Every state change is `POST /api/actions/{id}` (permission, tenant and warehouse scope, guards, idempotency, journal). Never mutate cached answers from a page |
| Re-render | `useBackend()` in `src/api/hooks.ts` | Call it at the top of every page component; it re-renders after any action |
| Access | `can()`, `canPage()` in `src/api/session.ts` | Hide what the role may never use (the demo removes those controls; it does not grey them out) |
| Look | `src/styles/legacy.gen.css` is the demo's whole stylesheet | **Use the demo's class names and DOM structure**, so the CSS applies unchanged. No new CSS unless something cannot be expressed with existing classes; put it in your area folder as a `.css` file |
| Shared UI | `src/ui/` | `Icon` (the demo's icon set by key), `Drawer`, `Modal`, `toast()`, `useTheme()`. Formatters in `src/api/format.ts` |
| Pages | `src/pages/<area>/` | One folder per area. Its `index.tsx` exports `pages` (page id → component); `src/pages/registry.tsx` picks it up automatically |

## Reading the demo

- Each screen is a function that returns an HTML string (`renderCommand(r)`, `renderProduct(r)` …). Later layers **wrap** those functions, for example `const rt0=route;route=function(){…}` or `renderIntegration=function(){…}`. The **last** override is what the demo shows, because the revamp (`FR_ON`), stage pages (`ST_ON`) and CXO screens (`CX_ON`) are all on by default. Search for every assignment to the function name.
- Buttons use `data-act="name"` with handlers in `ACT.name`. A handler that changes state calls `invoke('some.action', …)`; port it as an `onClick` that calls `invoke` through `src/api/actions.ts` and shows the result with `toast()`.
- `S` is the demo's UI state object. View-only state (open tab, filters, sort) becomes React state; anything the demo persists in `localStorage` may keep the same key.
- Helpers the page needs (for example `asModel(c)`, `afPriority(c)`, `ccLayout()`) become typed functions in your area's `src/api/<area>.ts` over what di-api answers: the area's screen endpoint through `cached(path)`, the demo's static lists through `ref('NAME')` (both in `src/api/client.ts`). There is no in-browser engine; when the page needs data no endpoint serves yet, add it to the area's screen endpoint in `apps/api/di/screens/`. Prefer the read actions (`case.get`, `cases.list`, `analytics.query` …; list them with `actionCatalog()`) where they return what the page needs.

## Checking your work

```sh
npm run typecheck
npx vite --port <your port> --strictPort        # in the background
BASE_URL=http://localhost:<port>/ node e2e/shot.mjs <outDir> approver product/received   # screenshot, signed in
```

Open the same route in the static demo to compare (`fixtures/demo/index.html#/product/received`).
