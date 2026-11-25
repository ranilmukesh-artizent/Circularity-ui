import { describe, expect, it } from 'vitest';
import type { QueuePlan } from '../../api/case';
import { planLines } from './queuePlan';

const holder: QueuePlan = { holds: 'LS-201', contested: ['LS-201'], lost: [], kinds: { 'LS-201': 'lease renewal' } };
const loser: QueuePlan = {
  holds: null, contested: ['LS-201'], lost: [{ order: 'LS-201', to: 'RT-1002', gain: 340 }], kinds: { 'LS-201': 'lease renewal' },
};

describe('P9-1.4 planLines (TF-08)', () => {
  it('says which order the return holds', () => {
    expect(planLines(holder)).toEqual(['Holds lease renewal LS-201.']);
  });

  it('says which return gets an order this return lost, and what it gains from it', () => {
    expect(planLines(loser)).toEqual(['Lease renewal LS-201 goes to RT-1002: it gains $340 more from it.']);
  });

  it('writes nothing for a case outside the queue plan or one that holds and loses nothing', () => {
    expect(planLines(null)).toEqual([]);
    expect(planLines({ holds: null, contested: [], lost: [], kinds: {} })).toEqual([]);
  });
});
