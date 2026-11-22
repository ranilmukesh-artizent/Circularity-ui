// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import type { AuditEntry } from '../../api/audit';

/** The cached answer the facade hands out: the same array on every read, shared by every page that reads it. */
const m = vi.hoisted(() => ({ entries: [] as AuditEntry[] }));
vi.mock('../../api/audit', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/audit')>()),
  auditEntries: () => m.entries,
}));

import { filtered } from './AuditPage';

const entry = (id: string, t: number) => ({ id, ts: new Date(t), kind: 'fetch', caseId: 'RT-1', asset: '', item: '', source: 'ERP', request: '', used: '' }) as AuditEntry;
const NONE = { q: '', src: '', type: '', status: '', limit: 40, prep: false };
describe('audit log order', () => {
  it('sorts a copy, never the cached array', () => {
    m.entries = [entry('b', 2), entry('a', 1), entry('c', 3)];
    const cached = m.entries, before = [...cached];
    expect(filtered({ ...NONE, dir: -1 }).map((x) => x.id)).toEqual(['c', 'b', 'a']);
    expect(filtered({ ...NONE, dir: 1 }).map((x) => x.id)).toEqual(['a', 'b', 'c']);
    expect(cached).toEqual(before); // the cache keeps the server's order
    expect(filtered({ ...NONE, dir: 1 })).not.toBe(cached);
  });
});
