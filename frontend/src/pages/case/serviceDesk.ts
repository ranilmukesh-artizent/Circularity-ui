/** Wording of the case page's Ticket tab (P9-4.3, SD-01) over the `serviceDesk` block of a case. */
import type { LineEstimate, LineGate, TicketLine } from '../../api/serviceDesk';

const SYMBOL: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', AUD: 'A$' };

/** "$430" or "$430.50": whole amounts without cents, with the currency's symbol or its code. */
export function money(amount: number, currency: string): string {
  const sym = SYMBOL[currency] ?? (currency ? `${currency} ` : '');
  const digits = Number.isInteger(amount) ? 0 : 2;
  return `${sym}${amount.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

/** "$430 (range $395–$470) · 92% confidence · 186 similar repairs" (P9-4.4, SD-02). */
export function estimateLine(e: Pick<LineEstimate, 'point' | 'p10' | 'p90' | 'confidence' | 'n' | 'currency'>): string {
  const range = `${money(e.p10, e.currency)}–${money(e.p90, e.currency)}`;
  return `${money(e.point, e.currency)} (range ${range}) · ${Math.round(e.confidence * 100)}% confidence · ${e.n} similar repairs`;
}

/** "Priced without a technician" or "Draft: a technician checks", then the reason the server gave. */
export function estimateStatus(e: Pick<LineEstimate, 'auto' | 'reason'>): string {
  return `${e.auto ? 'Priced without a technician' : 'Draft: a technician checks'}. ${e.reason}`;
}

/** The key the matches were found on: same class, fault and age band, or, when there were too few, class and fault. */
export function keyUsed(k: LineEstimate['key_used']): string {
  return k === 'class_fault_age' ? 'same class, fault and age band' : 'same class and fault, any age';
}

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