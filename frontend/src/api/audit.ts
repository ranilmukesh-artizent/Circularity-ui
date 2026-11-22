/**
 * Audit & provenance (#/audit): the fetch and event log, evidence gaps, provenance records and comments.
 * GET /api/screens/audit (entries, gaps, comments), /audit/provenance and /audit/comments, and
 * the action comment.add (di/services/screens/audit.py has the mapping).
 */
import { invoke } from './actions';
import { ApiError, cached, withQuery } from './client';
import type { ActionResult } from './types';
import { view } from './view';

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

// ---------------------------------------------------------------- API answers (ISO timestamps become Dates once)
type Wire<T> = Omit<T, 'ts' | 'p'> & { ts: string; p?: WireProv };
type WireProv = Omit<Provenance, 'fetchedAt' | 'observedAt'> & { fetchedAt?: string; observedAt?: string };
interface Answer { entries: Wire<AuditEntry>[]; gaps: { c: CaseLite; e: Evidence; p: WireProv }[]; comments: Record<string, Comment[]> }
interface Parsed { entries: AuditEntry[]; gaps: { c: CaseLite; e: Evidence }[]; comments: Record<string, Comment[]> }

const prov = (p: WireProv): Provenance => ({
  ...p,
  fetchedAt: p.fetchedAt ? new Date(p.fetchedAt) : undefined,
  observedAt: p.observedAt ? new Date(p.observedAt) : undefined,
});
const parsed = new WeakMap<Answer, Parsed>();

function audit(): Parsed {
  const a = cached<Answer>(withQuery('/api/screens/audit', { tenant_filter: view().tenant }));
  let p = parsed.get(a);
  if (!p) {
    p = {
      entries: a.entries.map((x) => ({ ...x, ts: new Date(x.ts), p: x.p && prov(x.p) })),
      gaps: a.gaps.map(({ c, e }) => ({ c, e })),
      comments: a.comments,
    };
    parsed.set(a, p);
  }
  return p;
}

/** A read that may be refused (not found, out of scope): null instead of the error; a pending fetch still suspends. */
function orNull<T>(f: () => T): T | null {
  try {
    return f();
  } catch (err) {
    if (err instanceof ApiError) return null;
    throw err;
  }
}

// ---------------------------------------------------------------- the log
/** Every entry the account may see (evidence fetches of visible cases, and instructions and events), with agent preparers. */
export const auditEntries = (): AuditEntry[] => audit().entries;
/** Evidence with no recorded fetch, so no provenance. */
export const auditGaps = (): { c: CaseLite; e: Evidence }[] => audit().gaps;

interface ProvAnswer { c: CaseLite; ev: Evidence; p: WireProv }
const provAnswer = (caseId: string, key: string): ProvAnswer | null =>
  orNull(() => cached<ProvAnswer>(withQuery('/api/screens/audit/provenance', { case_id: caseId, key })));

export function provenanceOf(caseId: string, key: string): { c: CaseLite; ev: Evidence; p: Provenance } | null {
  const r = provAnswer(caseId, key);
  return r && { c: r.c, ev: r.ev, p: prov(r.p) };
}

// ---------------------------------------------------------------- formatting
/** 2026-10-07 09:12:44 UTC (the demo's isoT). */
export const isoT = (d: Date | string | number): string => new Date(d).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');

/** Pretty-printed JSON (for the raw event block). */
export const eventJson = (ev: AuditEvent): string =>
  JSON.stringify({
    event: ev.id, type: ev.type, at: new Date(ev.ts).toISOString(), caseId: ev.caseId, decisionId: ev.decisionId, approvalRef: ev.approval,
    instructionVersion: ev.ver, destination: ev.dest, acknowledgement: ev.ack, idempotencyKey: ev.key,
  }, null, 2);

/** Acknowledgement chip colour (the demo's ackKind). */
export const ackKind = (a: string): string => (/^acknowledged$/.test(a) ? 'ok' : /conflict|stale|failed/.test(a) ? 'bad' : /sent/.test(a) ? 'line' : 'warn');

// ---------------------------------------------------------------- comments
/** Comments under a record key, oldest first: audit entries come with the log; other keys from /audit/comments. */
export function comments(key: string): Comment[] {
  if (key.startsWith('au:')) return audit().comments[key] ?? [];
  return orNull(() => cached<Comment[]>(withQuery('/api/screens/audit/comments', { key }))) ?? [];
}
export const postComment = (key: string, text: string): Promise<ActionResult> => invoke('comment.add', { key, text });
