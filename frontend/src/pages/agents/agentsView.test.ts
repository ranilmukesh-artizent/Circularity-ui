import { describe, expect, it } from 'vitest';
import type { AgentRow, AgentRun, AgentsScreen } from '../../api/agents';
import { NEVER_ALONE, STAGE_AUTONOMY, agentGroups, agentSummary, lastRunOf, plainTool } from './agentsView';

const row = (id: string, name: string, over: Partial<AgentRow> = {}): AgentRow => ({
  id, name, kind: 'internal', autonomy: 'act', enabled: true, org_scope: [], tools: [], created_by: null, ...over,
}); // prettier-ignore
const run = (id: string, agent: string, at: string, journey: { agent: string; status: string }[] = []): AgentRun =>
  ({ id, agent, agentName: agent, playbook: 'stage_chain', case_id: 'RT-1', status: 'done', step: 1, stage: null, reason: null, waiting: null,
    created_at: at, updated_at: at, steps: [], journey } as unknown as AgentRun); // prettier-ignore

const screen: Pick<AgentsScreen, 'agents' | 'packs' | 'runs'> = {
  agents: [row('stage-lease', 'Lease agent'), row('stage-intake', 'Intake agent', { enabled: false }), row('assembler', 'Evidence Assembler'), row('ext-x', 'Copilot', { kind: 'external' })],
  packs: [{
    key: 'industrial', name: 'Industrial returns',
    stages: [
      { stage: 'lease_end', agent: 'stage-lease', autonomy: 'alone', threshold: 0.75 },
      { stage: 'intake', agent: 'stage-intake', autonomy: 'limits', threshold: 0.75 },
    ],
  }],
  runs: [run('r1', 'recover-chain', '2026-11-01T10:00:00', [{ agent: 'stage-lease, stage-intake', status: 'Completed' }]), run('r2', 'assembler', '2026-11-02T10:00:00')],
};

describe('Agents page: the business view (UI audit gaps 14 and 21)', () => {
  it('groups the stage agents under their pack, the rest under platform and outside agents', () => {
    const g = agentGroups(screen);
    expect(g.map((x) => x.title)).toEqual(['Industrial returns', 'Platform agents', 'Outside agents']);
    expect(g[0].rows.map((r) => [r.stageLabel, r.autonomy, r.agent.id])).toEqual([
      ['Lease end', 'alone', 'stage-lease'],
      ['Intake', 'limits', 'stage-intake'],
    ]);
    expect(g[1].rows.map((r) => r.agent.id)).toEqual(['assembler']);
    expect(g[2].rows.map((r) => r.agent.id)).toEqual(['ext-x']);
  });

  it('keeps a pack with no stage agent, marked not set up', () => {
    const g = agentGroups({ ...screen, packs: [...screen.packs, { key: 'used_cars', name: 'Used vehicles', stages: [{ stage: 'lease_end', agent: 'stage-missing', autonomy: 'alone', threshold: 0.75 }] }] });
    expect(g.map((x) => [x.title, x.notSetUp ?? false])).toEqual([['Industrial returns', false], ['Used vehicles', true], ['Platform agents', false], ['Outside agents', false]]);
  });

  it('names the three levels in business words and says what act alone never covers', () => {
    expect(STAGE_AUTONOMY).toEqual({ recommend: 'Recommend only', limits: 'Act within limits', alone: 'Act alone' });
    expect(NEVER_ALONE).toMatch(/approving, overriding, declining or changing access/);
  });

  it('finds the last run of an agent, also from the stages of a chain run', () => {
    expect(lastRunOf('assembler', screen.runs)?.id).toBe('r2');
    expect(lastRunOf('stage-intake', screen.runs)?.id).toBe('r1');
    expect(lastRunOf('ext-x', screen.runs)).toBeNull();
  });

  it('says what an agent does without a model id', () => {
    expect(agentSummary(row('stage-intake', 'Intake agent'))).toMatch(/what arrived/);
    expect(agentSummary(row('ext-x', 'Copilot', { kind: 'external', tools: ['a', 'b'] }))).toBe('An outside agent with 2 tools.');
    expect(plainTool('get_case_evidence')).toBe('get case evidence');
  });
});
