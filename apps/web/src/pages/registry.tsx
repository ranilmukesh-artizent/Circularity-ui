import type { ComponentType } from 'react';
import type { RouteRef } from '../api/types';

export interface PageProps {
  route: RouteRef; // #/page/a/b
  query: URLSearchParams; // #/page/a?focus=RT-1048
}

/**
 * Each area folder has an index.tsx that exports `pages`: top-level page id (the first path segment) → component.
 * A page renders all of its own sections. Registration is automatic, so areas never edit a shared file.
 *
 *   // src/pages/command/index.tsx
 *   export const pages = { command: CommandCenterPage };
 */
const modules = import.meta.glob<{ pages?: Record<string, ComponentType<PageProps>> }>('./*/index.tsx', { eager: true });

// Built on first use, not at import time: page modules may import this file back (for PageProps or helpers),
// and in that cycle their `pages` export is not initialised yet when this module first runs.
let built: Record<string, ComponentType<PageProps>> | null = null;
export function pageFor(id: string): ComponentType<PageProps> | undefined {
  if (!built) {
    built = {};
    for (const [file, m] of Object.entries(modules)) {
      for (const [pid, page] of Object.entries(m.pages ?? {})) {
        if (built[pid]) console.warn(`[pages] "${pid}" registered twice (${file})`);
        built[pid] = page;
      }
    }
  }
  return built[id];
}
