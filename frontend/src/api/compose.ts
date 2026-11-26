/**
 * Describe your business (plan 9, P9-2.7, story X-02; backend/di/services/actions/config_agent.py): the configuration agent reads
 * a description, matches a pack, asks one question and drafts a change set of typed overlay operations. `config.read` reads (the
 * reading log, the matched pack, the question); `config.draft` stores the change set and holds its overlay draft as one proposal
 * for a person (proposal.accept; the overlay's own maker-checker approves it, no agent does). Both are on-demand actions, not
 * cached reads: the text is the person's.
 */
import { invoke, read } from './actions';
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

// ---------------------------------------------------------------- the composition (plan 9, P9-8.17; backend/di/services/actions/compose.py)

export type CompositionStep = 'describe' | 'mapping' | 'agents' | 'approve' | 'publish';
export type CompositionStatus = 'draft' | 'submitted' | 'sent_back' | 'approved' | 'published' | 'discarded';

export interface StepNote {
  reason: string;
  node_id?: string;
  by: string;
  at: string;
}

export interface StepState {
  state: 'todo' | 'done' | 'sent_back';
  note?: StepNote;
  [field: string]: unknown;
}

/** One approvable object: the change set, the mapping rows and the stage-agent settings, with maker-checker. */
export interface Composition {
  id: number;
  org_unit_id: string;
  pack_key: string;
  base_version: string;
  text: string;
  reading: Reading;
  change_set: ChangeSet;
  steps: Record<CompositionStep, StepState>;
  status: CompositionStatus;
  version: number;
  created_by: string;
  editors: string[];
  submitted_by: string | null;
  approved_by: string | null;
  published_by: string | null;
}

/** How far a system the composition needs is connected (P9-8.18, `compose.systems`). */
export type SystemStatus = 'connected' | 'needs_adapter' | 'test_connection' | 'awaiting_owner';

/** The bands of the suggested mappings of a system's sample; `asked_owner` counts the fields waiting for the system owner. */
export interface MappingCounts {
  fields: number;
  pre_ticked: number;
  check: number;
  none: number;
  asked_owner: number;
}

export interface ComposeSystem {
  name: string;
  system_type: string;
  source_id: string | null;
  /** ids of the registry entries of this system type the org may start from */
  registry: string[];
  status: SystemStatus;
  mapping: MappingCounts;
}

type Made = ActionResult<Composition & { log?: string }>;

/** The systems a composition needs, each joined with the org's sources and the adapter registry. */
export const useComposeSystems = (id: number): ComposeSystem[] => read<{ systems: ComposeSystem[] }>('compose.systems', { id }).systems;

/** The pack's sample descriptions (the Describe step's buttons). */
export const packPrompts = (pack: string): string[] => read<{ prompts: string[] }>('compose.prompts', { pack_key: pack }).prompts;

/** The composition with its steps and change set (a read, cached per id). */
export const useComposition = (id: number): Composition => read<Composition>('compose.get', { id });

/** The compositions of an org unit, or of every unit the person sees. */
export const compositions = (org?: string): Composition[] =>
  read<{ compositions: Composition[] }>('compose.list', org ? { org_unit_id: org } : {}).compositions;

/** Describe a business: the configuration agent drafts the change set (status draft). */
export const startComposition = (org: string, text: string, pack?: string): Promise<Made> =>
  invoke('compose.start', { org_unit_id: org, text, ...(pack ? { pack_key: pack } : {}) }) as Promise<Made>;

/** Answer the pack's one question (an option id or "skip"). */
export const answerQuestion = (id: number, answer: string): Promise<Made> => invoke('compose.answer', { id, answer }) as Promise<Made>;

/** Replace the typed operations; the server checks them against the pack. */
export const editChangeSet = (id: number, ops: OverlayOpRef[]): Promise<Made> => invoke('compose.editChangeSet', { id, ops }) as Promise<Made>;

/** Mark describe, mapping or agents done. */
export const markStep = (id: number, step: CompositionStep): Promise<Made> => invoke('compose.markStep', { id, step }) as Promise<Made>;

/** Submit for approval; refused with `blocking` (the list of what is left) when it is not ready. */
export const submitComposition = (id: number): Promise<ActionResult> => invoke('compose.submit', { id });

/** The checker sends it back with a reason (15 characters or more) pinned to a step, and to a node when given. */
export const sendBack = (id: number, step: CompositionStep, reason: string, nodeId?: string): Promise<ActionResult> =>
  invoke('compose.sendBack', { id, step, reason, ...(nodeId ? { node_id: nodeId } : {}) });

/** The checker approves (never the maker, submitter or an editor): the changes, mapping and stage settings apply as one. */
export const approveComposition = (id: number): Promise<ActionResult> => invoke('compose.approve', { id });

// ---------------------------------------------------------------- the test run (P9-8.19; compose.testRun)

export interface StopReasonCount {
  /** missing_field:<model.field>, held_record:<code>, guardrail:<id>, threshold:<stage>, no_route:<stage> */
  reason: string;
  count: number;
  /** the first item ids behind the count */
  examples: string[];
}

export interface StageStop {
  stage: string;
  reached: number;
  stopped: number;
  reasons: StopReasonCount[];
}

/** Past items put through the draft flow: where cases stopped. Nothing is written, published or approved. */
export interface TestRun {
  id: number;
  batch_id: number;
  /** items taken from the batch (at most the limit) */
  sample: number;
  /** the sample plus the rows the import held */
  total: number;
  decided: number;
  stages: StageStop[];
  /** "200 past items: 163 reached a decision; ...", worded by a model when one answered (the counts are the code's) */
  text: string;
  by_model: boolean;
  decisions: { item_id: string; route: string | null }[];
}

/** Run the draft over the org's past items (the newest batch of the pack unless `batchId` is given). On demand, never cached. */
export const testRunComposition = (id: number, opts: { limit?: number; batchId?: number } = {}): Promise<ActionResult<TestRun>> =>
  invoke('compose.testRun', {
    id,
    ...(opts.limit !== undefined ? { limit: opts.limit } : {}),
    ...(opts.batchId !== undefined ? { batch_id: opts.batchId } : {}),
  }) as Promise<ActionResult<TestRun>>;
