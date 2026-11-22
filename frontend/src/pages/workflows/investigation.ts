/**
 * The investigation panel's text for a failed run (frInvest), with the retries the run used: the demo's panel always
 * says "failed after 3 retries" and logs attempts 1 and 2 before the error; here the count is the workflow's Retries
 * setting (3 unless a person saved another), so the default reads exactly as the demo.
 */

/** The retries a run used: the run's own record, else the workflow's saved setting, else 3. */
export const retriesOf = (run: { retries?: number } | undefined, w: { retries?: number }): number => run?.retries ?? w.retries ?? 3;

/** "failed after 3 retries", "failed after 1 retry", "failed with no retries". */
export const failedAfter = (n: number): string => (n === 0 ? 'failed with no retries' : 'failed after ' + n + ' retr' + (n === 1 ? 'y' : 'ies'));

/** The error log: start, one warning per failed attempt before the last, the error, then the downstream note. Times
 * are seconds before the run's end (the demo's 9, 6, 4, 2 and 0 for 3 retries). */
export function errorLog(n: number, run: { id: string; trig: string; note: string; ts: number }, label: string): string {
  const t = (o: number) => new Date(run.ts - o).toISOString().slice(11, 19);
  const warns = Math.max(0, n - 1), start = 2000 + 2000 * warns + 3000;
  const lines = [`${t(start)} INFO  run ${run.id} started · trigger ${run.trig}`];
  for (let k = 1; k <= warns; k++) lines.push(`${t(2000 + 2000 * (warns - k + 1))} WARN  ${label}: attempt ${k} failed`);
  lines.push(`${t(2000)} ERROR ${run.note || label + ' failed'}`);
  lines.push(`${t(0)} INFO  downstream steps marked upstream failed; held records kept`);
  return lines.join('\n');
}
