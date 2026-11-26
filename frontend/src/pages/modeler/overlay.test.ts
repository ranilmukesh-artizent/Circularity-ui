import { describe, expect, it } from 'vitest';
import type { OverlayGuardrail, OverlayOp } from '../../api/types';
import { guardrailControls, opLabel, weakens, withApprover } from './overlay';

const floor: OverlayGuardrail = { id: 'GR-D2', text: 'Recovery floor', field: 'floor', value: 0.55, stricter: 'higher', min: 0.3, max: 0.9, locked: false };
const cap: OverlayGuardrail = { id: 'GR-X', text: 'Cap', field: 'cap', value: 10, stricter: 'lower', min: 1, max: 20, locked: true };

describe('overlay refusal text, mirrored from the server (X-04)', () => {
  it('x-04: a weakening value shows the server text, a stricter one shows none', () => {
    expect(weakens(floor, 0.5)).toBe('GR-D2 can only be tightened: floor 0.55 → 0.5 weakens it.');
    expect(weakens(floor, 0.55)).toBe('GR-D2 can only be tightened: floor 0.55 → 0.55 weakens it.');
    expect(weakens(floor, 0.6)).toBeNull();
    expect(weakens(cap, 12)).toBe('GR-X can only be tightened: cap 10 → 12 weakens it.');
    expect(weakens(cap, 8)).toBeNull();
  });

  it('x-04: a value outside the range shows the range text', () => {
    expect(weakens(floor, 0.95)).toBe('GR-D2.floor must be between 0.3 and 0.9.');
    expect(weakens(cap, 0)).toBe('GR-X.cap must be between 1 and 20.');
  });
});

describe('overlay operation labels (X-04)', () => {
  const by = { id: 'op-1', by: 'planner-a', note: '' };
  it('x-04: one plain line per kind', () => {
    const ops: [OverlayOp, string][] = [
      [{ ...by, op: 'tighten', target: 'GR-D2', field: 'floor', value: 0.6, seen: 0.55 }, 'Tighten GR-D2: floor 0.55 → 0.6'],
      [{ ...by, op: 'add_approver', target: 'GR-01', role: 'Finance' }, 'Add approver Finance to GR-01'],
      [{ ...by, op: 'add_step', stage: 'condition', when: [], step: 'Second grading check', owner_role: 'Engineer' }, 'Add step "Second grading check" at Condition'],
      [{ ...by, op: 'shortcut', stage: 'value', when: [], to: 'decide' }, 'Skip from Value each route to Decide'],
      [{ ...by, op: 'set_param', path: 'GR-D2.rulMin', value: 80, seen: 70 }, 'Set GR-D2.rulMin: 70 → 80'],
    ];
    for (const [op, label] of ops) expect(opLabel(op)).toBe(label);
  });
});

describe('locked guardrails in the customer layer (UC-17)', () => {
  const recall = { id: 'G-VEH-RECALL', text: 'No retail with an open recall', locked: true, approvers: [] as string[] };

  it('uc-17: G-VEH-RECALL shows threshold, scope, exception and suspend-until disabled, and Add approver enabled', () => {
    const c = guardrailControls(recall);
    expect(c.fields.map((f) => f.label)).toEqual(['Threshold', 'Scope', 'Exception', 'Suspend until']);
    expect(c.fields.every((f) => f.disabled)).toBe(true);
    expect(c.addApprover).toBe(true);
  });

  it('uc-17: an unlocked guardrail has the four fields enabled', () => {
    expect(guardrailControls({ locked: false }).fields.every((f) => !f.disabled)).toBe(true);
  });

  it('uc-17: an extra approver is one add_approver op, never twice', () => {
    const ops = withApprover([], recall, 'used_car_manager');
    expect(ops).toEqual([{ id: 'op-1', by: '', note: '', op: 'add_approver', target: 'G-VEH-RECALL', role: 'used_car_manager' }]);
    expect(withApprover(ops, recall, 'used_car_manager')).toBe(ops);
    expect(withApprover(ops, { ...recall, approvers: ['qa'] }, 'qa')).toBe(ops);
    expect(opLabel(ops[0])).toBe('Add approver used_car_manager to G-VEH-RECALL');
  });
});
