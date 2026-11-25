import { describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  cached: vi.fn((): unknown => ({
    agents: [{ agent: 'a1', name: 'A one', tools: [{ tool: 'case_evidence', action: 'case.evidence', read_only: true, destructive: false, needs_person: false }] }],
  })),
}));
vi.mock('./client', () => ({ cached: m.cached, accessToken: () => null, invalidate: vi.fn(), ref: vi.fn(), withQuery: (p: string) => p }));
vi.mock('./actions', () => ({ actionCatalog: () => [] }));

import { generatedTools } from './mcp';

describe('generated MCP tools (plan 9, P9-2.13)', () => {
  it('reads the per-agent tools and their hints from the screens endpoint', () => {
    const g = generatedTools();
    expect(m.cached).toHaveBeenCalledWith('/api/screens/mcp/generated');
    expect(g[0].tools[0]).toEqual({ tool: 'case_evidence', action: 'case.evidence', read_only: true, destructive: false, needs_person: false });
  });
});
