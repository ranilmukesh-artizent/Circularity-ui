/**
 * History batches for replay (plan 9, P9-7.1, story X-06; backend/di/services/actions/replay.py). `replay.import` checks a CSV
 * of past decisions row by row and stores it (a bad row is held with a reason; a personal column refuses the whole file);
 * `replay.batches` lists an org's batches. Both are actions, called when the Replay panel asks, not cached reads.
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
}

/** Check and store a CSV text; `batchId` appends to a batch of the same pack and org unit. */
export const importHistory = (pack: string, org: string, csvText: string, batchId?: number): Promise<ActionResult<ImportedBatch>> =>
  invoke<ImportedBatch>('replay.import', { pack, org_unit_id: org, csv: csvText, ...(batchId === undefined ? {} : { batch_id: batchId }) });

export const replayBatches = (pack: string, org: string): Promise<ActionResult<{ batches: BatchView[] }>> =>
  invoke<{ batches: BatchView[] }>('replay.batches', { pack, org_unit_id: org });
