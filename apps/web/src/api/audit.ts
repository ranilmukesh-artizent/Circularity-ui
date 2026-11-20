/** Audit & provenance (#/audit): the fetch and event log, evidence gaps, provenance records and comments. */
import { engine } from '../engine/engine';
import { invoke } from './actions';
import type { ActionResult } from './types';

const e = () => engine();

export interface Provenance {
  id: string; key: string; label: string; status: 'available' | 'partial' | 'unavailable'; state?: string;
  sourceName: string; vendor?: string; mode?: string; auth?: string;
  file?: string | null; fileNote?: string; table?: string | null; column?: string | null; record?: string | null;
  row?: number | null; rowsTotal?: number; value?: string; fetchedAt?: Date; observedAt?: Date; request?: string; checksum?: string;
  processing?: string[]; usedIn: string[]; notes?: string[]; partialWhy?: string; reason?: string;
}
export interface AuditEvent {
  id: string; type: string; ts: string | number | Date; dir: 'in' | 'out'; dest: string; ack: string; caseId?: string; decisionId?: string | null;
  approval?: string | null; ver?: string | null; key?: string; note?: string; by?: string;
}
export interface AuditEntry {
  id: string; kind: 'fetch' | 'event'; ts: Date; source: string; caseId: string; asset: string; item: string; key: string;
  request: string; result: string; used: string; status: 'available' | 'partial' | 'recorded'; prep?: string | null;
  p?: Provenance; ev?: AuditEvent;
}
export interface Evidence { k: string; label: string; source: string; state: string; note?: string }
export interface CaseLite { id: string; assetId: string; evidence: Evidence[] }
export interface Comment { by: string; at: Date | string; text: string; prep?: string | null }

/** Every entry the account may see (evidence fetches of visible cases, and instructions and events), with agent preparers. */
export const auditEntries = (): AuditEntry[] => e()<() => AuditEntry[]>('auditEntries')();
/** Evidence with no recorded fetch, so no provenance. */
export const auditGaps = (): { c: CaseLite; e: Evidence }[] => e()<() => { c: CaseLite; e: Evidence }[]>('auditGaps')();

export const caseById = (id: string): CaseLite | undefined => e()<Record<string, CaseLite>>('CASE_BY_ID')[id];
export function provenanceOf(caseId: string, key: string): { c: CaseLite; ev: Evidence; p: Provenance } | null {
  const c = caseById(caseId);
  const ev = c?.evidence.find((x) => x.k === key);
  if (!c || !ev) return null;
  return { c, ev, p: e()<(c: CaseLite, e: Evidence) => Provenance>('provFor')(c, ev) };
}

/** 2026-10-07 09:12:44 UTC (the demo's isoT). */
export const isoT = (d: Date | string | number): string => e()<(d: unknown) => string>('isoT')(d);

/** Pretty-printed JSON (for the raw event block). */
export const eventJson = (ev: AuditEvent): string =>
  JSON.stringify({
    event: ev.id, type: ev.type, at: new Date(ev.ts).toISOString(), caseId: ev.caseId, decisionId: ev.decisionId, approvalRef: ev.approval,
    instructionVersion: ev.ver, destination: ev.dest, acknowledgement: ev.ack, idempotencyKey: ev.key,
  }, null, 2);

/** Acknowledgement chip colour (the demo's ackKind). */
export const ackKind = (a: string): string => (/^acknowledged$/.test(a) ? 'ok' : /conflict|stale|failed/.test(a) ? 'bad' : /sent/.test(a) ? 'line' : 'warn');

export const comments = (key: string): Comment[] => e()<{ cm: Record<string, Comment[]> }>('S').cm[key] ?? [];
export const postComment = (key: string, text: string): Promise<ActionResult> => invoke('comment.add', { key, text });
