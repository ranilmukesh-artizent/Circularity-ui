import type { GuardrailStage, OverlayCond, OverlayGuardrail, OverlayOp, OverlayScreen } from '../../api/types';

/** The stage labels (mirrors backend `services/modeler/stages.py`). */
export const STAGE_LABEL: Record<GuardrailStage, string> = {
  receive: 'Return and receive',
  match: 'Match and verify',
  condition: 'Condition',
  value: 'Value each route',
  decide: 'Decide',
  execute: 'Execute',
  close: 'Close and learn',
};

const OP_SYMBOL: Record<OverlayCond['op'], string> = { eq: '=', ne: '≠', in: 'in', gte: '≥', lte: '≤', exists: 'exists' };

/** The guardrail fields a customer may tighten: the guardrails of the pack that carry a parameter. */
export function tightenable(guardrails: OverlayScreen['guardrails']): OverlayGuardrail[] {
  return guardrails.flatMap((g) => (g.param ? [{ id: g.id, text: g.text, locked: g.locked, ...g.param }] : []));
}

/**
 * The server's refusal of a value for a guardrail field, shown before saving (backend `overlay.py`, same texts): a value
 * that is not stricter than the pack's weakens it; one outside the range is refused. null when the value is accepted.
 */
export function weakens(g: OverlayGuardrail, value: number): string | null {
  const stricter = g.stricter === 'higher' ? value > g.value : value < g.value;
  if (!stricter) return `${g.id} can only be tightened: ${g.field} ${g.value} → ${value} weakens it.`;
  if (value < g.min || value > g.max) return `${g.id}.${g.field} must be between ${g.min} and ${g.max}.`;
  return null;
}

const condText = (c: OverlayCond) => (c.op === 'exists' ? `${c.fact} exists` : `${c.fact} ${OP_SYMBOL[c.op]} ${JSON.stringify(c.value)}`);
const whenText = (when: OverlayCond[]) => (when.length ? ' when ' + when.map(condText).join(' and ') : '');

/** An operation in one plain line. */
export function opLabel(op: OverlayOp): string {
  switch (op.op) {
    case 'tighten':
      return `Tighten ${op.target}: ${op.field} ${op.seen} → ${op.value}`;
    case 'add_approver':
      return `Add approver ${op.role} to ${op.target}`;
    case 'add_step':
      return `Add step "${op.step}" at ${STAGE_LABEL[op.stage]}${whenText(op.when)}`;
    case 'shortcut':
      return `Skip from ${STAGE_LABEL[op.stage]} to ${STAGE_LABEL[op.to as GuardrailStage] ?? op.to}${whenText(op.when)}`;
    case 'set_param':
      return `Set ${op.path}: ${op.seen} → ${op.value}`;
  }
}

/** The next free "op-<n>". */
export function nextOpId(ops: OverlayOp[]): string {
  return 'op-' + (Math.max(0, ...ops.map((o) => Number(o.id.slice(3)) || 0)) + 1);
}

/** The four guardrail fields a customer may not change on a locked guardrail (the server answers `locked_guardrail`). */
export const LOCKED_FIELDS = ['Threshold', 'Scope', 'Exception', 'Suspend until'] as const;

/** The guardrail's customer controls: each of the four fields, disabled when the pack locks the guardrail, and the extra
 *  approver, which a locked guardrail still takes (only tightening and extra approvers are allowed, UC-17). */
export function guardrailControls(g: { locked: boolean }): { fields: { label: string; disabled: boolean }[]; addApprover: boolean } {
  return { fields: LOCKED_FIELDS.map((label) => ({ label, disabled: g.locked })), addApprover: true };
}

/** The ops with an extra approver for the guardrail (unchanged when the role is blank, already named there or already added). */
export function withApprover(ops: OverlayOp[], g: { id: string; approvers: string[] }, role: string): OverlayOp[] {
  const r = role.trim();
  if (!r || g.approvers.includes(r) || ops.some((o) => o.op === 'add_approver' && o.target === g.id && o.role === r)) return ops;
  return [...ops, { id: nextOpId(ops), by: '', note: '', op: 'add_approver', target: g.id, role: r }];
}

/** The ops with this tightening in place of any earlier one of the same guardrail field (the server compares in order). */
export function withTighten(ops: OverlayOp[], g: OverlayGuardrail, value: number): OverlayOp[] {
  const rest = ops.filter((o) => !(o.op === 'tighten' && o.target === g.id && o.field === g.field));
  return [...rest, { id: nextOpId(ops), by: '', note: '', op: 'tighten', target: g.id, field: g.field, value, seen: g.value }];
}
