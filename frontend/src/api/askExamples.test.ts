import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ perms: new Set<string>() }));
const INTENTS = [
  { id: 'briefing', area: 'briefing', title: 'Brief me' },
  { id: 'case.risk', area: 'case', title: 'Risks before approving' },
  { id: 'case.submit', area: 'case', title: 'Submit for review' },
  { id: 'case.approve', area: 'case', title: 'Approve' },
  { id: 'gate.waive', area: 'case', title: 'Waive a gate' },
  { id: 'workflow.fix', area: 'integration', title: 'Fix workflow errors' },
];
vi.mock('./client', () => ({ cached: vi.fn(), http: vi.fn(), invalidate: vi.fn(), peek: vi.fn(), session: () => ({}), withQuery: (p: string) => p, ref: (k: string) => (k === 'AF_INTENTS' ? INTENTS : {}) }));
vi.mock('./session', () => ({ can: (p: string) => m.perms.has(p), canPage: () => true, currentAccount: () => ({ role: 'Planner' }) }));

import { askExamples } from './home';

beforeEach(() => m.perms.clear());

describe('askExamples (UI QA B item 11)', () => {
  it('offers a planner only questions and prepare-for-review examples, never Approve or Waive', () => {
    m.perms.add('submit');
    const l = askExamples();
    expect(l).toContain('Brief me');
    expect(l).toContain('Risks before approving');
    expect(l).toContain('Prepare this case for review');
    expect(l).not.toContain('Approve');
    expect(l.join('|')).not.toMatch(/Waive|Fix workflow/);
    expect(l).not.toContain('Prepare the decision packet for my approval'); // no approve right
  });

  it('shows the approval packet to an approver, phrased as a preparation, and still no waiver', () => {
    m.perms.add('approve.decisions');
    const l = askExamples();
    expect(l).toContain('Prepare the decision packet for my approval');
    expect(l).not.toContain('Approve');
    expect(l).not.toContain('Waive a gate');
  });

  it('shows workflow examples to a role that manages workflows', () => {
    m.perms.add('manageWorkflows');
    expect(askExamples()).toContain('Fix workflow errors');
  });
});
