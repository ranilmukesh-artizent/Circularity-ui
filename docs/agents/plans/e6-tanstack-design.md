# E6 design note: the read cache on TanStack Query, behind the same facade

Step E6 part 2 of [01b-refactor.md](01b-refactor.md) (finding W-03, also W-01). Written 20 Nov 2026, before the change.

## What exists today

`src/api/client.ts` has a home-grown read cache: a `Map<key, {data, error, promise, stale}>`.

- `cached(path)` and `cachedAction(id, input)` are called **during render** by the facade (`listCases()`,
  `navBadges()` …). They return the last answer at once. On a miss they throw the pending fetch, so React Suspense shows
  the fallback.
- `invalidate()` marks every entry stale. The next read starts a refetch and returns the old answer meanwhile
  (stale-while-revalidate). `bump()` (store.ts) then re-renders everything that called `useBackend()`. `App` calls it at
  the root and nothing is memoised, so every bump re-renders the whole mounted tree, and every answer on screen is read
  again.
- `retryFailed()` marks the failed entries stale (the error boundary's "Try again").
- `peek(path)` reads without suspending.
- Sign-in and sign-out call `clearCache()`.
- The stream (`connect()`) calls `invalidate()` once per burst of events (150 ms), and once when it reopens.

Gaps (W-01, W-03): nothing is ever evicted until sign-out. A failed read is never retried until someone presses
"Try again". There is no dedup beyond one promise per entry. Invalidation is all or nothing.

TanStack Query 5.62.7 (Dec 2024, older than 2 weeks) is already a dependency. `main.tsx` creates a `QueryClient` for
`StatusPage`'s `useQuery`. No new package is needed.

## Constraint: the facade stays synchronous

Pages call facade functions in render: in loops, conditionally, inside helpers. Those functions are not hooks, so
`useQuery`/`useSuspenseQuery` cannot be used. TanStack is used **imperatively** through one `QueryClient`, owned by
client.ts (main.tsx passes the same instance to `QueryClientProvider`). The facade's exports and their behaviour stay
as they are: `cached`, `cachedAction`, `peek`, `invalidate`, `retryFailed`, `withQuery`, `http`, `apiInvoke`, `ref`,
`login`, `logout`, `bootApi`, `onStream`. Pages see no change.

## Mapping

| Today | On TanStack |
|---|---|
| key `'GET ' + path` / `'ACT ' + id + json` | `queryKey: ['GET', path]` / `['ACT', id, input]`. The input object is hashed by TanStack's stable key hash, so property order no longer matters. |
| `readThrough` | `const q = cache.build(client, {queryKey, queryFn})`. If `q.state.data !== undefined`: when `q.isStaleByTime(Infinity)` / `q.state.isInvalidated` and no fetch is running, start `client.fetchQuery(...)` (it dedups) and return the data. Without data: an error and no fetch → throw the error; otherwise throw the in-flight promise. The promise thrown for a key is kept in a `WeakMap<Query, Promise>`, so repeated renders throw the same one. |
| `e.stale` | `state.isInvalidated` (`invalidateQueries({refetchType: 'none'})`). The refetch starts lazily on the next read, as today. A query has no observers, so TanStack's own `refetchType: 'active'` would never fire. |
| `bump()` when a fetch ends (only for the current entry) | `client.getQueryCache().subscribe(e => e.type === 'updated' && (e.action.type === 'success' \|\| e.action.type === 'error') && bump())`. Removed queries emit nothing, so a late answer from the previous session does not re-render. |
| `invalidate()` | `client.invalidateQueries({ refetchType: 'none' })`, then `bump()`. The old answers stay on screen while the reads refetch. |
| `retryFailed()` | `invalidateQueries({ predicate: q => q.state.status === 'error', refetchType: 'none' })`, then `bump()`. |
| `peek(path)` | `client.getQueryData(['GET', path])`. |
| `clearCache()` (sign-in, sign-out) | `client.clear()`. |
| stream bursts and reopen | unchanged: they call `invalidate()`. |
| `useBackend()` / `bump()` | unchanged: pages still re-render through store.ts, not through TanStack observers. |

## Retry (W-01)

Default options: `retry: (n, err) => n < 2 && err instanceof ApiError && (err.status === 0 || err.status >= 500)`,
`retryDelay: n => 500 * 2 ** n`. They are passed explicitly to every `fetchQuery` call, because `fetchQuery` does not
retry unless told to.

- Refusals (4xx: `tenant_boundary`, `out_of_scope`, `not_found` …) are not retried. The error boundary shows them at
  once, as today.
- Only an unreachable server or a 5xx is retried, twice (0.5 s, then 1 s). The boundary then shows the same text
  ("Could not reach the server …"), about 1.5 s later than today. This is the fix W-01 asks for, not a regression.
- `staleTime: Infinity`: an answer is fresh until it is invalidated, as today. Window-focus and reconnect refetches
  are off (`refetchOnWindowFocus: false`, `refetchOnReconnect: false`); the stream reopening already calls
  `invalidate()`.

## Eviction

TanStack's `gcTime` removes a query once it has had no observers for that long. Our queries never have observers, so
the default (5 min) would drop the data of a page that is still on screen. Its next render would suspend and flash
"Loading…", a visible change. So `gcTime: Infinity`, and eviction is done by client.ts:

- Every read records `lastRead` on the query (`query.meta` is read-only, so a `WeakMap<Query, number>`).
- After `invalidate()` has bumped, a sweep runs on a timer (1 s, after React's synchronous re-render). It removes the
  queries that are not fetching and were not read in the last 15 minutes (`client.removeQueries({ predicate })`).
- Why this cannot drop an answer on screen: `App` subscribes at the root and nothing is memoised, so the bump
  re-renders every mounted page, and its reads set `lastRead = now` before the sweep. A query that has not been read
  through 15 minutes of re-renders is not on screen. If a memoised subtree is added later, it must call
  `useBackend()` (that is already the rule for anything that reads the facade).
- No count cap: the 15-minute floor already bounds the cache to what was read in the last 15 minutes, and a cap that
  respects the floor could never drop anything more.
- `networkMode: 'always'`. TanStack's default (`online`) pauses fetches while `navigator.onLine` is false, which would
  leave a page on "Loading…" instead of showing the network error as today.
- A late answer for a query removed by sign-out does not re-render: the cache listener checks that the query is still
  in the cache.

## Scoped invalidation

`invalidate(match?: (key: readonly unknown[]) => boolean)`. With no argument it invalidates everything, as today, so
every caller keeps its behaviour. Uses follow, each in its own commit:

- a `workflow` stream event invalidates `GET /api/screens/workflows*`;
- a `sync` event invalidates `integration` reads.

These need the server's event kinds mapped to read paths. Until that mapping is tested on the parity routes, actions
and the stream keep invalidating everything. So this step adds the parameter and changes no caller.

## What stays the same for pages

- The same imports and signatures, synchronous reads, and Suspense on the first read. A refusal still reaches the
  error boundary as an `ApiError`.
- Stale-while-revalidate after actions and stream events: the old answers stay on screen, then the new ones render.
- "Try again" refetches only the failed reads.
- Sign-in and sign-out start from an empty cache, and nothing from the previous session renders.

## Tests (client.test.ts, and the new readCache.test.ts)

The existing cache tests in client.test.ts must pass: suspend then answer, stale-while-revalidate, refusal thrown,
retryFailed, cachedAction, logout clears. One expectation changes on purpose: a 500 is now retried twice, so the
retryFailed test counts four requests instead of two. New tests, in readCache.test.ts:

- a 503 is retried and then answers; a 403 is not retried;
- eviction removes an unread query after the sweep and keeps one read in the same tick;
- two reads of the same key during one fetch make one request;
- a scoped `invalidate(match)` leaves the other keys fresh;
- after `logout()`, a late answer from the old session does not populate the cache.

## Risks

- `client.ts` is owned by F3 (stream ticket) until it is committed. Part 2 starts only after the lead's go-ahead.
- The bundle: `@tanstack/query-core` is already in the vendor graph through `StatusPage`, but that page loads lazily.
  Moving it into client.ts puts query-core (~13 kB gzip) into the main chunk. Acceptable.
- Structural sharing (`structuralSharing: true`) keeps the old object for an equal subtree after a refetch. The facade
  never mutates cached answers (E1 removed the in-place sorts), so this only saves re-renders.
