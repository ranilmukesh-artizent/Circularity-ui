/**
 * My work (plan 9, P9-1.7; registry entry I-20): the one list of what waits for the signed-in person, from
 * GET /api/screens/mywork (backend/di/services/screens/mywork.py). Exceptions and questions are work items with an owner
 * role and a due time; approvals and tasks are Home's list; proposals are the agents' held writes; conflicts are the
 * ones that hold a decision.
 *
 * The writes are actions: resolveItem (work.resolve) and assignItem (work.assign) by the owner or Admin, askForInfo
 * (case.needInfo) by anyone who may open the case. Agents never run resolve or assign (backend/di/services/actions/work.py).
 * A proposal row is accepted or rejected with acceptProposal and rejectProposal from ./agents, as Home does.
 */
import { invoke } from './actions';
import type { PackKpi } from './analytics';
import { cached } from './client';
import type { ActionResult } from './types';

export type WorkKind = 'exception' | 'approval' | 'needs_info' | 'proposal' | 'conflict' | 'task';

export interface WorkItem {
  /** where the row comes from: w:<id> a work item, a:<title> an approval or task, p:<id> a proposal, c:<id> a conflict */
  id: string;
  kind: WorkKind;
  case_id: string | null;
  title: string;
  cause: string | null;
  action: string | null;
  /** the account or role it waits for */
  owner: string;
  /** ISO time, or null */
  due: string | null;
  overdue: boolean;
  priority: number;
  /** a route without the leading #/ */
  go: string | null;
}

export interface MyWorkScreen {
  items: WorkItem[];
  counts: Record<WorkKind, number>;
  /** P9-1.13: the KPIs of the packs of the cases the account sees, from the packs' own data (empty for the industrial demo) */
  kpis: (PackKpi & { pack: string; pack_name: string })[];
}

/** My work (Suspense read cache). */
export const useMyWork = (): MyWorkScreen => cached<MyWorkScreen>('/api/screens/mywork');

/** Close an exception, question or step with an outcome; an answer to a question becomes a note on the case. */
export const resolveItem = (itemId: number, outcome: string, note?: string): Promise<ActionResult<{ id: number; case_id: string | null }>> =>
  invoke('work.resolve', { item_id: itemId, outcome, ...(note ? { note } : {}) });

/** Hand a work item to one account (its owner or Admin). */
export const assignItem = (itemId: number, account: string): Promise<ActionResult<{ id: number; account: string }>> =>
  invoke('work.assign', { item_id: itemId, account });

/** One fact behind the exception assistant's draft, with where it came from and when. */
export interface DraftSource {
  fact: string;
  source: string;
  at: string;
}

/** P9-2.10: the exception assistant's draft for an exception item. `owner_role` and `recommended_action` come from the pack;
 *  `by_model` is true when a language model worded `cause`. */
export interface ExceptionDraft {
  cause: string;
  recommended_action: string;
  owner_role: string;
  by_model: boolean;
  sources: DraftSource[];
}

/** The assistant's draft for an exception item (exception.explain, a read): it proposes, a person resolves or assigns. */
export const explainException = (exceptionId: number): Promise<ActionResult<ExceptionDraft>> =>
  invoke('exception.explain', { exception_id: exceptionId });

/** Ask a role a question about a case; it appears in that role's My work, due as the pack's SLA says. */
export const askForInfo = (caseId: string, question: string, toRole: string): Promise<ActionResult<{ id: number; case_id: string }>> =>
  invoke('case.needInfo', { case_id: caseId, question, to_role: toRole });
