import { describe, expect, it } from 'vitest';
import type { NewAgent } from '../../api/agents';
import { idFromName, problem, toolOptions } from './register';

const tool = (action: string, agent_allowed: boolean, agent_mode: 'yes' | 'held' | 'no' = agent_allowed ? 'yes' : 'no', implemented = true) => ({
  name: action.replace('.', '_'), action, title: action, description: '', risk: 'read', input_schema: {}, agent_allowed, agent_mode, implemented,
}); // prettier-ignore

describe('the Register agent dialog (plan 8 UI gaps)', () => {
  it('makes an id from the name', () => {
    expect(idFromName('Claims Helper 2')).toBe('claims-helper-2');
    expect(idFromName('  --Ünïcode bot!! ')).toBe('n-code-bot');
    expect(idFromName('x'.repeat(80))).toHaveLength(64);
  });

  it('never offers an action no agent may run', () => {
    const opts = toolOptions({
      mcp_tools: ['get_case_evidence'],
      tools: [tool('cases.list', true), tool('decision.approve', false), tool('model.promote', false), tool('agent.register', false)],
    });
    expect(opts.map((o) => [o.id, o.kind])).toEqual([
      ['get_case_evidence', 'mcp'],
      ['cases.list', 'action'],
    ]);
  });

  it('offers held actions and hides actions that are not built', () => {
    const opts = toolOptions({
      mcp_tools: [],
      tools: [tool('cases.list', true), tool('mapping.revert', true, 'held'), tool('analytics.query', false, 'no', false), tool('credentials.rotate', false)],
    });
    expect(opts.map((o) => o.id)).toEqual(['cases.list', 'mapping.revert']);
  });

  it('checks the form before it is sent', () => {
    const a: NewAgent = { id: 'ext-b', name: 'B', kind: 'external', tools: [], org_scope: [], autonomy: 'propose' };
    expect(problem(a, [])).toBe('');
    expect(problem({ ...a, name: ' ' }, [])).toBe('Give the agent a name.');
    expect(problem({ ...a, id: 'B!' }, [])).toMatch(/^The id is 2 to 64/);
    expect(problem(a, ['ext-b'])).toBe('An agent with the id ext-b is already registered.');
  });
});
