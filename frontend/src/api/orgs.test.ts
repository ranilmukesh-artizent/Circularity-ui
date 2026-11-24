import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async () => ({ ok: true, output: { id: 'x' }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', () => ({ cached: m.cached }));

import { actionScope, matcher } from './invalidation';
import {
  createOrg, exportPack, flatten, importPack, moveOrg, packFileName, parsePack, pilotPath, previewPack, renameOrg, setPilot,
  useOrgTree, useOrgUnits, usePilotReport, type OrgNode, type OrgPack,
} from './orgs';

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

const pack: OrgPack = { version: 1, org: { id: 'Customer A', parent_id: 'workspace', kind: 'customer', name: 'Customer A' }, sources: [], mappings: {}, workflows: [], flows: {} };

describe('org screens (plan 8 UI gaps)', () => {
  it('units and the pilot report are screen reads', () => {
    const screen = { units: [], can: { manage: true, report: true } };
    m.cached.mockReturnValue(screen);
    expect(useOrgUnits()).toBe(screen);
    expect(m.cached).toHaveBeenCalledWith('/api/screens/orgs');
    usePilotReport('Customer A');
    expect(m.cached).toHaveBeenLastCalledWith('/api/screens/orgs/Customer%20A/pilot');
    expect(pilotPath('a/b')).toBe('/api/screens/orgs/a%2Fb/pilot');
  });

  it('pilot mode and the pack go to their server actions', async () => {
    await setPilot('Customer A', true);
    expect(call()).toEqual(['org.setPilot', { org_unit_id: 'Customer A', on: true }]);
    m.invoke.mockClear();
    await exportPack('Customer A');
    expect(call()).toEqual(['org.exportPack', { org_unit_id: 'Customer A' }]);
    m.invoke.mockClear();
    await previewPack(pack, 'Customer B');
    expect(call()).toEqual(['org.previewPack', { pack, target_org_unit_id: 'Customer B' }]);
    m.invoke.mockClear();
    await importPack(pack, 'Customer B');
    expect(call()).toEqual(['org.importPack', { pack, target_org_unit_id: 'Customer B' }]);
  });

  it('pilot mode and an import refresh every cached read, the org screens included', () => {
    for (const id of ['org.setPilot', 'org.importPack']) {
      const match = matcher(actionScope(id));
      expect(match === undefined || (match !== null && match(['GET', '/api/screens/orgs']))).toBe(true);
    }
  });

  it('parsePack takes a pack and refuses other files', () => {
    expect(parsePack(JSON.stringify(pack))).toEqual({ pack });
    expect(parsePack('not json')).toEqual({ error: 'The file is not JSON.' });
    expect(parsePack('[1]')).toEqual({ error: 'The file is not an org configuration pack.' });
    expect(parsePack('{"version": 1}')).toEqual({ error: 'The file is not an org configuration pack.' });
  });

  it('packFileName is a safe file name', () => {
    expect(packFileName('Customer A')).toBe('org-pack-customer-a.json');
    expect(packFileName('!!')).toBe('org-pack-org.json');
  });
});