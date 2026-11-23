import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ cached: vi.fn() }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));
vi.mock('./view', () => ({ view: () => ({ tenant: 'All' }) }));

import { analyticsOrgs, analyticsRows, DEFAULT_FILTER } from './analytics';

const orgs = [
  { id: 'workspace', name: 'Workspace', kind: 'group', depth: 0 },
  { id: 'Customer A', name: 'Customer A', kind: 'customer', depth: 1 },
];
const answer = { rows: [], metrics: {}, model_stats: [], telemetry_unavailable: true, orgs };

beforeEach(() => {
  m.cached.mockReset();
  m.cached.mockReturnValue(answer);
});

describe('analytics org roll-up (plan 8 MVP-10.1)', () => {
  it('the default filter asks for no org: the demo request', () => {
    analyticsRows(DEFAULT_FILTER);
    expect(m.cached).toHaveBeenCalledWith('/api/screens/analytics?from=0&to=11&tenant_filter=All');
  });

  it('an org in the filter narrows the request to its subtree', () => {
    analyticsRows({ ...DEFAULT_FILTER, org: 'Customer A' });
    expect(m.cached).toHaveBeenCalledWith('/api/screens/analytics?from=0&to=11&org=Customer+A&tenant_filter=All');
  });

  it("the org select lists the answer's units", () => {
    expect(analyticsOrgs()).toEqual(orgs);
  });
});
