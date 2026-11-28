import { describe, expect, it, vi } from 'vitest';

vi.mock('./view', () => ({ view: () => ({ tenant: 'Customer A' }) }));

import { DEFAULT_FILTER } from './analytics';
import { rowsPath } from './analyticsRows';

describe('rows query', () => {
  it('names the figure that was opened and the top bar tenant, and leaves empty filters out', () => {
    expect(rowsPath({ source: 'cases', chart: 'age', key: 'band:0-7|route:redeploy' })).toBe(
      '/api/screens/analytics/rows?source=cases&chart=age&key=band%3A0-7%7Croute%3Aredeploy&tenant_filter=Customer+A',
    );
  });
  it('carries the page filters, sort, search and page', () => {
    const p = rowsPath({ source: 'decisions', chart: 'flow', key: 'all', filter: { ...DEFAULT_FILTER, cls: 'pump', from: 2, to: 5 }, sort: 'actual', dir: 'desc', q: ' RT-10 ', limit: 50, offset: 100 });
    expect(p).toContain('cls=pump');
    expect(p).toContain('from=2&to=5');
    expect(p).toContain('sort=actual&dir=desc&q=RT-10&limit=50&offset=100');
  });
  it('asks for the CSV of the same selection, with no paging', () => {
    const p = rowsPath({ source: 'cases', chart: 'age', key: 'all', limit: 50, offset: 50, sort: 'net' }, true);
    expect(p.startsWith('/api/screens/analytics/rows.csv?')).toBe(true);
    expect(p).not.toContain('limit');
    expect(p).toContain('sort=net');
  });
});
