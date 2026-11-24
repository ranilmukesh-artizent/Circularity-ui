import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn(async () => ({ ok: true, output: {}, key: null, action: 'x' })) }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { saveSource, type Draft } from './integration';

const d: Draft = { type: 'erp', name: 'ERP', vendor: 'V', ver: '', env: 'Production', url: '', method: 'api', cfg: {}, interval: 0, auth: 'OAuth 2.0', owner: '' };
const ops = { read: ['a'], write: [] };

beforeEach(() => m.invoke.mockClear());

describe("a source's org unit (audit U6 follow-up)", () => {
  it('the Source drawer sends org_unit_id only when it changes it; empty means shared by every org (null)', async () => {
    await saveSource('edit', 'erp', d, [], ops);
    expect((m.invoke.mock.calls[0] as unknown as [string, Record<string, unknown>])[1]).not.toHaveProperty('org_unit_id');
    m.invoke.mockClear();
    await saveSource('edit', 'erp', d, [], ops, 'Customer A');
    expect(m.invoke.mock.calls[0]).toEqual(['source.update', { mode: 'edit', id: 'erp', d, maps: [], ops, note: '', org_unit_id: 'Customer A' }]);
    m.invoke.mockClear();
    await saveSource('edit', 'erp', d, [], ops, '');
    expect((m.invoke.mock.calls[0] as unknown as [string, Record<string, unknown>])[1].org_unit_id).toBeNull();
  });
});
