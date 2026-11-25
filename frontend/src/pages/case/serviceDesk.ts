/** Wording of the case page's Ticket tab (P9-4.3, SD-01) over the `serviceDesk` block of a case. */
import type { LineGate, TicketLine } from '../../api/serviceDesk';

const COVER: Record<string, string> = { fleet: 'fleet cover', warranty: 'warranty cover', none: 'no cover' };

/** "CRH · Cordless rotary hammer, 22 V · 18 months · MOT · fleet cover"; an empty fault code reads "unclear". */
export function lineSummary(l: Pick<TicketLine, 'model_class' | 'family' | 'age_months' | 'fault_code' | 'cover_type'>): string {
  const cover = l.cover_type ? (COVER[l.cover_type] ?? `${l.cover_type} cover`) : 'no cover';
  return [l.model_class, l.family, `${l.age_months} months`, l.fault_code || 'unclear', cover].join(' · ');
}

/** "Contract right: passed. Active contract line FL-CRH-46042" / "Safety recall: held. Safety recall RC-1 (repair): ...". */
export function gateLine(g: Pick<LineGate, 'name' | 'passed' | 'reason'>): string {
  return `${g.name}: ${g.passed ? 'passed' : 'failed'}. ${g.reason}`;
}

/** What a line needs a person for, or null when both checks pass. */
export function lineProblem(l: Pick<TicketLine, 'gates'>): string | null {
  const bad = l.gates.filter((g) => !g.passed);
  return bad.length ? bad.map((g) => g.reason).join('; ') : null;
}

/** "Ticket CS0010050 · batch BATCH-0050 · 22 tools" or "Ticket CS0010042 · 1 tool". */
export function ticketLine(t: { ticket: string; batch: boolean; batchId: string | null; lines: unknown[] }): string {
  const n = t.lines.length;
  return [`Ticket ${t.ticket}`, t.batch && t.batchId ? `batch ${t.batchId}` : '', `${n} ${n === 1 ? 'tool' : 'tools'}`].filter(Boolean).join(' · ');
}