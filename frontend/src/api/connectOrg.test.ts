import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn(async () => ({ ok: true, output: {}, key: null, action: 'x' })) }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { connectFromCatalog } from './integration';
import { defaultConnectOrg, type OrgUnitRow } from './orgs';

beforeEach(() => m.invoke.mockClear());
const call = () => m.invoke.mock.calls[0] as unknown as [string, Record<string, unknown>];

const units: OrgUnitRow[] = [
  { id: 'workspace', parent_id: null, kind: 'group', name: 'Workspace', depth: 0 },
  { id: 'Customer A', parent_id: 'workspace', kind: 'customer', name: 'Customer A', depth: 1 },
];

describe("the Connect dialog's org unit (plan 8 UI gaps)", () => {
  it('a chosen org unit is sent with the connection', async () => {
    await connectFromCatalog('postgres', 'key', ['read'], [], undefined, 'Customer A');
    expect(call()).toEqual(['source.update', { mode: 'catalog', id: '', d: { catalog: 'postgres', auth: 'key', scopes: ['read'] }, maps: [], ops: {}, org_unit_id: 'Customer A' }]);
  });

  it('no org unit sends no field, as before (the source is shared)', async () => {
    await connectFromCatalog('postgres', 'key', ['read'], [], undefined, '');
    expect(call()[1]).not.toHaveProperty('org_unit_id');
  });

  it("the default is the top bar's tenant when the account sees it, else shared", () => {
    expect(defaultConnectOrg(units, 'All')).toBe('');
    expect(defaultConnectOrg(units, 'Customer A')).toBe('Customer A');
    expect(defaultConnectOrg(units, 'Customer B')).toBe('');
  });
});