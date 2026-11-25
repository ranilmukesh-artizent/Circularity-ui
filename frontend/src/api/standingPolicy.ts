/**
 * Standing policies (plan 9, P9-2.5, story X-05; backend/di/services/actions/standing_policy.py): a person-owned approval policy that
 * approves a submitted decision below its limits. A person drafts and submits it, a different person approves or retires it
 * (maker-checker); no agent approves. Every write is a standingPolicy.* action; the list is a read action cached per pack and org.
 * A write invalidates every read (invalidation.ts: an unknown family refreshes all), so the Modeler's panel re-reads.
 */
import { invoke, read } from './actions';
import type { ActionResult } from './types';

export interface StandingRules {
  max_value: number;
  min_confidence: number;
  routes: string[] | null;
  classes: string[] | null;
  markets: string[] | null;
}

export type StandingStatus = 'draft' | 'review' | 'active' | 'retired';

export interface StandingPolicy {
  id: string;
  pack: string;
  org_unit_id: string;
  name: string;
  ver: number;
  status: StandingStatus;
  rules: StandingRules;
  owner: string;
  maker: string;
  checker: string | null;
  approved_at: string | null;
}

export interface StandingPolicyList {
  pack: string;
  org_unit_id: string;
  policies: StandingPolicy[];
  /** the active policy in force for this org: its own, or the nearest unit above's */
  in_force: StandingPolicy | null;
  /** the pack's value limit (an Approval guardrail's value_limit), null when it sets none */
  pack_limit: number | null;
  /** the flow's confidence threshold at the Decide stage */
  threshold: number;
  can: { edit: boolean; approve: boolean };
}

type Done = ActionResult<{ id: string; status: StandingStatus; ver?: number; log?: string }>;

/** The policies of a pack at an org unit, and the one in force there (read action, Suspense cache). */
export const listStandingPolicies = (pack: string, org: string): StandingPolicyList => read<StandingPolicyList>('standingPolicy.list', { pack, org_unit_id: org });

export interface StandingDraft {
  pack: string;
  org: string;
  name: string;
  rules: Partial<StandingRules> & Pick<StandingRules, 'max_value' | 'min_confidence'>;
  owner: string;
  /** a draft or policy in review to change; leave out for a new one */
  id?: string;
}

export const saveStandingPolicy = (d: StandingDraft): Promise<Done> =>
  invoke('standingPolicy.save', { pack: d.pack, org_unit_id: d.org, name: d.name, rules: d.rules, owner: d.owner, ...(d.id ? { id: d.id } : {}) });
export const submitStandingPolicy = (id: string): Promise<Done> => invoke('standingPolicy.submit', { id });
export const approveStandingPolicy = (id: string): Promise<Done> => invoke('standingPolicy.approve', { id });
export const retireStandingPolicy = (id: string, reason: string): Promise<Done> => invoke('standingPolicy.retire', { id, reason });
