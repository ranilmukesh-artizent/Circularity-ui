/**
 * Publishing a flow in steps (plan 9, P9-7.3, story X-06; backend/di/services/actions/rollout.py): a canary of the approved
 * candidate in one region at a share, widened by a person, then full. All are actions, called when the Rollout panel asks.
 * Starting, widening and going full are refused to the person who made the flow's changes (maker-checker); agents never run them.
 */
import { invoke } from './actions';
import type { ActionResult } from './types';

export type RolloutStage = 'replay' | 'shadow' | 'canary' | 'full' | 'paused' | 'rolled_back';

/** The steps the panel draws, in order. */
export const ROLLOUT_STEPS = ['replay', 'shadow', 'canary', 'full'] as const;

export interface RolloutRow {
  id: number;
  stage: RolloutStage;
  region_key: string;
  region: string | null;
  share: number;
  candidate_ver: number | null;
  base_ver: number | null;
}

/** What a person may do now: null when allowed, else the reason it is refused (shown on the button). */
export interface RolloutCan {
  startCanary: string | null;
  widen: string | null;
  pause: string | null;
  full: string | null;
  rollback: string | null;
}

export interface Rollout {
  flow_id: number;
  name: string;
  /** null: a published flow that never had a rollout */
  stage: RolloutStage | null;
  status: string;
  base_ver: number;
  candidate_ver: number | null;
  rollouts: RolloutRow[];
  counts: { canary: number; control: number };
  replay_run_id: number | null;
  replay_done: boolean;
  can: RolloutCan;
}

export interface RolloutDone {
  flow_id: number;
  stage: RolloutStage;
  log?: string;
}

export const getRollout = (flowId: number): Promise<ActionResult<Rollout>> => invoke<Rollout>('rollout.get', { flow_id: flowId });

