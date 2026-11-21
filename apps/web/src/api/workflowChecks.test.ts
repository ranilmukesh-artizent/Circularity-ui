// Workflow Studio usability (plan 6 follow-up, G2): the canvas' checks merged with the server's for the draft, and the
// saved version a published workflow can publish.
import { describe, expect, it } from 'vitest';
import type { Check, WfGraph } from './workflows';
import { mergeChecks, republishVer } from './workflowGraph';

const g: WfGraph = {
  nodes: [
    { id: 'r', k: 'conn', ref: 'crm', x: 0, y: 0 },
    { id: 'late', k: 'xf', ref: 'x_late', x: 200, y: 0, cfg: { keys: ['opportunity_id'] } },
  ],
  edges: [{ id: 'e1', a: 'r', b: 'late', locked: false }],
};
const BAD = 'Order late events: Key fields opportunity_id is not a field the records carry.';

describe('mergeChecks', () => {
  it('adds the server-only field error to the browser checks, errors first', () => {
    const browser: Check[] = [{ sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' }];
    const server: Check[] = [{ sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' }, { sev: 'error', id: 'late', msg: BAD }];
    expect(mergeChecks(browser, server, g)).toEqual([
      { sev: 'error', id: 'late', msg: BAD },
      { sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' },
    ]);
  });
  it('keeps one check per step and text, and the server wins on a duplicate', () => {
    const browser: Check[] = [{ sev: 'warn', id: 'r', msg: 'Same text.' }];
    const server: Check[] = [{ sev: 'error', id: 'r', msg: 'Same text.' }];
    expect(mergeChecks(browser, server, g)).toEqual([{ sev: 'error', id: 'r', msg: 'Same text.' }]);
  });
  it('drops a server check for a step no longer in the graph (an answer for an earlier edit)', () => {
    const server: Check[] = [{ sev: 'error', id: 'gone', msg: 'Old step.' }, { sev: 'error', id: 'e1', msg: 'A link check.' }];
    expect(mergeChecks([], server, g)).toEqual([{ sev: 'error', id: 'e1', msg: 'A link check.' }]);
  });
  it('is the browser checks alone without a server answer', () => {
    const browser: Check[] = [{ sev: 'info', id: 'r', msg: 'A note.' }];
    expect(mergeChecks(browser, null, g)).toBe(browser);
    expect(mergeChecks(browser, [], g)).toBe(browser);
  });
});

describe('republishVer', () => {
  it('offers the saved version when it is newer than the published one', () => {
    expect(republishVer({ status: 'published', ver: '0.3' }, '0.2')).toBe('0.3');
  });
  it('offers nothing when the published version is the saved one, or the workflow is not published', () => {
    expect(republishVer({ status: 'published', ver: '0.3' }, '0.3')).toBeNull();
    expect(republishVer({ status: 'paused', ver: '0.3' }, '0.2')).toBeNull();
    expect(republishVer({ status: 'draft', ver: '0.3' }, null)).toBeNull();
  });
});
