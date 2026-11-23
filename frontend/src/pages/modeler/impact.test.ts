import { describe, expect, it } from 'vitest';
import type { SimResult } from '../../api/types';
import { formatImpact, poMoney, tradeOff } from './impact';

const flip = { case_id: 'A', from: 'resell', to: 'refurb', dv: -20 };
const equip = (dv: number): SimResult => ({ kind: 'equip', n: 26, flips: [flip, flip, flip], dv, extra: {} });

describe('impact wording (the prototype propHtml)', () => {
  it('money as the prototype prints it', () => {
    expect([poMoney(950.4), poMoney(12345), poMoney(-2_500_000)]).toEqual(['$950', '$12.3k', '−$2.50M']);
  });

  it('dv >= 0: a plus sign and no trade-off', () => {
    expect(formatImpact(equip(18400))).toBe('3 of 26 open decisions change · +$18.4k queue net');
    expect(tradeOff(equip(0))).toBeNull();
  });

  it('dv < 0: a minus sign and the trade-off note', () => {
    expect(formatImpact(equip(-4200))).toBe('3 of 26 open decisions change · −$4,200 queue net');
    expect(tradeOff(equip(-4200))).toBe(
      'Trade-off: the models already pick the highest-value path, so this rule gives up $4,200. Approve it for a business reason such as a customer commitment, risk or capacity.',
    );
  });

  it('device: lots, expected cash and days', () => {
    const s: SimResult = { kind: 'device', n: 40, flips: [flip], dv: -1500, extra: { dd: -3.25, u: 900 } };
    expect(formatImpact(s)).toBe('1 of 40 lots change channel · −$1,500 expected cash · -3.3 days');
    expect(tradeOff(s)).toContain('gives up $1,500 to dispose 3.3 days faster.');
  });
});
