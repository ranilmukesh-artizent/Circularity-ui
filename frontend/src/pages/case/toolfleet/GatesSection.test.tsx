// @vitest-environment jsdom
// Plan 9, P9-3.6 (TF-02): the gates of a tool fleet case, a failed GR-07 with the term it is blocked on.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { GateView } from '../../../api/toolFleet';
import { GatesSection, gateLine } from './GatesSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const gate = (over: Partial<GateView>): GateView => ({
  id: 'G-CON-2', name: 'Contract right', passed: true, reason: 'Active contract line FL-30117-03', guardrail: 'GR-07', owner: 'Fleet desk',
  kind: 'block', stage: 'match', stageLabel: 'Match and verify', hold: true, locked: true, ...over,
});
const FAILED = gate({ passed: false, reason: 'Theft recovered: claim CLM-7781 is open' });

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = (gates: GateView[]) => {
  act(() => root.render(<GatesSection gates={gates} />));
  return host;
};

describe('gate line', () => {
  it('says passed, or the term the gate is blocked on', () => {
    expect(gateLine(gate({}))).toBe('GR-07 Contract right: passed');
    expect(gateLine(FAILED)).toBe('GR-07 Contract right: Theft recovered: claim CLM-7781 is open');
    expect(gateLine(gate({ guardrail: null, passed: false, reason: 'Data-wipe certificate missing' }))).toBe(
      'Contract right: Data-wipe certificate missing',
    );
  });
});

describe('GatesSection', () => {
  it('renders a failed GR-07 with its reason and a Blocked chip', () => {
    const h = render([FAILED]);
    expect(h.querySelector('[data-testid="tf-gate-G-CON-2"]')?.textContent).toContain('Theft recovered: claim CLM-7781 is open');
    expect(h.querySelector('.chip')?.textContent).toBe('Blocked');
    expect(h.querySelector('.chip.bad')).not.toBeNull();
  });
  it('renders a passed gate with a Passed chip', () => {
    const h = render([gate({})]);
    expect(h.textContent).toContain('GR-07 Contract right: passed');
    expect(h.querySelector('.chip.ok')?.textContent).toBe('Passed');
  });
  it('renders nothing for a case no gate applies to', () => {
    expect(render([]).innerHTML).toBe('');
  });
});

// Plan 9, P9-3.8 (TF-05): GR-13, the telematics freshness line; a stale tool needs a person for re-issue and pool.
const tel = (over: Partial<GateView>): GateView =>
  gate({ id: 'G-TOOL-TEL', name: 'Telematics under 7 days old', guardrail: 'GR-13', owner: 'Engineer', kind: 'require_approval', stage: 'condition', hold: false, ...over });

describe('telematics gate (GR-13)', () => {
  it('says how old the telematics are when fresh', () => {
    const h = render([tel({ reason: 'Telematics 3 days old', age_days: 3, max_age_days: 7 })]);
    expect(h.querySelector('[data-testid="tf-gate-G-TOOL-TEL"]')?.textContent).toContain('Telematics 3 days old');
    expect(h.querySelector('.chip.ok')?.textContent).toBe('Passed');
  });
  it('says when it was last seen and that re-issue and pool need a person when stale', () => {
    const g = tel({ passed: false, reason: 'Telematics last seen 8 days ago', age_days: 8, max_age_days: 7 });
    expect(gateLine(g)).toBe('Telematics last seen 8 days ago: re-issue and pool need a person');
    const h = render([g]);
    expect(h.querySelector('[data-testid="tf-gate-G-TOOL-TEL"]')?.textContent).toContain('re-issue and pool need a person');
    expect(h.querySelector('.chip.bad')?.textContent).toBe('Needs a person');
  });
});
