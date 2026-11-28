/** The headline of a pack in Analytics (plan 11, D1): pure helpers that turn the server's figures into the words and numbers the section shows.
 *  Nothing is computed here that the server did not send, except proportions for drawing. */
import type { HeadlineFigure, HeadlineGrades, HeadlineRoute, PackHeadline } from '../../api/analytics';

export const PERIODS = [30, 90, 180, 365] as const;

const int = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const one = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const MINUS = '−';

/** Whole dollars with a true minus sign. */
export const formatUsd = (n: number): string => (n < 0 ? MINUS + usd.format(-n) : usd.format(n));

/** Days to one decimal; under one day is said so rather than shown as 0. */
export function formatDays(d: number): string {
  if (d < 1) return 'Under 1 day';
  return one.format(d) + (one.format(d) === '1' ? ' day' : ' days');
}

/** Kilograms of CO2e; a tonne and over in tonnes. */
export const formatKg = (kg: number): string => (Math.abs(kg) >= 1000 ? one.format(kg / 1000) + ' t' : int.format(kg) + ' kg');

/** The value of a figure as text; null when no case supports it. */
export function formatFigure(f: Pick<HeadlineFigure, 'value' | 'unit'>): string | null {
  if (f.value === null) return null;
  switch (f.unit) {
    case 'usd': return formatUsd(f.value);
    case 'pct': return one.format(f.value) + '%';
    case 'days': return formatDays(f.value);
    case 'kg': return formatKg(f.value);
    default: return int.format(f.value);
  }
}

const cases = (n: number): string => (n === 1 ? 'case' : 'cases');

/** "last 90 days" */
export const periodLabel = (days: number): string => `last ${int.format(days)} days`;

/** What a figure rests on, with its count and the period: "2 of 3 cases on a sale channel, last 90 days". */
export function figureBasis(f: Pick<HeadlineFigure, 'id' | 'n' | 'of'>, days: number): string {
  const p = ', ' + periodLabel(days);
  const n = int.format(f.n), of = int.format(f.of);
  switch (f.id) {
    case 'net': return `${n} closed ${cases(f.n)}${p}`;
    case 'days': return `median of ${n} closed ${cases(f.n)}${p}`;
    case 'carbon': return `${n} of ${of} closed ${cases(f.of)} carry a factor${p}`;
    case 'sell_through': case 'listed': return `${n} of ${of} ${cases(f.of)} on a sale channel${p}`;
    case 'reuse_rate': return `${n} of ${of} ${cases(f.of)} with a route${p}`;
    default: return `${n} of ${of} ${cases(f.of)} opened${p}`;
  }
}

/** The tag a figure that is not a plain count carries. */
export const basisTag = (b: HeadlineFigure['basis']): string | null => (b === 'modelled' ? 'Modelled' : b === 'estimated' ? 'Estimated' : null);

/** The section's title. */
export const headlineTitle = (h: Pick<PackHeadline, 'name'>): string => h.name;

/** A route row for drawing: the share of the largest route's cases that the row's cases and its closed cases make (0 to 1), and the text of its counts. */
export interface RouteBar { id: string; name: string; total: number; closed: number; closedShare: number; openShare: number; net: string; cases: string; sold: string }
export function routeBars(routes: HeadlineRoute[]): RouteBar[] {
  const max = Math.max(1, ...routes.map((r) => r.n));
  return routes.map((r) => ({
    id: r.id, name: r.name, total: r.n, closed: r.closed, closedShare: r.closed / max, openShare: (r.n - r.closed) / max,
    net: formatUsd(r.net), cases: int.format(r.n), sold: r.n ? one.format((r.closed / r.n) * 100) + '%' : '',
  }));
}

/** A grade-by-route cell: its count and its strength 0 to 1 against the largest cell (for the tint). */
export interface GradeCell { route: string; n: number; strength: number }
export interface GradeRow { grade: string; total: number; cells: GradeCell[] }
export function gradeRows(g: HeadlineGrades): GradeRow[] {
  const max = Math.max(1, ...g.rows.flatMap((r) => g.routes.map((x) => r.cells[x.id] ?? 0)));
  return g.rows.map((r) => ({
    grade: r.grade, total: r.total,
    cells: g.routes.map((x) => ({ route: x.id, n: r.cells[x.id] ?? 0, strength: (r.cells[x.id] ?? 0) / max })),
  }));
}

/** The one sentence that stands in for the section when the period holds no case. */
export const emptySentence = (h: Pick<PackHeadline, 'name' | 'period'>): string =>
  `No ${h.name.toLowerCase()} cases were opened in the ${periodLabel(h.period.days)}. Pick a longer period, or open cases from the source systems this pack reads.`;

/** The carbon note: which factor set the estimate used. */
export const carbonSetNote = (sets: string[]): string =>
  sets.length ? `Estimated from factor set ${sets.join(', ')} (sample factors, not measured).` : '';
