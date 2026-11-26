/** Wording of the case page's Ticket tab (P9-4.3, SD-01) over the `serviceDesk` block of a case. */
import type { Approval, LineEstimate, LineGate, OptionKey, TicketLine, TicketOption } from '../../api/serviceDesk';

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

/** The options with the recommended one first, the others in the order fix, swap, upgrade (P9-4.6, SD-04). */
export function optionOrder(options: TicketOption[], best: OptionKey | null | undefined): TicketOption[] {
  return [...options].sort((a, b) => Number(b.k === best) - Number(a.k === best));
}

/** "Customer pays $580.50 · margin $126.50 · 5 days out of use"; an option that cannot be offered says why instead. */
export function optionSummary(o: TicketOption, currency: string): string {
  if (!o.eligible || o.customer_price === null || o.margin === null) return `Not offered: ${o.why}`;
  const days = o.days === null ? 'days out of use not known' : `${o.days} ${o.days === 1 ? 'day' : 'days'} out of use`;
  const pay = o.customer_price === 0 ? 'Customer pays nothing' : `Customer pays ${money(o.customer_price, currency)}`;
  return `${pay} · margin ${money(o.margin, currency)} · ${days}`;
}

/** "62% expected take-up · expected margin $97.10" for an upgrade; the expected margin alone for the others. */
export function expectedLine(o: TicketOption, currency: string): string {
  const margin = `expected margin ${money(o.expected_margin ?? 0, currency)}`;
  return o.take_up === null ? margin : `${Math.round(o.take_up * 100)}% expected take-up · ${margin}`;
}

/** "Approval: Fleet manager (GR-14)" with the first hold, or "Approval: Standing policy P1 v2". */
export function approvalLine(a: Pick<Approval, 'owner' | 'holds'>): string {
  return a.holds.length ? `Approval: ${a.owner} (${a.holds.map((h) => h.id).join(', ')}). ${a.holds[0].reason}` : `Approval: ${a.owner}`;
}
const NAMES: Record<OptionKey, string> = { fix: 'Fix and return', swap: 'Covered swap', upgrade: 'Upgrade' };

/** "Fix and return beats Upgrade with credit above 28% credit" where the best option changes; else which stays best (P9-4.10, SD-09). */
export function flipLine(r: { from: OptionKey | null; crossing: { from: OptionKey; to: OptionKey; credit_pct: number } | null }): string {
  if (r.crossing) return `${NAMES[r.crossing.to]} beats ${NAMES[r.crossing.from]} with credit above ${Math.round(r.crossing.credit_pct * 100)}% credit`;
  return r.from ? `${NAMES[r.from]} stays best at every credit up to 40%` : 'No option can be offered yet';
}

/** "Expected margin peaks at 20% credit: $97.10". */
export function peakLine(r: { peak: { credit_pct: number; upgrade: number } | null; currency: string }): string {
  return r.peak ? `Expected margin of the upgrade peaks at ${Math.round(r.peak.credit_pct * 100)}% credit: ${money(r.peak.upgrade, r.currency)}` : 'The upgrade cannot be offered to this tool';
}

/** "Upgrade 9 · Fix 11 · Covered swap 2": the lines of a batch per chosen option; an option no line took is left out (P9-4.8, SD-07). */
export function splitLine(counts: Partial<Record<OptionKey, number>>): string {
  const parts: [OptionKey, string][] = [['upgrade', 'Upgrade'], ['fix', 'Fix'], ['swap', 'Covered swap']];
  return parts.filter(([k]) => (counts[k] ?? 0) > 0).map(([k, label]) => `${label} ${counts[k]}`).join(' · ');
}

/** "Customer pays $4,120 · margin $1,236 · expected margin $1,180" over the chosen options of a batch. */
export function batchTotalsLine(t: { customer_price: number; margin: number; expected_margin: number }, currency: string): string {
  return `Customer pays ${money(t.customer_price, currency)} · margin ${money(t.margin, currency)} · expected margin ${money(t.expected_margin, currency)}`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Market terms: US parts prices v2, US labour rates v1, US credit rules v1 · valid until 21 Oct 2026" (P9-4.9, SD-05). */
export function termsLine(t: { refs: string[]; valid_until: string }): string {
  const [y, m, d] = t.valid_until.split('-').map(Number);
  return `Market terms: ${t.refs.join(', ')} · valid until ${d} ${MONTHS[m - 1]} ${y}`;
}
