import { describe, expect, it } from 'vitest';
import { statusLine, statusText } from './status';

describe('statusLine (plan 10, 2.4)', () => {
  it('get_case: reading while running, read when done, numbers only from the result', () => {
    const run = statusLine({ name: 'get_case', phase: 'running', args: { case_id: 'RT-1048' } });
    expect(statusText(run)).toBe('Reading RT-1048 and its evidence · read-only…');
    expect(run.state).toBe('working');
    const done = statusLine({ name: 'get_case', phase: 'done', args: { case_id: 'RT-1048' }, result: { evidence: 6 } });
    expect(statusText(done)).toBe('Read RT-1048 and 6 evidence records');
    expect(done.state).toBe('done');
    expect(statusText(statusLine({ name: 'get_case', phase: 'done', args: { case_id: 'RT-1048' } }))).toBe('Read RT-1048');
  });
  it('list_cases', () => {
    expect(statusText(statusLine({ name: 'list_cases', phase: 'running' }))).toBe('Searching open cases you may see · read-only…');
    expect(statusText(statusLine({ name: 'list_cases', phase: 'done', result: { count: 41 } }))).toBe('Searched 41 open cases');
  });
  it('device_question', () => {
    const args = { question: 'Which grades sell fastest?' };
    expect(statusText(statusLine({ name: 'device_question', phase: 'running', args }))).toBe(
      'Answering "Which grades sell fastest?" from device records · read-only…',
    );
    expect(statusText(statusLine({ name: 'device_question', phase: 'done', args, result: { count: 312 } }))).toBe('Answered from 312 device records');
  });
  it('a refused tool is blocked and says why', () => {
    const s = statusLine({ name: 'get_case', phase: 'refused', args: { case_id: 'RT-2001' }, message: 'outside your tenants' });
    expect(s.state).toBe('blocked');
    expect(statusText(s)).toBe('Could not read RT-2001: outside your tenants');
  });
  it('the rules answered, with the reason', () => {
    const s = statusLine({ name: 'ask.fallback', phase: 'done', result: { reason: 'the model was unavailable' } });
    expect(statusText(s)).toBe('Answered by the rules, because the model was unavailable');
  });
  it('flow.propose', () => {
    const ctx = { flowName: 'draft v2', guardrails: 5 };
    expect(statusText(statusLine({ name: 'flow.propose', phase: 'running' }, ctx))).toBe('Checking the sentence against 5 guardrails · nothing saved…');
    expect(statusText(statusLine({ name: 'flow.propose', phase: 'done', result: { rules: 1 } }, ctx))).toBe('Checked against 5 guardrails · 1 rule proposed');
  });
  it('flow.simulate', () => {
    const ctx = { flowName: 'draft v2' };
    expect(statusText(statusLine({ name: 'flow.simulate', phase: 'running', result: { cases: 41 } }, ctx))).toBe('Simulating draft v2 on 41 open cases · nothing saved…');
    expect(statusText(statusLine({ name: 'flow.simulate', phase: 'done', result: { cases: 41 } }, ctx))).toBe('Simulated on 41 open cases');
  });
  it('flow.saveDraft', () => {
    const ctx = { flowName: 'draft v2' };
    expect(statusText(statusLine({ name: 'flow.saveDraft', phase: 'running', args: { rule: 'IR-02' } }, ctx))).toBe('Saving IR-02 to draft v2 · not published…');
    expect(statusText(statusLine({ name: 'flow.saveDraft', phase: 'done', args: { rule: 'IR-02' } }, ctx))).toBe('Saved to draft v2');
  });
  it('compose.start and compose.answer', () => {
    expect(statusText(statusLine({ name: 'compose.start', phase: 'running', args: { words: 62 } }, { org: 'workspace' }))).toBe('Reading 62 words for workspace · drafts only…');
    expect(statusText(statusLine({ name: 'compose.start', phase: 'done', args: { words: 62 }, result: { pack: 'Industrial returns' } }))).toBe('Read 62 words · matched Industrial returns');
    expect(statusText(statusLine({ name: 'compose.answer', phase: 'running' }))).toBe('Drafting changes from your answer · drafts only…');
    expect(statusText(statusLine({ name: 'compose.answer', phase: 'done', result: { changes: 4, assumed: 1 } }))).toBe('Drafted 4 changes, 1 assumed');
  });
  it('proposal.accept runs as you', () => {
    const a = { title: 'Approve route', case_id: 'RT-1048' };
    expect(statusText(statusLine({ name: 'proposal.accept', phase: 'running', args: a }))).toBe('Running "Approve route" for RT-1048 as you…');
    expect(statusText(statusLine({ name: 'proposal.accept', phase: 'done', args: a }))).toBe('Ran as you · see History');
  });
  it('an unknown tool falls back to a generic line', () => {
    expect(statusText(statusLine({ name: 'get_inbox', phase: 'running' }))).toBe('Reading get_inbox · read-only…');
    expect(statusText(statusLine({ name: 'get_inbox', phase: 'done' }))).toBe('Read get_inbox');
    expect(statusLine({ name: 'get_inbox', phase: 'failed', message: 'boom' }).state).toBe('failed');
  });
});
