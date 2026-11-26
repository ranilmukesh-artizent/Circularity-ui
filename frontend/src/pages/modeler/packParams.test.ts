import { describe, expect, it } from 'vitest';
import type { OverlayOp, OverlayParam } from '../../api/types';
import { changeable, directionText, paramLine, paramRefusal, proposedValue, withParam } from './packParams';

const rul: OverlayParam = { path: 'valuer.rulMin', value: 50, min: 30, max: 90, direction: 'raise_only', guardrail: 'GR-03', owner: 'Quality' };
const free: OverlayParam = { path: 'fraud.threshold', value: 0.7, min: 0.5, max: 0.95, direction: null, guardrail: null, owner: null };

describe('pack parameters a customer may change (P9-3.20)', () => {
  it('lists the parameters the pack publishes', () => {
    expect(changeable([rul, free]).map((p) => p.path)).toEqual(['valuer.rulMin', 'fraud.threshold']);
    expect(changeable([])).toEqual([]);
  });

  it('shows the threshold with its owner and which way it may move', () => {
    expect(paramLine(rul)).toBe('Fit-for-use threshold 50% · owner Quality');
    expect(paramLine(rul, 60)).toBe('Fit-for-use threshold 60% · owner Quality');
    expect(directionText(rul)).toBe("Raise only: 30–90, never below the pack's 50% (GR-03).");
    expect(directionText(free)).toBe('Between 0.5 and 0.95.');
  });

  it('refuses a value below the pack, naming GR-03, with the server text', () => {
    expect(paramRefusal(rul, 40)).toBe('GR-03 can only be raised: valuer.rulMin 50 → 40 weakens it.');
    expect(paramRefusal(rul, 95)).toBe('valuer.rulMin must be between 30 and 90.');
    expect(paramRefusal(rul, 60)).toBeNull();
    expect(paramRefusal(rul, 50)).toBeNull();
    expect(paramRefusal(free, 0.6)).toBeNull();
  });

  it('sets the parameter once, in place of an earlier change', () => {
    const tighten: OverlayOp = { id: 'op-1', by: '', note: '', op: 'tighten', target: 'GR-D2', field: 'floor', value: 0.6, seen: 0.55 };
    const one = withParam([tighten], rul, 60);
    expect(one).toHaveLength(2);
    expect(one[1]).toEqual({ id: 'op-2', by: '', note: '', op: 'set_param', path: 'valuer.rulMin', value: 60, seen: 50 });
    expect(proposedValue(one, 'valuer.rulMin')).toBe(60);
    const two = withParam(one, rul, 70);
    expect(two.filter((o) => o.op === 'set_param')).toHaveLength(1);
    expect(proposedValue(two, 'valuer.rulMin')).toBe(70);
    expect(proposedValue([tighten], 'valuer.rulMin')).toBeNull();
  });
});
