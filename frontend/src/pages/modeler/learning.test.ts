import { describe, expect, it } from 'vitest';
import type { RuleSuggestion } from '../../api/modeler';
import { shareLine } from './learning';

const sug = { dim: 'cls', value: 'motor', path: 'resale', overrides: 3, decisions: 4, share: 0.75 } as RuleSuggestion;

describe('the Modeler rule suggestions (audit U8)', () => {
  it('says how many decisions were overridden to the suggested path', () => {
    expect(shareLine(sug, (k) => (k === 'resale' ? 'Whole-asset resale' : k))).toBe('3 of 4 motor decisions overridden to Whole-asset resale (75%)');
  });
});
