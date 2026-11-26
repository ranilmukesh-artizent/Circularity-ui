/** How a report preview cell reads on screen: stage ids as the words the case pages use, an em dash for an empty cell,
 *  and ids that must not break across lines. The CSV export keeps the raw values; this is presentation only. */
import { fmtNumber } from '../../api/format';

const STAGE_LABEL: Record<string, string> = {
  awaiting_approval: 'Awaiting approval',
  approved: 'Approved · handing off',
  executing: 'Handed off',
  reeval: 'Re-evaluate',
  closed: 'Closed',
  none: 'Not started',
};

const ID = /^[A-Z]{1,5}-[A-Z0-9]+(?:-[A-Z0-9]+)*$/;

export interface ReportCell { text: string; id: boolean; empty: boolean; num: boolean }

export function reportCell(header: string | number | undefined, v: string | number | null | undefined): ReportCell {
  if (v == null || String(v).trim() === '') return { text: '—', id: false, empty: true, num: false };
  if (typeof v === 'number') return { text: Math.abs(v) >= 1000 ? fmtNumber(v) : String(v), id: false, empty: false, num: true };
  const s = String(v);
  if (/^stage$/i.test(String(header ?? '')) && STAGE_LABEL[s]) return { text: STAGE_LABEL[s], id: false, empty: false, num: false };
  return { text: s, id: ID.test(s), empty: false, num: false };
}
