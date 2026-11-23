import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async () => ({ ok: true, output: { id: 'x' }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', () => ({ cached: m.cached }));

import { actionScope, matcher } from './invalidation';
import { createOrg, flatten, moveOrg, renameOrg, useOrgTree, type OrgNode } from './orgs';

beforeEach(() => {
  m.invoke.mockClear();
  m.cached.mockReset();
});
const call = () => m.invoke.mock.calls[0] as unknown as [string, Record<string, unknown>];

const tree: OrgNode[] = [
  {
    id: 'workspace', parent_id: null, kind: 'group', name: 'Workspace',
    children: [
      { id: 'Customer A', parent_id: 'workspace', kind: 'customer', name: 'Customer A', children: [] },
      {
        id: 'East', parent_id: 'workspace', kind: 'group', name: 'East',
        children: [{ id: 'Sub Co', parent_id: 'East', kind: 'company', name: 'Sub Co', children: [] }],
      },
    ],
  },
]; // prettier-ignore

describe('org units', () => {
  it('create, move and rename go to their server actions with their bodies', async () => {
    await createOrg({ id: 'Sub Co', parent_id: 'East', kind: 'company', name: 'Sub Co' });
    expect(call()).toEqual(['org.create', { id: 'Sub Co', parent_id: 'East', kind: 'company', name: 'Sub Co' }]);
    m.invoke.mockClear();
    await moveOrg('Sub Co', 'workspace');
    expect(call()).toEqual(['org.move', { id: 'Sub Co', parent_id: 'workspace' }]);
    m.invoke.mockClear();
    await renameOrg('Sub Co', 'Sub Company');
    expect(call()).toEqual(['org.update', { id: 'Sub Co', name: 'Sub Company' }]);
  });

  it("the tree is the Access page's orgs section (read cache)", () => {
    m.cached.mockReturnValue({ sections: ['orgs'], orgs: { units: tree } });
    expect(useOrgTree()).toBe(tree);
    expect(m.cached).toHaveBeenCalledWith('/api/screens/access');
  });

  it('a write invalidates the cached Access page, and so the tree', () => {
    for (const id of ['org.create', 'org.move', 'org.update']) {
      const match = matcher(actionScope(id));
      expect(match === undefined || (match !== null && match(['GET', '/api/screens/access']))).toBe(true);
    }
  });

  it('flatten lists every unit depth first with its depth', () => {
    expect(flatten(tree).map(({ node, depth }) => [node.id, depth])).toEqual([
      ['workspace', 0], ['Customer A', 1], ['East', 1], ['Sub Co', 2],
    ]); // prettier-ignore
  });
});
