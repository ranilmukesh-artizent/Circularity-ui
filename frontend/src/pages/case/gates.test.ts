import { describe, expect, it } from 'vitest';
import type { GateRow } from '../../api/case';
import { clauseLine, gateLine, gateTime, holdLine } from './gates';

const wipe: GateRow = {
  id: 'G-DEV-WIPE', name: 'Data-wipe certificate', type: 'Compliance', stage: 'condition', stageLabel: 'Condition', passed: false,
  kind: 'block', routes: ['buynow', 'offers'], routeNames: ['Buy Now', 'Offers'], hold: true, step: null, owner: 'Compliance',
  evidence: [], missing: ['Data-wipe certificate'], reason: 'Data-wipe certificate missing', locked: true,
};

describe('P9-1.2 gateLine (X-03)', () => {
  it('names the routes a failed gate blocks, and why', () => {
    expect(gateLine(wipe)).toBe('Blocks Buy Now, Offers: Data-wipe certificate missing');
  });

  it('names the evidence, its source and time when the gate passed', () => {
    const g: GateRow = {
      ...wipe, passed: true, missing: [], reason: 'Data-wipe certificate on file',
      evidence: [{ type: 'data_wipe', label: 'Data-wipe certificate', source: 'bench-wipe', at: '2026-10-01T08:00:00+00:00' }],
    };
    expect(gateLine(g)).toBe('Passed: Data-wipe certificate from bench-wipe, 2026-10-01 08:00 UTC');
  });

  it('says what a failed gate that blocks no route does instead', () => {
    expect(gateLine({ ...wipe, kind: 'require_step', step: 'Destroy the media', reason: 'Destruction record missing' })).toBe(
      'Requires a step (Destroy the media): Destruction record missing');
    expect(gateLine({ ...wipe, kind: 'require_approval', step: null, reason: 'Telematics reading missing' })).toBe(
      'Needs approval: Telematics reading missing');
    expect(gateLine({ ...wipe, kind: 'close_block', reason: 'Carbon factor provenance missing' })).toBe(
      'Blocks closing: Carbon factor provenance missing');
  });

  it('formats the time as the server wrote it', () => {
    expect(gateTime('2026-10-01T08:00:00Z')).toBe('2026-10-01 08:00 UTC');
    expect(gateTime('soon')).toBe('soon');
  });
});

describe('P9-1.2 holdLine (X-07)', () => {
  const hold = { gates: ['G-DEV-WIPE'], since: '2026-10-07T09:00:00+00:00', batch: 'B-7' };

  it('shows how many lots of the batch are released', () => {
    expect(holdLine(hold, { ref: 'B-7', total: 3, held: 2, released: 1 })).toBe('Held until evidence arrives (batch B-7: 1 of 3 released)');
  });

  it('falls back to the batch name, or to no batch at all', () => {
    expect(holdLine(hold)).toBe('Held until evidence arrives (batch B-7)');
    expect(holdLine({ ...hold, batch: null })).toBe('Held until evidence arrives');
  });
});

describe('P9-1.11 contract result (X-11)', () => {
  const clause = {
    type: 'contract_clause', label: 'Contract clause', source: 'lease-system', at: '2026-10-01T08:00:00+00:00',
    value: { contract_id: 'LS-5412', clause: '7.2', text: 'No resale without consent', restricts: ['sale'] },
  };
  const line = "Contract LS-5412 · clause 7.2 · 'No resale without consent' · from lease-system, 2026-10-01 08:00 UTC";
  const blocked: GateRow = {
    ...wipe, id: 'G-CON-1', name: 'Contract entitlement', hold: false, routes: ['resell'], routeNames: ['Pre-owned sale'],
    owner: 'Customer operations', evidence: [clause], missing: ['Customer consent'],
    reason: 'Contract LS-5412 clause 7.2: No resale without consent. Customer consent not on file.',
  };

  it('shows the contract, clause, text, source and date, then what it blocks', () => {
    expect(clauseLine(blocked)).toBe(line);
    expect(gateLine(blocked)).toBe(
      `${line}. Blocks Pre-owned sale: Contract LS-5412 clause 7.2: No resale without consent. Customer consent not on file.`);
  });

  it('shows the consent reference when the gate passes', () => {
    const g: GateRow = {
      ...blocked, passed: true, missing: [], reason: 'Consent on file: CONS-88.',
      evidence: [clause, { type: 'customer_consent', label: 'Customer consent', source: 'crm', at: clause.at, value: { ref: 'CONS-88' } }],
    };
    expect(gateLine(g)).toBe(`${line}. Consent on file: CONS-88.`);
  });

  it('has no clause line for another gate', () => {
    expect(clauseLine(wipe)).toBeNull();
  });
});
