import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 'x' }, key: null, action: 'x' })),
  cached: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));

import {
  acceptProposal, fitModel, promoteModel, proposeModel, reasonText, registerAgent, rejectProposal, setLlmModel, stageLabel, startRun, updateAgent, useAgents, useModels,
} from './agents'; // prettier-ignore
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

  it('reads the Models panel (plan 8 UI gaps)', () => {
    m.cached.mockReturnValue({ models: [] });
    expect(useModels()).toEqual({ models: [] });
    expect(m.cached).toHaveBeenCalledWith('/api/screens/agents/models');
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
      [() => startRun('ext-a', 'RT-1048'), 'agent.startRun', { agent: 'ext-a', case_id: 'RT-1048', playbook: 'case_autopilot' }],
      [
        () => registerAgent({ id: 'ext-b', name: 'B', kind: 'external', tools: ['cases.list'], org_scope: [], autonomy: 'propose' }),
        'agent.register',
        { id: 'ext-b', name: 'B', kind: 'external', tools: ['cases.list'], org_scope: [], autonomy: 'propose' },
      ],
      [() => setLlmModel('groq-default', { enabled: false, priority: 2 }), 'llm.setModel', { id: 'groq-default', enabled: false, priority: 2 }],
      [() => fitModel(), 'model.fit', { template: 'industrial' }],
      [() => fitModel('device'), 'model.fit', { template: 'device' }],
      [() => proposeModel('MV-001'), 'model.propose', { id: 'MV-001' }],
      [() => promoteModel('MV-001'), 'model.promote', { id: 'MV-001' }],
    ];
    for (const [run, id, body] of cases) {
      await run();
      expect(last()).toEqual([id, body]);
    }
  });

  it('a stage chain run sends its playbook and the stage ids show in the D1 words (plan 9 P9-2.1)', async () => {
    await startRun('stage-intake', 'RT-1048', 'stage_chain');
    expect(last()).toEqual(['agent.startRun', { agent: 'stage-intake', case_id: 'RT-1048', playbook: 'stage_chain' }]);
    expect(stageLabel('fit_for_use')).toBe('Fit-for-use');
    expect(stageLabel('condition')).toBe('Condition and life');
    expect(stageLabel('somewhere_new')).toBe('somewhere_new');
  });

  it('the hold reasons read as one line (plan 9 P9-2.4)', () => {
    expect(reasonText([{ reason: 'value', detail: 'Value $900 is above the $600 limit' }])).toBe('Value $900 is above the $600 limit');
    expect(
      reasonText([
        { reason: 'value', detail: 'Value $900 is above the $600 limit' },
        { reason: 'confidence', detail: 'Confidence 0.62 is below 0.75' },
      ]),
    ).toBe('Value $900 is above the $600 limit · Confidence 0.62 is below 0.75');
    expect(reasonText([])).toBe('');
    expect(reasonText(undefined)).toBe('');
  });

  it('an agent change or a decided proposal refreshes every page', () => {
    for (const id of ['agent.update', 'agent.register', 'agent.startRun', 'proposal.accept', 'proposal.reject', 'model.fit', 'model.propose', 'model.promote', 'llm.setModel']) expect(actionScope(id)).toBe('all');
  });
});
