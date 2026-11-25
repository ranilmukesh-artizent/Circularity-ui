import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 'x' }, key: null, action: 'x' })),
  cached: vi.fn(),
  read: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke, read: m.read }));
vi.mock('./client', async (orig) => ({ ...(await orig<typeof import('./client')>()), cached: m.cached }));

import {
  acceptProposal, findTools, fitModel, fitStageCalibration, promoteModel, proposeModel, reasonText, registerAgent, rejectProposal, runTrace, setAgentEnabled, setLlmModel, spanRows, spanTree, stageCalibrationOf, stageLabel, startRun, updateAgent, useAgents, useModels,
  type TraceSpan,
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

  it('names the pack and stage of a stage calibration model (P9-2.9)', () => {
    expect(stageCalibrationOf('industrial.stage.fit_for_use')).toEqual({ pack: 'industrial', stage: 'fit_for_use' });
    expect(stageCalibrationOf('industrial')).toBeNull();
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
      [() => fitStageCalibration('industrial', 'disposition'), 'stage.fitCalibration', { pack: 'industrial', stage: 'disposition' }],
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

  it('the run view reads one run or the latest on a case, with its spans nested (plan 9 P9-2.6)', () => {
    const sp = (span_id: string, parent_id: string | null, kind: TraceSpan['kind']): TraceSpan => ({
      span_id, trace_id: 'AR-1', parent_id, name: kind, kind, started_at: '2026-11-25T10:00:00Z', ended_at: '2026-11-25T10:00:02Z', status: 'ok', attrs: {}, children: [],
    });
    m.read.mockReturnValue({ run: null, spans: [sp('a', null, 'run'), sp('b', 'a', 'model'), sp('c', 'b', 'tool')] });
    const t = runTrace({ caseId: 'RT-1048' });
    expect(m.read).toHaveBeenLastCalledWith('agent.runTrace', { case_id: 'RT-1048' });
    expect(runTrace({ runId: 'AR-1' })).toBeTruthy();
    expect(m.read).toHaveBeenLastCalledWith('agent.runTrace', { run_id: 'AR-1' });
    expect(t.spans).toHaveLength(1);
    expect(t.spans[0].children[0].children[0].kind).toBe('tool'); // the tool span sits under its model span
  });

  it('the span-tree helper nests a tool span under its model span, flat or already nested (plan 9 P9-2.6)', () => {
    const mk = (span_id: string, parent_id: string | null, kind: TraceSpan['kind']): TraceSpan => ({
      span_id, trace_id: 't', parent_id, name: kind, kind, started_at: '2026-11-25T10:00:00Z', ended_at: '2026-11-25T10:00:01Z', status: 'ok', attrs: {}, children: [],
    });
    const flat = [mk('m', null, 'model'), mk('t', 'm', 'tool'), mk('lost', 'gone', 'action')];
    const tree = spanTree(flat);
    expect(tree.map((s) => s.span_id)).toEqual(['m', 'lost']);
    expect(tree[0].children.map((s) => s.kind)).toEqual(['tool']);
    expect(spanTree(tree)).toEqual(tree);
    expect(spanRows(tree).map((r) => [r.span.span_id, r.depth])).toEqual([['m', 0], ['t', 1], ['lost', 0]]);
  });

  it('Pause agent calls the journaled kill switch (plan 9 P9-2.6)', async () => {
    await setAgentEnabled('stage-intake', false);
    expect(last()).toEqual(['agent.setEnabled', { id: 'stage-intake', on: false }]);
  });
});

describe('findTools (plan 9 P9-2.12)', () => {
  it('invokes the tools.find read and returns its tools, the ten best by default', async () => {
    m.invoke.mockResolvedValueOnce({ ok: true, output: { tools: [{ action: 'evidence.request' }] }, key: null, action: 'tools.find' });
    const tools = await findTools('request missing evidence');
    expect(last()).toEqual(['tools.find', { query: 'request missing evidence', limit: 10 }]);
    expect(tools).toEqual([{ action: 'evidence.request' }]);
  });

  it('returns nothing for a blank query without calling the server, and for a refusal', async () => {
    m.invoke.mockClear();
    expect(await findTools('  ')).toEqual([]);
    expect(m.invoke).not.toHaveBeenCalled();
    m.invoke.mockResolvedValueOnce({ ok: false, code: 'out_of_scope', message: 'no' });
    expect(await findTools('case')).toEqual([]);
  });
});
