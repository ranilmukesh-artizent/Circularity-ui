import type { OverlayOp, OverlayParam } from '../../api/types';
import { nextOpId } from './overlay';

type SetParam = Extract<OverlayOp, { op: 'set_param' }>;

/** How the Modeler names a pack parameter and shows its number (the pack publishes the rest: owner, range, direction). */
const KNOWN: Record<string, { label: string; unit: string }> = {
  'valuer.rulMin': { label: 'Fit-for-use threshold', unit: '%' },
};

export const paramLabel = (p: OverlayParam): string => KNOWN[p.path]?.label ?? p.path;

const unit = (p: OverlayParam): string => KNOWN[p.path]?.unit ?? '';

/** The parameters a customer may change from the pack view: every one the pack publishes, in the order it lists them. */
export const changeable = (params: OverlayParam[]): OverlayParam[] => params;

/** "Fit-for-use threshold 50% · owner Quality" (the pack's value, who owns it, the direction a customer may move it). */
export function paramLine(p: OverlayParam, value: number = p.value): string {
  const owner = p.owner ? ` · owner ${p.owner}` : '';
  return `${paramLabel(p)} ${value}${unit(p)}${owner}`;
}

/** Which way a customer may move it, in words. */
export const directionText = (p: OverlayParam): string =>
  p.direction === 'raise_only' ? `Raise only: ${p.min}–${p.max}, never below the pack's ${p.value}${unit(p)}${p.guardrail ? ` (${p.guardrail})` : ''}.` : `Between ${p.min} and ${p.max}.`;

/** The server's refusal of a value (backend `overlay.py`, same texts), shown before saving; null when it is accepted. */
export function paramRefusal(p: OverlayParam, value: number): string | null {
  if (value < p.min || value > p.max) return `${p.path} must be between ${p.min} and ${p.max}.`;
  if (p.direction === 'raise_only' && value < p.value) return `${p.guardrail ?? 'The pack'} can only be raised: ${p.path} ${p.value} → ${value} weakens it.`;
  return null;
}

/** The value the shown overlay sets for the parameter, if it sets one. */
export const proposedValue = (ops: OverlayOp[], path: string): number | null => {
  const op = ops.find((o): o is SetParam => o.op === 'set_param' && o.path === path);
  return op ? op.value : null;
};

/** The ops with this parameter set, in place of any earlier `set_param` of the same path. */
export function withParam(ops: OverlayOp[], p: OverlayParam, value: number): OverlayOp[] {
  const rest = ops.filter((o) => !(o.op === 'set_param' && o.path === p.path));
  return [...rest, { id: nextOpId(ops), by: '', note: '', op: 'set_param', path: p.path, value, seen: p.value }];
}
