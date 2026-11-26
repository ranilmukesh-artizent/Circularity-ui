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
