import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { case_id: 'MR-1', kind: 'certification' }, key: null, action: 'service.book' })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { bookService, serviceProposal, type CaseRec } from './case';

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => m.invoke.mockClear());

describe('the service booking facade (plan 9, P9-11.7, MR-06)', () => {
  it('mr-06: bookService invokes service.book with the case, the tag, the kind and the date', async () => {
    await bookService('MR-1', 'SYN-MR-IP-0002', 'certification', '2026-12-07');
    expect(last()).toEqual(['service.book', { case_id: 'MR-1', asset_tag: 'SYN-MR-IP-0002', kind: 'certification', due_by: '2026-12-07' }]);
  });

  it('mr-06: the proposal is read off the case, null when the gate proposes none', () => {
    const input = { case_id: 'MR-1', asset_tag: 'SYN-MR-IP-0002', kind: 'certification' as const, due_by: '2026-12-07' };
    const c = { serviceCheck: { requests: [], proposed: { action: 'service.book', input } } } as unknown as CaseRec;
    expect(serviceProposal(c)).toEqual(input);
    expect(serviceProposal({ serviceCheck: { requests: [], proposed: null } } as unknown as CaseRec)).toBeNull();
    expect(serviceProposal({} as CaseRec)).toBeNull();
  });
});
