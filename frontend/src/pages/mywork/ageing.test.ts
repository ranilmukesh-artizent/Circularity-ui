import { describe, expect, it, vi } from 'vitest';
const m = vi.hoisted(() => ({
  invoke: vi.fn(async (id: string): Promise<unknown> => (id === 'flow.fork' ? { ok: true, output: { id: 9, flow_id: 9 } } : { ok: true, output: { id: 9 } })),
}));
vi.mock('../../api/actions', () => ({ invoke: m.invoke }));
import { acceptAgeingSuggestion, ageingSuggestions, type AgeingSuggestion } from '../../api/device';
import { ACCEPTED, ageingLine, blockedBy } from './ageing';

const s: AgeingSuggestion = {
  kind: 'offers_to_auction', from: 'offers', to: 'auction', days: 14, n: 12, value: 3840,
  listings: ['L-1'], text: 'Move 12 Offers listings to Auction: 14 days, no offer',
  rule: { action: 'require', path: 'auction', scope: { listChannel: ['offers'], listDaysMin: 14, offersMax: 0 } },
  proposal: { kind: 'rule', graph: { nodes: [], edges: [] } as never, rid: 'DR-02', guard: null, msg: '' },
};

describe('P9-6.13 ageingLine (DV-08)', () => {
  it('says the move, the days and the value', () => {
    expect(ageingLine(s)).toBe('Move 12 Offers listings to Auction: 14 days, no offer · $3,840');
  });
  it('says what happens on Accept: a draft that a different person approves', () => {
    expect(ACCEPTED).toBe('Added to your draft; a different person approves it');
  });
  it('shows why a blocked rule cannot be accepted', () => {
    expect(blockedBy(s)).toBeNull();
    expect(blockedBy({ proposal: { ...s.proposal, kind: 'blocked', msg: 'It breaks GR-D1.' } })).toBe('It breaks GR-D1.');
  });
});

describe('P9-6.13 the calls', () => {
  it('reads the org with the chosen days', async () => {
    await ageingSuggestions('Customer A', 21);
    expect(m.invoke.mock.calls.at(-1)).toEqual(['device.ageingSuggestions', { org_unit_id: 'Customer A', offers_days: 21 }]);
  });
  it("accepting is the person's own flow.saveDraft of the proposal graph", async () => {
    await acceptAgeingSuggestion(s, { flow_id: 3, flow_org: 'Customer A', org_unit_id: 'Customer A' });
    expect(m.invoke.mock.calls.at(-1)).toEqual([
      'flow.saveDraft',
      { flow_id: 3, graph: s.proposal.graph, source: 'assistant', note: 'Ageing suggestion: ' + s.text },
    ]);
  });
  it('forks the flow the org inherits before it saves the draft', async () => {
    await acceptAgeingSuggestion(s, { flow_id: 1, flow_org: 'workspace', org_unit_id: 'Customer A' });
    const ids = m.invoke.mock.calls.slice(-2).map((c) => c[0]);
    expect(ids).toEqual(['flow.fork', 'flow.saveDraft']);
    expect((m.invoke.mock.calls.at(-1) as unknown[])[1]).toMatchObject({ flow_id: 9 });
  });
});
