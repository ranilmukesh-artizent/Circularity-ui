/** The "System of record" line and the Custody list of a case (P9-1.10, X-08): wording over `recordMatch` and `custody`. */
import type { CustodyEntry, RecordMatchView } from '../../api/case';
import { fmtDate } from '../../api/format';

const LABEL: Record<CustodyEntry['event'], string> = {
  received: 'Received', matched: 'Matched to the system of record', moved: 'Moved', released: 'Released',
};

const stamp = (iso: string): string => {
  const t = new Date(iso);
  return `${fmtDate(t)} ${String(t.getUTCHours()).padStart(2, '0')}:${String(t.getUTCMinutes()).padStart(2, '0')} UTC`;
};

/** "3 h ago", "12 min ago", "2 d ago" from minutes. */
export function ago(minutes: number): string {
  if (minutes < 60) return `${minutes} min ago`;
  return minutes < 1440 ? `${Math.floor(minutes / 60)} h ago` : `${Math.floor(minutes / 1440)} d ago`;
}

/**
 * Newest first: "Moved to Warehouse 2 · <source> · 07 Oct 09:00 UTC · by system". The location follows "at" for a receipt
 * and a release, "to" for a move; a part that is not known is left out.
 */
export function custodyLines(custody: CustodyEntry[] | null | undefined): string[] {
  return [...(custody ?? [])].reverse().map((e) => {
    const where = e.location ? ` ${e.event === 'moved' ? 'to' : 'at'} ${e.location}` : '';
    return [LABEL[e.event] + where, e.source, stamp(e.at), e.by ? `by ${e.by}` : ''].filter(Boolean).join(' · ');
  });
}

/**
 * "System of record: found in <system> record <key>, synced <time ago>", or "Not found in <system>: exception sent to
 * <owner>". No line for a case whose pack has no system of record.
 */
export function recordMatchLine(rm: RecordMatchView | null | undefined): string | null {
  if (!rm) return null;
  if (!rm.found) return `Not found in ${rm.system}: exception sent to ${rm.owner ?? 'the owner'}`;
  const synced = rm.syncedMinutesAgo != null ? `, synced ${ago(rm.syncedMinutesAgo)}` : '';
  return `System of record: found in ${rm.system} record ${rm.key}${synced}`;
}
