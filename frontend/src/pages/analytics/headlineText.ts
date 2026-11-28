/** The sentence Analytics opens on, computed from the same metrics as the four figures under it (never typed). */
import { kfmt, type Metrics } from '../../api/analytics';

export interface HeadlineParts { empty: boolean; amount: string; tone: 'pos' | 'neg'; before: string; after: string }

const int = new Intl.NumberFormat('en-US');

/** "Circularity recovered $2.31M more than the baseline across 1,277 reconciled decisions; cases close in a median 14 days, 38% faster than today." */
export function headlineParts(m: Pick<Metrics, 'uplift' | 'rc' | 'days' | 'baseDays'>): HeadlineParts {
  if (!m.rc.length) return { empty: true, amount: '', tone: 'pos', before: 'No reconciled decisions in this selection yet, so there is no gain to report.', after: '' };
  const less = m.uplift < 0;
  const faster = m.baseDays ? Math.round((1 - m.days / m.baseDays) * 100) : 0;
  const pace = !m.baseDays || faster === 0 ? 'about as fast as today' : faster > 0 ? `${faster}% faster than today` : `${-faster}% slower than today`;
  return {
    empty: false, amount: kfmt(Math.abs(m.uplift)), tone: less ? 'neg' : 'pos',
    before: 'Circularity recovered ', after: ` ${less ? 'less' : 'more'} than the baseline across ${int.format(m.rc.length)} reconciled decisions; cases close in a median ${m.days} days, ${pace}.`,
  };
}

/** "1,277 reconciled of 1,400 decisions · Jan to Dec · Customer A, B" */
export const headlineMeta = (reconciled: number, all: number, period: string, tenants: string[]): string =>
  [`${int.format(reconciled)} reconciled of ${int.format(all)} decisions`, period, tenants.join(', ')].filter(Boolean).join(' · ');
