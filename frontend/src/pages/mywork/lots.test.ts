import { describe, expect, it } from 'vitest';
import type { LotView } from '../../api/device';
import { canApprove, droppedLine, lotLine, waitLine } from './lots';

const lot: LotView = {
  id: 'L-1', lot_ref: 'LOT-W-0001', org_unit_id: 'Customer A', model: 'Galaxy S23', grade: 'C', units: 100, status: 'proposed',
  bids_received: 6, best_bid: { bid_id: 'BID-0002', buyer_code: 'B02', amount: 324, fees: 8, logistics: 6, net: 310 },
  dropped: [{ bid_id: 'BID-0005', buyer_code: 'B05', reason: 'Buyer B05 is not an approved wholesale buyer' }],
  value_usd: 31000, created_by: 'planner-a', proposed_by: 'planner-a', approved_by: null, reason: null,
  waits_for: { role: 'Approver', owner: 'Commercial manager', reason: 'A $31,000 lot is over the $25,000 limit' },
};

describe('P9-6.11 lotLine (DV-07)', () => {
  it('says the model, grade, units, best approved bid a unit and the value', () => {
    expect(lotLine(lot)).toBe('Galaxy S23 · grade C · 100 units · best approved bid $310 a unit · $31,000');
  });
  it('says so when no approved bid has come in', () => {
    expect(lotLine({ ...lot, best_bid: null, value_usd: null })).toBe('Galaxy S23 · grade C · 100 units · no approved bid yet');
  });
  it('keeps cents on a bid that has them', () => {
    expect(lotLine({ ...lot, best_bid: { ...lot.best_bid!, net: 309.5 }, value_usd: 30950 })).toContain('$309.50 a unit · $30,950');
  });
});

describe('P9-6.11 reasons shown beside a lot', () => {
  it('names a dropped bid with its reason', () => {
    expect(droppedLine(lot.dropped[0])).toBe('B05: Buyer B05 is not an approved wholesale buyer');
  });
  it('names who a lot waits for', () => {
    expect(waitLine(lot)).toBe('Waits for the Approver role (Commercial manager): A $31,000 lot is over the $25,000 limit');
    expect(waitLine({ ...lot, waits_for: null })).toBe('');
  });
  it('maker-checker: the person who built or proposed a lot cannot approve it', () => {
    expect(canApprove(lot, 'planner-a')).toBe('You built or proposed this lot, so you cannot approve it.');
    expect(canApprove(lot, 'approver')).toBeNull();
    expect(canApprove({ ...lot, status: 'bidding' }, 'approver')).toBe('Only a proposed lot is approved.');
  });
});
