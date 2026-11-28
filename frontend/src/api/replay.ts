/**
 * History batches for replay (plan 9, P9-7.1 and P9-7.2, story X-06; backend/di/services/actions/replay.py). `replay.import`
 * checks a CSV of past decisions row by row and stores it (a bad row is held with a reason; a personal column refuses the whole
 * file); `replay.batches` lists an org's batches; `replay.run` queues an as-of replay of a batch under a flow, `replay.report`
 * reads its four measures and `replay.runs` lists a flow's runs; `replay.importDemand` stores the demand windows a replay plans
 * against (P9-7.5). All are actions, called when the Replay panel asks, not cached reads.
 */
import { invoke } from './actions';
import type { ActionResult } from './types';

export interface HeldRow {
  n: number;
  item_id: string;
  held_reason: string;
}

export interface Batch {
  id: number;
  pack: string;
  org_unit_id: string;
  rows: number;
  held: number;
  /** [from, to] as ISO dates, or null when no row was good */
  period: [string, string] | null;
  held_reasons: Record<string, number>;
}

export type ImportedBatch = Batch & { log?: string };
export interface BatchView extends Batch {
  /** the first 50 held rows */
  held_items: HeldRow[];
  /** demand windows kept and held (P9-7.5) */
  demand_rows: number;
  demand_held: number;
}

/** Check and store a CSV text; `batchId` appends to a batch of the same pack and org unit. */
export const importHistory = (pack: string, org: string, csvText: string, batchId?: number): Promise<ActionResult<ImportedBatch>> =>
  invoke<ImportedBatch>('replay.import', { pack, org_unit_id: org, csv: csvText, ...(batchId === undefined ? {} : { batch_id: batchId }) });

/** Import the pack's synthetic sample history (every value invented), so a replay can run before real history is loaded. */
export const importSampleHistory = (pack: string, org: string, rows?: number): Promise<ActionResult<ImportedBatch>> =>
  invoke<ImportedBatch>('replay.importSample', { pack, org_unit_id: org, ...(rows === undefined ? {} : { rows }) });

export interface HeldDemand {
  n: number;
  demand_id: string;
  held_reason: string;
}

export type ImportedDemand = Batch & { demand_rows: number; demand_held: number; held_demand: HeldDemand[]; log?: string };

/** Check and store a CSV of demand windows (demand_id, route, opens_at, closes_at, value, capacity) for a batch (P9-7.5). */
export const importDemand = (batchId: number, csvText: string): Promise<ActionResult<ImportedDemand>> =>
  invoke<ImportedDemand>('replay.importDemand', { batch_id: batchId, csv: csvText });

export const replayBatches = (pack: string, org: string): Promise<ActionResult<{ batches: BatchView[] }>> =>
  invoke<{ batches: BatchView[] }>('replay.batches', { pack, org_unit_id: org });

// ---------------------------------------------------------------- runs (P9-7.2)
export type RunStatus = 'queued' | 'running' | 'done' | 'failed';

export interface RouteMixRow {
  route: string;
  actual_pct: number;
  flow_pct: number;
}

export interface ReplayUplift {
  /** percent of the actual routes' net, modelled */
  primary: number;
  band80: [number, number];
  band95: [number, number];
  secondary: number;
  bias: number;
  /** the lower of primary and secondary: the report leads with it */
  conservative: number;
  basis: 'modelled';
}

export interface ReplayReport {
  run_id: number;
  batch_id: number;
  /** "draft" or the version number replayed */
  flow_ver: string;
  n_items: number;
  n_held_rows: number;
  n_decided: number;
  /** business days (Mon to Fri) between the first and last decision */
  days: number;
  route_mix: RouteMixRow[];
  straight_through_pct: number;
  approvals_per_day: number;
  exceptions_per_day: number;
  by_guardrail: { guardrail: string; owner: string; approvals: number; exceptions: number }[];
  uplift: ReplayUplift;
  /** case-by-case net minus planned net: what capacity and competing returns cost (P9-7.5); 0 with no demand file */
  constraint_loss: number;
  agreement_pct: number;
  /** decided items that would wait for an approval or raise an exception (P9-7.6) */
  held_for_person: number;
  /** waterfall inputs (P9-7.6): sums of the actual and the flow's planned nets */
  actual_net: number;
  flow_net: number;
  repricing: number;
  route_changes: { route: string; amount: number }[];
  flips: { item_id: string; actual: string | null; flow: string | null; delta: number; reason: string; gate?: string | null; trace?: string }[];
  leakage: { item_id: string; fact: string; fact_at: string | null; decided_at: string }[];
  data_quality: { reason: string; count: number }[];
  method: string;
}

export interface RunView {
  run_id: number;
  batch_id: number;
  flow_id: number;
  flow_ver: string;
  dver: number | null;
  status: RunStatus;
  error: string | null;
  created_by: string;
  created_at: string;
  finished_at: string | null;
}

/** Queue a replay of a batch under a flow: `flowVer` is "draft" or a version number; left out, the draft if there is one. */
export const runReplay = (batchId: number, flowId: number, flowVer?: string): Promise<ActionResult<{ run_id: number; status: RunStatus }>> =>
  invoke<{ run_id: number; status: RunStatus }>('replay.run', { batch_id: batchId, flow_id: flowId, ...(flowVer === undefined ? {} : { flow_ver: flowVer }) });

/** One step of the back-test waterfall (P9-7.6): the actual net (`base`), a change (`delta`), the net uplift (`result`). The base
 * and the deltas add up to the flow's net. */
export interface WaterfallStep {
  step: string;
  amount: number;
  kind: 'base' | 'delta' | 'result';
}

/** One of the largest flips, explained: the gate or rule that decided it and the decision's own trace text. */
export interface ExplainedFlip {
  item_id: string;
  from: string | null;
  to: string | null;
  delta: number;
  reason: string;
  gate: string | null;
  trace: string;
}

/** `replay.report`: the run, its report and the three parts of the back-test page, all computed by the server. */
export type ReplayReportOut = RunView & {
  report: ReplayReport | null;
  waterfall: WaterfallStep[];
  top_flips: ExplainedFlip[];
  /** the fixed method text, shown as sent */
  method_note: string;
};

export const replayReport = (runId: number): Promise<ActionResult<ReplayReportOut>> => invoke<ReplayReportOut>('replay.report', { run_id: runId });

export const replayRuns = (flowId: number): Promise<ActionResult<{ runs: RunView[] }>> => invoke<{ runs: RunView[] }>('replay.runs', { flow_id: flowId });

/** A finished run with the flow it replayed, for the Analytics run picker. */
export type RunPick = RunView & { flow_name: string; template_key: string; org_unit_id: string };

/** The finished runs of every flow the signed-in person may see, newest first (the Back-test section's picker). */
export const finishedRuns = (): Promise<ActionResult<{ runs: RunPick[] }>> => invoke<{ runs: RunPick[] }>('replay.runs', {});
