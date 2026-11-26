/** Number, date and count formats of the Connection Fabric pages. */
import { fmtNumber } from '../../api/format';

export const fmtN = (n: number) => fmtNumber(n);
export const when = (ts: number | string | Date) =>
  new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
export const plural = (n: number, w: string, p = w + 's') => n + ' ' + (n === 1 ? w : p);
export const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

/** A conflict's record as a person reads it: a key of "Tenant:ID" shows the ID, the tenant beside it; the raw key stays
 *  as secondary text (UI QA 21). */
export function recordLabel(key: string): { name: string; scope: string | null } {
  const i = key.indexOf(':');
  return i > 0 && i < key.length - 1 ? { name: key.slice(i + 1), scope: key.slice(0, i) } : { name: key, scope: null };
}
