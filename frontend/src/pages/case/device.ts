/** Wording of the case page's Device tab (P9-6.4, DV-01) over the `device` block of a case. */
import { money } from '../../api/format';
import type { DeviceView, QuoteCheck, QuoteRow } from '../../api/device';

/** "iPhone 14 · 128 GB · declared B · quote $410 · partner P01"; a bulk lot: "20 devices · batch BATCH-0020 · grade B · partner P01". */
export function deviceLine(v: DeviceView): string {
  if (v.bulk) {
    return [`${v.lines.length} devices`, v.batch ? `batch ${v.batch}` : '', `grade ${v.grade}`, `partner ${v.partner}`].filter(Boolean).join(' · ');
  }
  return [
    v.model, v.storageGb != null ? `${v.storageGb} GB` : '', `declared ${v.declaredGrade}`,
    v.quote ? `quote ${money(v.quote.amount)}` : '', `partner ${v.partner}`,
  ].filter(Boolean).join(' · ');
}

/** "Reference $330 a unit, from the market feed" or "... from the quote". */
export function refLine(v: DeviceView): string {
  return `Reference ${money(v.ref)} a unit, from ${v.refSource === 'feed' ? 'the market feed' : 'the quote'}`;
}

/** "grade C (graded)" or "grade B (declared)". */
export function gradeLine(v: DeviceView): string {
  return `grade ${v.grade} (${v.graded ? 'graded' : 'declared'})`;
}

const FIELD_LABEL = { imei: 'IMEI', model: 'Model', storage: 'Storage' } as const;
const said = (field: QuoteRow['field'], v: string | number | null) => (field === 'storage' ? `${v} GB` : String(v));

/** "Storage quoted 256 GB, read 128 GB" (the backend says the same, verify.mismatch_line). */
export function mismatchLine(m: Pick<QuoteRow, 'field' | 'quoted' | 'read'>): string {
  return `${FIELD_LABEL[m.field]} quoted ${said(m.field, m.quoted)}, read ${said(m.field, m.read)}`;
}

/** What the quote check says in one line: "Quote matches the device read", "Waiting for the lab's diagnostics" or the
 * mismatches joined, then who owns the exception and where it stands. */
export function quoteCheckLine(q: QuoteCheck): string {
  if (q.state === 'waiting') return "Waiting for the lab's diagnostics";
  if (q.state === 'match') return 'Quote matches the device read';
  const lines = q.rows.filter((r) => r.mismatch).map(mismatchLine).join('; ');
  const where = q.item ? (q.item.state === 'open' ? 'open' : `resolved${q.item.outcome ? `: ${q.item.outcome}` : ''}`) : 'not opened';
  return `${lines}. ${q.owner}, ${where}`;
}

/** The lines of a bulk lot: "<imei> · iPhone 14 · 128 GB · grade B · quote $410". */
export function lotLines(v: DeviceView): string[] {
  return v.lines.map((l) => [l.imei, l.model, `${l.storageGb} GB`, `grade ${l.grade}`, `quote ${money(l.quote)}`].join(' · '));
}
