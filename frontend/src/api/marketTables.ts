/**
 * Per-market rate cards and decision tables (plan 9, P9-4.2, story SD-03; backend/di/services/actions/market_tables.py). A change is a
 * new version: a person drafts and submits it, a different person approves it (maker-checker); no agent approves or rejects.
 * Every write is a marketTable.* action; the list is a read action cached per pack and flow (a write refreshes the Modeler).
 */
import { invoke, read } from './actions';
import type { ActionResult } from './types';

type TableKind = 'rate_card' | 'decision_table';
export type TableStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'retired';

/** A JDM graph (GoRules): the body of a decision table. */
export interface Jdm {
  nodes: { id: string; type: string; name?: string; content?: unknown; [k: string]: unknown }[];
  edges: { id: string; sourceId: string; targetId: string; [k: string]: unknown }[];
}

export interface MarketTable {
  id: number;
  org_unit_id: string | null;
  pack: string;
  flow: string;
  market: string;
  name: string;
  /** "labour rates": what a priced line calls the table */
  title: string;
  /** "DE labour rates v1" */
  label: string;
  kind: TableKind;
  version: number;
  status: TableStatus;
  valid_from: string;
  valid_to: string | null;
  currency: string | null;
  /** a rate card: `{ values: { rate: number } }`; a decision table: a JDM graph */
  body: { values: Record<string, number> } & Partial<Jdm>;
  created_by: string;
  submitted_by: string | null;
  approved_by: string | null;
  reason: string | null;
}

export interface MarketTableList {
  pack: string;
  /** market -> currency */
  markets: Record<string, string>;
  /** the input fields each decision table may read */
  inputs: Record<string, string[]>;
  tables: MarketTable[];
  can: { edit: boolean; approve: boolean };
}

export interface TableTest {
  id: number;
  label: string;
  outputs: Record<string, unknown>;
  matched: string[];
  trace: string[];
}

type Done = ActionResult<{ id: number; version?: number; status: TableStatus; log?: string }>;

/** The versions of a pack's tables the signed-in person may see (read action, Suspense cache). */
export const useMarketTables = (pack: string, flow: string): MarketTableList => read<MarketTableList>('marketTable.list', { pack, flow });

export interface TableDraft {
  pack: string;
  flow: string;
  market: string;
  name: string;
  kind: TableKind;
  valid_from: string;
  valid_to?: string;
  currency?: string;
  org_unit_id?: string;
  body: object;
  /** your own draft to change; leave out for a new version */
  id?: number;
}

export const saveMarketTable = (d: TableDraft): Promise<Done> => invoke('marketTable.save', { ...d });
export const submitMarketTable = (id: number): Promise<Done> => invoke('marketTable.submit', { id });
export const approveMarketTable = (id: number): Promise<Done> => invoke('marketTable.approve', { id });
export const rejectMarketTable = (id: number, reason: string): Promise<Done> => invoke('marketTable.reject', { id, reason });
export const testMarketTable = (id: number, inputs: Record<string, unknown>): Promise<ActionResult<TableTest>> => invoke<TableTest>('marketTable.test', { id, inputs });
