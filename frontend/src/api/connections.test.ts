import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 1 }, key: null, action: 'x' })),
  read: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke, read: m.read }));

import { actionScope } from './invalidation';
import {
  connectionApprovals, createConnection, discoverConnection, ownerApprove, ownerDecline, promoteConnection, registryEntries, requestOwner,
} from './connections'; // prettier-ignore

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => {
  m.invoke.mockClear();
  m.read.mockReset();
});

describe('the adapter registry facade (plan 9, P9-8.1, X-10)', () => {
  it('x-10: registryEntries reads registry.list, by kind when given', () => {
    m.read.mockReturnValue({ entries: [{ id: 'workday', kind: 'catalogue' }] });
    expect(registryEntries()).toEqual([{ id: 'workday', kind: 'catalogue' }]);
    expect(m.read).toHaveBeenLastCalledWith('registry.list', {});
    registryEntries('generic_rest');
    expect(m.read).toHaveBeenLastCalledWith('registry.list', { kind: 'generic_rest' });
  });

  it('x-10: createConnection sends the entry, the owner and the org, and the secret only when typed', async () => {
    await createConnection({ registryId: 'workday', version: 1, name: 'Workday test', orgUnitId: 'Customer A', systemOwner: 'approver' });
    expect(last()).toEqual(['connection.create', { registry_id: 'workday', version: 1, name: 'Workday test', org_unit_id: 'Customer A', system_owner: 'approver' }]);
    await createConnection({ registryId: 'generic-rest', version: 1, name: 'Parts', orgUnitId: 'Customer A', systemOwner: 'approver', testBaseUrl: 'https://t.example/api', auth: 'api_key', secret: 'abcdefgh' });
    expect(last()[1]).toMatchObject({ test_base_url: 'https://t.example/api', auth: 'api_key', secret: 'abcdefgh' });
  });

  it('x-10: each write invokes its action with its body', async () => {
    await requestOwner('workday', 'production', 'read');
    expect(last()).toEqual(['connection.requestOwner', { source_id: 'workday', environment: 'production', access: 'read' }]);
    await requestOwner('workday', 'production', 'read_write', 'Instructions to Workday');
    expect(last()[1]).toMatchObject({ access: 'read_write', note: 'Instructions to Workday' });
    await ownerApprove(7);
    expect(last()).toEqual(['connection.ownerApprove', { id: 7 }]);
    await ownerDecline(7, 'Not before the audit.');
    expect(last()).toEqual(['connection.ownerDecline', { id: 7, reason: 'Not before the audit.' }]);
    await promoteConnection('workday', 'prod-key-98765');
    expect(last()).toEqual(['connection.promote', { source_id: 'workday', secret: 'prod-key-98765' }]);
  });

  it('x-10: connectionApprovals is a read per source, and a write refreshes every read', () => {
    m.read.mockReturnValue({ approvals: [] });
    connectionApprovals('workday');
    expect(m.read).toHaveBeenCalledWith('connection.approvals', { source_id: 'workday' });
    expect(actionScope('connection.ownerApprove')).toBe('all');
  });

  it('p9-8.3: discoverConnection invokes connection.discover and a sample refreshes every read', async () => {
    await discoverConnection('parts-api');
    expect(last()).toEqual(['connection.discover', { source_id: 'parts-api' }]);
    expect(actionScope('connection.discover')).toBe('all');
  });
});
