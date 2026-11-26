/**
 * The contract refresh case panel (plan 9, P9-5.1, stories CR-01 and CR-08; backend/di/services/screens/refresh.py): the
 * contract a refresh case was opened for, the window that opened it and its lines. `window.basis` says what the window
 * counts back from: the contract's end date or its notice date. The other fields are empty until the tasks that fill them.
 * A read only; writes go through the action pipeline.
 */
import { cached } from './client';

export interface RefreshContract {
  id: string;
  customer: string | null;
  market: string | null;
  start: string | null;
  end: string | null;
  notice: string | null;
  term_months: number | null;
  status: string | null;
}

export interface RefreshLine {
  serial: string;
  cls: string | null;
  model: string | null;
  fee: number | null;
  months: number | null;
}

/** One tool's choice for the next term (P9-5.2, CR-02): keep, like-life swap or upgrade, with its reason. */
export interface RefreshTool {
  serial: string;
  cls: string;
  action: 'keep' | 'swap' | 'upgrade';
  reason: string;
  rul_pct: number;
  confidence: string;
  flag: string | null;
  end_of_parts: string | null;
  successor: string | null;
}

export interface RefreshView {
  case_id: string;
  contract: RefreshContract;
  window: { opens: string | null; basis: 'end' | 'notice' };
  lines: RefreshLine[];
  tools: RefreshTool[];
  tools_totals: { keep: number; swap: number; upgrade: number };
  tools_hold: 'confidence' | null;
  match: unknown[];
  pricing: unknown | null;
  approval: unknown | null;
  execution: unknown | null;
  outcome: unknown | null;
}

/** The panel's read for a contract refresh case (GET /api/screens/refresh/{id}). */
export const refreshView = (caseId: string): RefreshView => cached<RefreshView>('/api/screens/refresh/' + encodeURIComponent(caseId));
