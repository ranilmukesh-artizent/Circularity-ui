/**
 * What the Replay panel says about a replay report (plan 9, P9-7.2, story X-06): the wording of the four numbers. Pure; the
 * numbers themselves are the server's (backend/di/services/replay), never computed here.
 */
import type { ReplayReport, ReplayUplift, RunStatus } from '../../api/replay';

/** Percent with an explicit sign for an uplift: "+3.2 %" or "-1.0 %". */
export const signed = (n: number): string => `${n >= 0 ? '+' : '-'}${Math.abs(n).toFixed(1)} %`;

/** "+3.2 % (80 % band -1.0 % to +7.4 %), modelled": the conservative figure leads, as the report does. */
export const upliftLine = (u: ReplayUplift): string =>
  `${signed(u.conservative)} (80 % band ${signed(u.band80[0])} to ${signed(u.band80[1])}), ${u.basis}`;

/** Whether the run has ended, so the panel stops asking. */
export const finished = (s: RunStatus): boolean => s === 'done' || s === 'failed';

/** "draft" or "v3", for a run's flow version. */
export const versionLabel = (v: string): string => (v === 'draft' ? 'draft' : `v${v}`);

/** The three headline loads as the panel lists them, in the order the story reads them. */
export const headline = (r: ReplayReport): { key: string; label: string; value: string }[] => [
  { key: 'straight', label: 'Straight-through', value: `${r.straight_through_pct.toFixed(1)} %` },
  { key: 'approvals', label: 'Approvals a day', value: r.approvals_per_day.toFixed(1) },
  { key: 'exceptions', label: 'Exceptions a day', value: r.exceptions_per_day.toFixed(1) },
];
