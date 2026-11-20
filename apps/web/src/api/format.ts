/**
 * The demo's formatters, so every page prints numbers and dates exactly as index.html does. They are pure functions
 * (ports of the demo's money, fmtD, fmtDY and fmtN), so both backends use this code and nothing reads the engine.
 */

/** $1,234 / −$1,234 */
export const money = (n: number): string => (n < 0 ? '−' : '') + '$' + Math.abs(Math.round(n)).toLocaleString('en-US');
/** 07 Oct */
export const fmtDate = (d: Date | string | number): string =>
  new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
/** 07 Oct 2026 */
export const fmtDateYear = (d: Date | string | number): string =>
  new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
/** 1,234 */
export const fmtNumber = (n: number): string => Number(n).toLocaleString('en-US');
