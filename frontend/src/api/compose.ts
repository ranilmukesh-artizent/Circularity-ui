/**
 * Describe your business (plan 9, P9-2.7, story X-02; backend/di/services/actions/config_agent.py): the configuration agent reads
 * a description, matches a pack, asks one question and drafts a change set of typed overlay operations. `config.read` reads (the
 * reading log, the matched pack, the question); `config.draft` stores the change set and holds its overlay draft as one proposal
 * for a person (proposal.accept; the overlay's own maker-checker approves it, no agent does). Both are on-demand actions, not
 * cached reads: the text is the person's.
 */
import { invoke } from './actions';
import type { ActionResult } from './types';

export interface Control {
  kind: 'amount' | 'percent' | 'role' | 'market' | 'condition';
  text: string;
  value: string | number | string[];
}

export interface Reading {
  word_count: number;
  controls: Control[];
  systems: string[];
  unit: string | null;
  /** a model drafted it (the rules still checked it) */
  by_model: boolean;
}

export interface PackMatch {
  key: string;
  score: number;
  /** below the bar: this is only the nearest pack, none is invented */
  nearest_only: boolean;
}

export interface ChangeOption {
  id: string;
  label: string;
}

export interface ChangeQuestion {
  text: string;
  options: ChangeOption[];
}

export interface OverlayOpRef {
  id: string;
  op: 'tighten' | 'add_approver' | 'add_step' | 'shortcut' | 'set_param';
  [field: string]: unknown;
}

export interface ChangeSet {
  pack: string;
  base_version: string;
  ops: OverlayOpRef[];
  /** ids of operations the person did not state */
  assumed: string[];
  blocked: { text: string; guardrail: string }[];
  systems: { name: string; adapter: boolean }[];
  kpis: string[];
  question: ChangeQuestion | null;
  answer: string | null;
  by_model: boolean;
}

export interface DescriptionRead {
  reading: Reading;
  match: PackMatch;
  question: ChangeQuestion | null;
}

export interface Drafted {
  change_set_id: number;
  /** the held overlay draft (Home's proposals); null when it ran without being held */
  proposal_id: number | null;
  change_set: ChangeSet;
  log?: string;
}

/** The reading log, the matched pack and the one question for a description at an org unit. */
export const readDescription = (text: string, org: string): Promise<ActionResult<DescriptionRead>> =>
  invoke('config.read', { text, org_unit_id: org }) as Promise<ActionResult<DescriptionRead>>;

/** The change set for a description; `answer` is an option id of the question or "skip" (required when there is a question). */
export const draftChangeSet = (text: string, org: string, answer?: string): Promise<ActionResult<Drafted>> =>
  invoke('config.draft', { text, org_unit_id: org, ...(answer ? { answer } : {}) }) as Promise<ActionResult<Drafted>>;