/** Release the candidate to `share` percent of the cases of `region` (`regionKey` is a case fact, default `market`). */
export const startCanary = (flowId: number, region: string, share: number, regionKey?: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.startCanary', { flow_id: flowId, region, share, ...(regionKey ? { region_key: regionKey } : {}) });

/** Raise the share, add a region, or both; widening a paused canary resumes it. */
export const widenRollout = (flowId: number, share?: number, region?: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.widen', { flow_id: flowId, ...(share === undefined ? {} : { share }), ...(region ? { region } : {}) });

export const goFull = (flowId: number): Promise<ActionResult<RolloutDone>> => invoke<RolloutDone>('rollout.full', { flow_id: flowId });

export const pauseRollout = (flowId: number, reason: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.pause', { flow_id: flowId, reason });

export const rollbackRollout = (flowId: number, reason: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.rollback', { flow_id: flowId, reason });

/** "Canary: FR at 20 % of volume" (one clause per region), or '' with no canary rows. */
export const canaryLine = (rows: Pick<RolloutRow, 'region' | 'share'>[]): string =>
  rows.length ? 'Canary: ' + rows.map((r) => `${r.region ?? 'all regions'} at ${r.share} % of volume`).join(', ') : '';

/** One arm's figures in the canary report (rates are 0 to 1; the means are null while no case has the value). */
export interface ArmStats {
  n: number;
  decided: number;
  override_rate: number;
  exception_rate: number;
  hold_rate: number;
  mean_net: number | null;
  mean_realised: number | null;
}

/** Canary against control (backend/di/services/modeler/canary_stats.py): every figure is computed by the server, none by a model. */
export interface RolloutReport {
  flow_id: number;
  name: string;
  stage: RolloutStage | null;
  canary: ArmStats;
  control: ArmStats;
  /** the difference of mean nets (canary minus control) with its bootstrap bands; null while an arm has no values */
  band: { diff: number; band80: [number, number]; band95: [number, number] } | null;
  n_needed: number;
  rules: Record<string, number>;
  /** "Too few cases to tell a difference yet" while either arm is below the cases it needs */
  note: string | null;
  /** the stop rule breached right now, if any */
  breach: string | null;
  /** set while the canary is paused: why, and whether the system did it */
  paused: { reason: string; by: string; automatic?: boolean; at?: string } | null;
}

export const rolloutReport = (flowId: number): Promise<ActionResult<RolloutReport>> =>
  invoke<RolloutReport>('rollout.report', { flow_id: flowId });

const pct = (x: number): string => `${Math.round(x * 100)} %`;
const money = (x: number | null): string => (x === null ? '–' : Math.round(x).toLocaleString('en-US'));

/** The comparison table rows: [label, canary, control]. */
export const reportRows = (r: Pick<RolloutReport, 'canary' | 'control'>): [string, string, string][] => [
  ['Cases', String(r.canary.n), String(r.control.n)],
  ['Override rate', pct(r.canary.override_rate), pct(r.control.override_rate)],
  ['Exception rate', pct(r.canary.exception_rate), pct(r.control.exception_rate)],
  ['Holds', pct(r.canary.hold_rate), pct(r.control.hold_rate)],
  ['Mean net', money(r.canary.mean_net), money(r.control.mean_net)],
];

/** "Difference of mean net: +10 (80 % band -2 to +21)", or '' while an arm has no values. */
export const bandLine = (r: Pick<RolloutReport, 'band'>): string => {
  if (!r.band) return '';
  const s = (x: number) => (x > 0 ? '+' : '') + Math.round(x).toLocaleString('en-US');
  return `Difference of mean net: ${s(r.band.diff)} (80 % band ${s(r.band.band80[0])} to ${s(r.band.band80[1])})`;
};

// ---------------------------------------------------------------- the market canary of the service-desk tables (P9-7.7, SD-10)
/** A table rollout hangs on the org's tool-fleet flow: `subject_kind "table"` with that flow's id as `subject_id`. */
const tableOf = (flowId: number) => ({ subject_kind: 'table', subject_id: String(flowId) });

export interface TableRollout extends Omit<Rollout, 'base_ver' | 'candidate_ver'> {
  subject_kind: 'table';
  /** the markets of the service desk, for the picker */
  markets: string[];
}

/** "Decision tables · FR": how the Rollout panel names the subject of a table canary. */
export const tableSubject = (market: string): string => `Decision tables · ${market}`;

/** The service-desk measures of one arm (shares 0 to 1; the means are null while no ticket has the value). */
export interface SdMeasures {
  tickets: number;
  option_mix: { fix: number; swap: number; upgrade: number };
  margin_per_ticket: number | null;
  upgrade_take_up: number | null;
  days_to_option: number | null;
}

export interface TableReport extends Omit<RolloutReport, 'canary' | 'control'> {
  subject_kind: 'table';
  canary: ArmStats & { sd: SdMeasures };
  control: ArmStats & { sd: SdMeasures };
  /** the arms as the panel names them: `Canary` and `Standard quote` */
  labels: { canary: string; control: string };
  regions: { region: string; share: number; stage: RolloutStage }[];
}

export const getTableRollout = (flowId: number): Promise<ActionResult<TableRollout>> => invoke<TableRollout>('rollout.get', tableOf(flowId));

export const startTableCanary = (flowId: number, market: string, share: number): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.startCanary', { ...tableOf(flowId), region_key: 'market', region: market, share });

export const widenTableCanary = (flowId: number, share: number): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.widen', { ...tableOf(flowId), share });

export const pauseTableCanary = (flowId: number, reason: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.pause', { ...tableOf(flowId), reason });

export const rollbackTableCanary = (flowId: number, reason: string): Promise<ActionResult<RolloutDone>> =>
  invoke<RolloutDone>('rollout.rollback', { ...tableOf(flowId), reason });

export const tableReport = (flowId: number): Promise<ActionResult<TableReport>> => invoke<TableReport>('rollout.report', tableOf(flowId));

/** The comparison rows of a table canary: [label, canary, standard quote] (option mix, margin per ticket, take-up, days). */
export const tableReportRows = (r: Pick<TableReport, 'canary' | 'control'>): [string, string, string][] => {
  const mix = (a: SdMeasures) => `fix ${pct(a.option_mix.fix)}, swap ${pct(a.option_mix.swap)}, upgrade ${pct(a.option_mix.upgrade)}`;
  const take = (x: number | null) => (x === null ? '–' : pct(x));
  const days = (x: number | null) => (x === null ? '–' : x.toFixed(1));
  const c = r.canary.sd;
  const k = r.control.sd;
  return [
    ['Tickets', String(r.canary.n), String(r.control.n)],
    ['Option mix', mix(c), mix(k)],
    ['Margin per ticket', money(c.margin_per_ticket), money(k.margin_per_ticket)],
    ['Upgrade take-up', take(c.upgrade_take_up), take(k.upgrade_take_up)],
    ['Days to the quoted option', days(c.days_to_option), days(k.days_to_option)],
  ];
};
