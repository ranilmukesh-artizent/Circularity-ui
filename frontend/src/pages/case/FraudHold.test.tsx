// @vitest-environment jsdom
// P9-2.24 (X-15): the fraud hold banner is one component, shown on the Overview and on every stage page of a held case.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ approve: true }));
vi.mock('../../api/session', () => ({ can: () => m.approve, canPage: () => true }));
vi.mock('../../api/actions', () => ({ invoke: vi.fn() }));

import type { CaseRec } from '../../api/case';
import { fraudLine, type FraudRecord } from '../../api/fraud';
import { FraudHold } from './FraudHold';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { m.approve = true; host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));

const fraud: FraudRecord = {
  status: 'held', score: 0.8, threshold: 0.6, rule_version: 'v1', held_at: '2026-11-25T10:00:00+00:00', by: 'stage-intake',
  signals: [{ id: 'F-BL', fired: true, value: true, source: 'Blacklist register', at: '2026-11-20T10:00:00+00:00' }],
  review: { narrative: 'The serial is on a blacklist.', concerns: [{ text: 'Blacklisted.', sources: ['F-BL'] }], raise_hold: false },
}; // prettier-ignore
const held = (f: Partial<FraudRecord> | null) => ({ id: 'RT-1', ...(f ? { fraud: { ...fraud, ...f } } : {}) }) as unknown as CaseRec;

describe('P9-2.24 FraudHold banner (X-15)', () => {
  it('shows the score line, the signals and the release controls of a held case', () => {
    act(() => root.render(<FraudHold c={held({})} />));
    const banner = host.querySelector('[data-testid="fraud-hold"]');
    expect(banner?.textContent).toContain(fraudLine(fraud));
    expect(banner?.textContent).toContain('F-BL · Blacklist register');
    expect(host.querySelector('[data-testid="fraud-review"]')?.textContent).toContain('The serial is on a blacklist.');
    expect(host.querySelector('#fraud-reason')).not.toBeNull();
    expect([...host.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Release', 'Reject']);
  });

  it('leaves the decision to an approver: others read it only', () => {
    m.approve = false;
    act(() => root.render(<FraudHold c={held({})} />));
    expect(host.querySelector('#fraud-reason')).toBeNull();
    expect(host.textContent).toContain('An Approver releases the hold or rejects the return.');
  });

  it('draws nothing for a case that was never held or is released', () => {
    act(() => root.render(<FraudHold c={held(null)} />));
    expect(host.innerHTML).toBe('');
    act(() => root.render(<FraudHold c={held({ status: 'released' })} />));
    expect(host.innerHTML).toBe('');
  });
});
