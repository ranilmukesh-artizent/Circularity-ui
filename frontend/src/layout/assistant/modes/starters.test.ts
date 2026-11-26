import { describe, expect, it } from 'vitest';
import { argsText, selectStarters, startersQuery, usedLine } from './starters';
import type { AssistantContext } from '../types';

const home: AssistantContext = { page: 'home', role: 'Admin' };
const demo = ['Who can approve above $5,000?', 'What did agents do today?', 'What needs me today?'];

describe('selectStarters', () => {
  it('leads with the demo starters on Home and for the industrial pack', () => {
    const r = selectStarters(demo, { pack: null, starters: [{ text: 'What needs me today?' }, { text: 'Other' }] }, home);
    expect(r).toEqual([...demo, 'Other']);
  });
  it('leads with the pack questions on a case of another pack, then one demo starter', () => {
    const ctx: AssistantContext = { page: 'product', caseId: 'RT-2001', role: 'Planner' };
    const r = selectStarters(demo, { pack: 'device', starters: [{ text: 'Is the data-wipe certificate on file?' }] }, ctx);
    expect(r).toEqual(['Is the data-wipe certificate on file?', 'Why this route for RT-2001?', demo[0]]);
  });
  it('is the demo starters alone when the server has nothing', () => {
    expect(selectStarters(demo, { pack: null, starters: [] }, home)).toEqual(demo);
  });
  it('shows at most six, each once', () => {
    const many = Array.from({ length: 9 }, (_, i) => ({ text: 'Q' + i }));
    expect(selectStarters([], { pack: 'itad', starters: [...many, ...many] }, home)).toHaveLength(6);
  });
});

describe('pages the demo does not have', () => {
  it('shows no demo starter on the Modeler, only the server questions', () => {
    const r = selectStarters(demo, { pack: null, starters: [{ text: 'Which guardrails does this flow keep?' }] }, { page: 'modeler', role: 'Admin' });
    expect(r).toEqual(['Which guardrails does this flow keep?']);
  });
});

describe('startersQuery', () => {
  it('sends the flow template as the section on the Modeler', () => {
    const ctx: AssistantContext = { page: 'modeler', role: 'Admin', flow: { id: 1, name: 'F', template: 'used_cars', org: 'workspace', canEdit: true, draftVer: null } };
    expect(startersQuery(ctx)).toEqual({ page: 'modeler', section: 'used_cars', case_id: undefined });
  });
});

describe('the Used line', () => {
  it('names each tool once in plain words', () => {
    expect(usedLine([{ name: 'get_case' }, { name: 'get_case' }, { name: 'device_question' }])).toBe('Used: the case record, the device records');
    expect(usedLine([])).toBe('');
  });
  it('lists the inputs of a call', () => {
    expect(argsText({ case_id: 'RT-1048', org_unit_id: '', n: 3 })).toBe('case id RT-1048, n 3');
  });
});
