import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 'x' }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));

import { acceptProposal, rejectProposal, updateAgent, useAgents } from './agents';
import { actionScope } from './invalidation';

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => {
  m.invoke.mockClear();
  m.cached.mockReset();
});

describe('the Agents facade (plan 8 MVP-11.8)', () => {
  it('reads the Agents screen', () => {
    m.cached.mockReturnValue({ agents: [] });
    expect(useAgents()).toEqual({ agents: [] });
    expect(m.cached).toHaveBeenCalledWith('/api/screens/agents');
  });

  it('each write invokes its action with its body', async () => {
    const cases: [() => Promise<unknown>, string, Record<string, unknown>][] = [
      [() => updateAgent('ext-a', { enabled: false }), 'agent.update', { id: 'ext-a', enabled: false }],
      [() => updateAgent('ext-a', { autonomy: 'read' }), 'agent.update', { id: 'ext-a', autonomy: 'read' }],
      [
        () => updateAgent('ext-a', { tools: ['get_case_evidence'], org_scope: ['Customer A'] }),
        'agent.update',
        { id: 'ext-a', tools: ['get_case_evidence'], org_scope: ['Customer A'] },
      ],
      [() => acceptProposal(4), 'proposal.accept', { id: 4 }],
      [() => rejectProposal(4, 'Not for this case.'), 'proposal.reject', { id: 4, reason: 'Not for this case.' }],
    ];
    for (const [run, id, body] of cases) {
      await run();
      expect(last()).toEqual([id, body]);
    }
  });

  it('an agent change or a decided proposal refreshes every page', () => {
    for (const id of ['agent.update', 'proposal.accept', 'proposal.reject']) expect(actionScope(id)).toBe('all');
  });
});
