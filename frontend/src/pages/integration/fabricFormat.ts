/** Number, date and count formats of the Connection Fabric pages. */
import { fmtNumber } from '../../api/format';

export const fmtN = (n: number) => fmtNumber(n);
export const when = (ts: number | string | Date) =>
  new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
export const plural = (n: number, w: string, p = w + 's') => n + ' ' + (n === 1 ? w : p);
export const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
