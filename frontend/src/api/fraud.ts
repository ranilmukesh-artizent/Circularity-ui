/**
 * Fraud triage (plan 9, P9-2.11, story X-15; backend/di/services/actions/fraud.py): a returned asset whose fraud score reaches the
 * pack's threshold is held on intake, and only a person releases it or rejects the return. The hold is the case's `fraud` record
 * (`fraudOf`); the writes are the actions fraud.release and fraud.reject (approve.decisions, never an agent); `simulateFraud` runs
 * the triage over the org's open cases with another threshold or rule set before it is saved (fraud.simulate, manageFlows).
 * A write invalidates every read (invalidation.ts: an unknown family refreshes all), so the case and My work re-read.
 */
import { invoke } from './actions';
import type { CaseRec } from './case';
import type { WorkItem } from './mywork';
import type { ActionResult } from './types';

export interface FraudSignal {
  /** the pack rule's id */
  id: string;
  fired: boolean;
  value: unknown;
  source: string;
  /** when the evidence behind it was recorded (ISO), null for a count over the case history */
  at: string | null;
}

export type FraudStatus = 'held' | 'released' | 'rejected';

/** The model's review of a triage (P9-2.19): why the case looks or does not look like fraud, with the sources it cites. It
 *  only adds caution: a hold it asked for carries the signal `model_review`; it never releases one. */
export interface FraudReview {
  narrative: string;
  concerns: { text: string; sources: string[] }[];
  raise_hold: boolean;
}

/** The case's fraud record: what held it, and later who released it or rejected the return, and why. */
export interface FraudRecord {
  status: FraudStatus;
  score: number;
  threshold: number | null;
  signals: FraudSignal[];
  rule_version: string;
  held_at: string;
  by: string;
  review?: FraudReview;
  resolved_by?: string;
  resolved_at?: string;
  reason?: string;
}

/** The case's fraud record, or null when it was never held. */
export const fraudOf = (c: CaseRec): FraudRecord | null => (c as CaseRec & { fraud?: FraudRecord | null }).fraud ?? null;

/** "Held for fraud review: score 0.8 ≥ 0.6 · rule set v1" (without the threshold when the hold did not record one). */
export const fraudLine = (f: FraudRecord): string =>
  `Held for fraud review: score ${f.score}${f.threshold == null ? '' : ` ≥ ${f.threshold}`} · rule set ${f.rule_version}`;

/** "Model review: <narrative>", or null when no model reviewed the case. */
export const reviewLine = (f: FraudRecord): string | null => (f.review ? `Model review: ${f.review.narrative}` : null);

/** The ids the review cites, once each, in the order they come. */
export const reviewSources = (f: FraudRecord): string[] => [...new Set((f.review?.concerns ?? []).flatMap((c) => c.sources))];

/** True when the review itself asked for this hold (the computed score alone would not have held the case). */
export const heldByReview = (f: FraudRecord): boolean => f.signals.some((s) => s.id === 'model_review');

/** My work's "Fraud and compliance" rows: the exceptions fraud.hold opens (their title starts with this). */
export const FRAUD_TITLE = 'Fraud and compliance';
export const isFraudItem = (i: WorkItem): boolean => i.kind === 'exception' && i.title.startsWith(FRAUD_TITLE);

type Done = ActionResult<{ case_id: string; status: FraudStatus; log?: string }>;

/** Clear the hold (an Approver or Admin): the reason stays on the record. */
export const releaseFraud = (caseId: string, reason: string): Promise<Done> => invoke('fraud.release', { case_id: caseId, reason });

/** Decline the held return through the decision path, as the person: the reason stays on the record. */
export const rejectFraud = (caseId: string, reason: string): Promise<Done> => invoke('fraud.reject', { case_id: caseId, reason });

export interface FraudRuleInput {
  id: string;
  signal: string;
  weight: number;
  params?: Record<string, unknown>;
  source: string;
}

export interface FraudSimulation {
  pack: string;
  org_unit_id: string;
  cases: number;
  /** cases held by the rules in force, and by the ones simulated */
  held_now: number;
  held: number;
  by_signal: Record<string, number>;
  would_change: { case_id: string; was: boolean; now: boolean; score: number }[];
  pack_in_force: string;
}

/** The triage over an org's open cases of a pack with a threshold or rules of your own (it changes nothing). */
export const simulateFraud = (pack: string, org: string, opts: { threshold?: number; rules?: FraudRuleInput[] } = {}): Promise<ActionResult<FraudSimulation>> =>
  invoke('fraud.simulate', { pack, org_unit_id: org, ...opts });
