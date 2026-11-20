import { lazy, type ComponentType } from 'react';
import type { RouteRef } from '../api/types';

export interface PageProps {
  route: RouteRef; // #/page/a/b
  query: URLSearchParams; // #/page/a?focus=RT-1048
}

type Page = ComponentType<PageProps>;

/**
 * Each area folder has an index.tsx that exports `pages`: top-level page id (the first path segment) → a loader that
 * imports the page module. A page renders all of its own sections. Registration is automatic, so areas never edit a
 * shared file.
 *
 *   // src/pages/command/index.tsx
 *   export const pages = { command: () => import('./CommandCenterPage').then((m) => m.CommandCenterPage) };
 *
 * The index files are tiny and loaded eagerly, so `pageFor` knows synchronously which ids exist (an unknown id falls
 * back to NotPortedPage in App). The pages themselves are dynamic imports: each becomes its own chunk, fetched the
 * first time the page renders. App renders every page inside <Boundary> (Suspense + error boundary).
 */
const modules = import.meta.glob<{ pages?: Record<string, () => Promise<Page>> }>('./*/index.tsx', { eager: true });

// Built on first use, not at import time, and each id wrapped in React.lazy once so its identity is stable across
// renders (a new lazy component per render would remount the page and refetch the chunk).
let built: Record<string, Page> | null = null;
export function pageFor(id: string): Page | undefined {
  if (!built) {
    built = {};
    for (const [file, m] of Object.entries(modules)) {
      for (const [pid, load] of Object.entries(m.pages ?? {})) {
        if (built[pid]) console.warn(`[pages] "${pid}" registered twice (${file})`);
        built[pid] = lazy(() => load().then((page) => ({ default: page })));
      }
    }
  }
  return built[id];
}
