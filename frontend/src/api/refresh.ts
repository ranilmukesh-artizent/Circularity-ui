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

/** The like-life unit of one swapped tool (P9-5.3, CR-03): unit_id is null and why says why when none fits. */
export interface RefreshMatch {
  serial: string;
  need_id: string;
  cls: string;
  target: number;
  unit_id: string | null;
  rul: number | null;
  distance: number | null;
  source: 'stock' | 'return' | null;
  why: string | null;
}

/** The proposal's money (P9-5.4, CR-04), in the market's currency, computed by the server from the rate card and credit table it cites. */
export interface RefreshPricing {
  currency: string;
  rate_card_version: number;
  fees_version: number;
  credit_rules_version: number;
  term_months: number;
  current_fee_month: number;
  proposed_fee_month: number;
  saving_vs_new: number;
  renewal_likelihood: number;
  renewal_without: number;
  renewal_basis: string;
  credits: { serial: string; amount: number; rule_version: number }[];
  credit_total: number;
  credit_total_usd: number;
  lines: { label: string; amount: number; cite: string }[];
  routes: { id: string; name: string; net: number; standard: boolean }[];
  best: string;
  uplift: number;
}

/** Who approves the proposal: always a person (GR-C2), Sales when the credits are over the limit (GR-C1). The server words `text`. */
export interface RefreshApproval {
  kind: 'person';
  role: string;
  text: string;
  holds: { id: string; reason: string; owner: string }[];
}

/** What an approved refresh carried out (P9-5.5, CR-05): the three steps with the reference each system returned. Null before an approval. */
export interface RefreshExecution {
  approval: string;
  route: string;
  approver: string | null;
  valid_until: string;
  steps: { kind: string; system: string; state: 'done' | 'active' | 'todo'; ref: string | null; text: string }[];
  done: boolean;
  /** Set when a unit was taken meanwhile and the decision went back to the Fleet desk. */
  back: { to: string; reason: string } | null;
}

export interface RefreshView {
  case_id: string;
  contract: RefreshContract;
  window: { opens: string | null; basis: 'end' | 'notice' };
  lines: RefreshLine[];
  tools: RefreshTool[];
  tools_totals: { keep: number; swap: number; upgrade: number };
  tools_hold: 'confidence' | null;
  match: RefreshMatch[];
  pricing: RefreshPricing | null;
  approval: RefreshApproval | null;
  execution: RefreshExecution | null;
  outcome: unknown | null;
}

/** The panel's read for a contract refresh case (GET /api/screens/refresh/{id}). */
export const refreshView = (caseId: string): RefreshView => cached<RefreshView>('/api/screens/refresh/' + encodeURIComponent(caseId));
