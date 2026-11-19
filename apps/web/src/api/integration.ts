/**
 * Connection Fabric (#/integration): sources, catalogue, source map, source tables, canonical models, event stream,
 * conflicts, manual import and monitor. Typed reads over the engine; changes go through invoke() where the demo has an
 * action, and through the small helpers at the bottom for the demo's near-real flows (pause, disconnect, re-authenticate,
 * connect from the catalogue) that the demo itself does not journal.
 */
import { bump, engine } from '../engine/engine';
import { invoke } from './actions';

/* eslint-disable @typescript-eslint/no-explicit-any */
const g = () => engine();
const fn = <T extends (...a: any[]) => any>(name: string) => ((...a: Parameters<T>) => g()<T>(name)(...a)) as T;

export type SrcStatus = 'live' | 'stale' | 'manual' | 'unavailable';
export interface SyncRun { id: string; ts: number; trigger: string; rows: number; dur: number; result: string; note: string }
export interface AuditEntry { ver: string; who: string; ts: number; change: string }
export interface Source {
  id: string; type: string; cat: string; name: string; short: string; vendor: string; ver: string; env: string; url: string;
  status: SrcStatus; mode: string; interval: number; auth: string; freshMin: number | null; fresh: string; compl: number; conf: number;
  rw: string; inputs: string; read: string[]; write: string[]; step: number[]; authority: string[]; owner: string; records: number;
  note?: string; cfgVer: string; lastSync: number | null; updatedAt: number; runs: SyncRun[]; audit: AuditEntry[];
  method: string; cfg: Record<string, string | number>; credAt: number; credDays: number;
  syncing?: boolean; syncPct?: number; paused?: boolean; disconnected?: boolean; discBy?: string; frConnectedAt?: number;
}
export interface CmField { k: string; l: string; t: 'select' | 'text' | 'number'; def: string | number; o: string | string[]; req?: number }
export interface ConnMethod { label: string; badge: string; sub: string; tip: string; sched: number; url: number; auth: string; fields: CmField[] }
export interface SrcType { label: string; short: string; cat: string; target: string; vendors: string[] }
export interface CatalogItem { id: string; vendor: string; type: string; status: string; desc: string; auth: string[]; why?: string; connected?: boolean }
export interface Integration {
  id: string; src?: Source; c?: CatalogItem; vendor: string; name: string; cat: string; type: string;
  status: 'connected' | 'attention' | 'unavailable' | 'available' | 'paused' | 'disconnected' | 'manual'; last: number | null; owner: string;
}
export interface Rec { s?: Source; c?: CatalogItem; v: string; t: string; line: string; why: string; btn: string; act: string; arg: string; st: string }
export interface Canon { n: string; v: string; fields: string[]; purpose: string; sources: string[] }
export interface Conflict {
  id: string; kind: string; asset: string; a: { src: string; val: string }; b: { src: string; val: string }; authority: string; impact: string;
  status: 'open' | 'resolved'; since: string; escalated?: { by: string; at: string };
}
export interface StreamEvent {
  id: string; dir: 'in' | 'out'; type: string; caseId: string | null; decisionId: string | null; approval: string | null; ver: number | null;
  dest: string; ack: string; key: string; note?: string; ts: Date | string | number; retries?: number;
}
export interface Table { n: string; cl: string; desc: string; cols: [string, string][]; rows: string; x: number; y: number }
export interface TableModel { cl: [string, string][]; t: Table[]; fk: [string, string, string][]; ww?: number; wh?: number }
export interface HourBucket { ok: number; warn: number; bad: number }
export interface Totals { ok: number; warn: number; bad: number; run: number; pct: number }
export interface Workflow { id: string; name: string; src?: string; cat: string; status: string; runsN?: number; okN?: number; last?: { state: string; ts: number; dur: number; note?: string } | null; frNew?: boolean }
export interface Comment { by: string; at: string | Date; text: string }
export interface SmLog { ts: number; id: string; kind: string; text: string }
export interface MapException { src: string; obj: string; issue: string; sev: 'High' | 'Medium' | 'Low'; st: string }
export type MapRow = [string, string, string, string, string];

/* ---- reference data ---- */
export const sources = (): Source[] => g()<Source[]>('SOURCES');
export const source = (id: string | null | undefined): Source | undefined => (id ? sources().find((s) => s.id === id) : undefined);
export const mappings = (id: string): MapRow[] => g()<Record<string, MapRow[]>>('MAPPINGS')[id] ?? [];
export const allMappings = (): Record<string, MapRow[]> => g()<Record<string, MapRow[]>>('MAPPINGS');
export const connMethods = (): Record<string, ConnMethod> => g()('CONN_METHODS');
export const srcTypes = (): Record<string, SrcType> => g()('SRC_TYPES');
export const srcCats = (): Record<string, string> => g()('SRC_CATS');
export const srcCatNote = (): Record<string, string> => g()('SRC_CAT_NOTE');
export const authOpts = (): string[] => g()('AUTH_OPTS');
export const canon = (): Canon[] => g()('CANON');
export const canonExample = (n: string): unknown => g()<Record<string, unknown>>('CANON_EX')[n];
export const canonPrefix = (): Record<string, string> => g()('CANON_PFX');
export const conflicts = (): Conflict[] => g()('CONFLICTS');
export const events = (): StreamEvent[] => g()('EVENTS');
export const catalog = (): CatalogItem[] => g()('CATALOG');
export const frCats = (): string[] => g()('FR_CATS');
export const frDecisions = (): [string, string, string[]][] => g()('FR_DEC');
export const intSub = (tab: string): string => g()<Record<string, string>>('FR_INT_SUB')[tab] ?? '';
export const intKids = (): [string, string, string, string?][] => g()('FR_INT_KIDS');
export const sampleCsv = (): string => g()('SAMPLE_CSV');
export const facilities = (): string[] => g()('FACILITIES');
export const tenantList = (): string[] => g()('TENANTS');
export const tableModelIds = (): string[] => Object.keys(g()<Record<string, unknown>>('TBL_MODELS'));
export const tableSuggestions = (src: string): { n: string; cl: string; desc: string; cols: string[] }[] => g()<Record<string, any[]>>('TBL_AVAIL')[src] ?? [];
export const frSample = (type: string): [string, string, string, string, number][] => {
  const S = g()<Record<string, [string, string, string, string, number][]>>('FR_SAMPLE');
  return (S[type] || S.db).map((r) => r.slice() as [string, string, string, string, number]);
};
export const frAuthOptions = (): [string, string, string][] => g()('FR_AUTH');
export const caseExists = (id: string): boolean => !!g()<Record<string, unknown>>('CASE_BY_ID')[id];
export const rbPath = (p: string): boolean => !!g()<(p: string) => unknown>('rbPath')(p);
export const nowLabel = (): string => g()<() => string>('who')();

/* ---- derived (the demo's own helpers) ---- */
export const integrations = fn<() => Integration[]>('frIntegrations');
export const recommendations = fn<() => Rec[]>('frRecs');
export const connected = fn<() => Source[]>('frConnected');
export const available = fn<() => CatalogItem[]>('frAvail');
export const needsAttention = fn<(s: Source) => boolean>('frNeedsAttn');
export const srcFailing = fn<(s: Source) => boolean>('frSrcFailing');
export const credDays = fn<(s: Source) => number>('frCredDays');
export const series = fn<(s: Source, n: number) => number[]>('frSeries');
export const successRate = fn<(s: Source) => number>('frSuccess');
export const failedRecords = fn<(s: Source, n: number) => number>('frFailedRecs');
export const srcAgeText = fn<(s: Source) => string>('srcAgeText');
export const srcFresh = fn<(s: Source) => number>('srcFresh');
export const srcAge = fn<(m: number) => string>('srcAge');
export const typeOf = fn<(t: string) => SrcType>('frTypeOf');
export const catOf = fn<(s: Source) => string>('frCatOf');
export const tableCount = fn<(id: string) => number>('frTblN');
export const fieldCount = fn<(id: string) => number>('frFldN');
export const srcModels = fn<(s: Source) => Record<string, MapRow[]>>('frSrcModels');
export const tableModel = fn<(id: string) => TableModel | null>('tgModel');
export const tableHeight = fn<(t: Table) => number>('tgH');
export const syncHistory = fn<(s: Source) => { ts: number; ok: boolean; rows: number; dur: string }[]>('frSyncHist');
export const slaMinutes = fn<(s: Source) => number>('frSla');
export const latency = fn<(s: Source) => number | null>('frLat');
export const wfUsing = fn<(id: string) => string[]>('wfUsing');
export const exceptions = fn<() => MapException[]>('smExceptions');
export const methodMode = fn<(m: string, iv: number) => string>('methodMode');
export const cfgDefaults = fn<(m: string) => Record<string, string | number>>('cfgDefaults');
export const buildUrl = fn<(d: { method: string; cfg: Record<string, unknown>; url: string }) => string>('buildUrl');
export const hashId = fn<(s: string) => string>('hashId');
export const vHue = fn<(v: string) => number>('vHue');
export const ackKind = fn<(a: string) => string>('ackKind');
export const pct = fn<(v: number, d: number) => string>('pct');
export const isoTime = fn<(d: unknown) => string>('isoT');
export const srcChannels = fn<(s: Source) => string[]>('srcCh');
export const commentsOf = (key: string): Comment[] => g()<(k: string) => Comment[]>('cmList')(key);
export const smLog = (): SmLog[] => g()<{ smLog: SmLog[] }>('S').smLog;
export const openDecisionCount = (): number =>
  g()<() => { stage: string }[]>('visCases')().filter((c) => c.stage === 'awaiting_approval' || c.stage === 'reeval').length;

export function totals(): Totals {
  return g()<() => Totals>('hhTotals')();
}
export function hourly(): HourBucket[] {
  g()<() => void>('hhInit')();
  return g()<{ hh: HourBucket[] }>('S').hh;
}
export function workflows(): Workflow[] {
  g()<() => void>('wfInit')();
  return g()<{ wf: { list: Workflow[] } }>('S').wf.list;
}
export const wfStat = (w: Workflow): string => g()<(w: Workflow) => string>('wfStat')(w);

/** Static, trusted markup fragments from the demo (vendor logos, journey step chips, highlighted JSON). */
export const vlogoHtml = (vendor: string): string => g()<(s: { vendor: string }) => string>('vlogo')({ vendor });
export const stepHtml = (n: number): string => g()<(n: number) => string>('stp')(n);
export const jsonHtml = (o: unknown): string => g()<(o: unknown) => string>('jsonHtml')(o);

/* ---- changes through the action registry ---- */
export const syncSource = (id: string) => invoke('source.sync', { source_id: id });
export const reconnectSource = (id: string) => invoke('source.reconnect', { source_id: id });
export const rotateCredentials = (id: string, days: number) => invoke<{ source_id: string; ver: string; stale: boolean }>('credentials.rotate', { source_id: id, days });
export const deleteSource = (id: string) => invoke<{ source_id: string; name: string; vendor: string }>('source.delete', { source_id: id });
export interface Draft {
  type: string; name: string; vendor: string; ver: string; env: string; url: string; method: string;
  cfg: Record<string, string | number>; interval: number | ''; auth: string; owner: string;
}
export const saveSource = (mode: 'new' | 'edit', id: string, d: Draft, maps: string[][], ops: { read: string[]; write: string[] }) =>
  invoke<{ mode: 'new' | 'edit'; source_id: string; name: string; vendor?: string; ver?: string; csv?: boolean; wasOff?: boolean }>('source.update', {
    mode, id, d, maps, ops, note: '',
  });
export const resolveConflict = (id: string) => invoke<{ id: string; authority: string; kind: string }>('conflict.resolve', { id });
export const escalateConflict = (id: string) => invoke('conflict.escalate', { id });
export const commitImport = (ok: number, err: number, rows: unknown) =>
  invoke('import.commit', { ok, err, hash: hashId(JSON.stringify(rows)) });
export const updateTables = (input: Record<string, unknown>) =>
  invoke<{ op: string; name?: string; fks?: number; from?: string; to?: string }>('tables.update', input);
export const addComment = (key: string, text: string) => invoke('comment.add', { key, text });

/** Undo journaled actions: the journal is replayed without them on the next load (the demo's afUndo). */
export function undoActions(seqs: number[]) {
  const AF = g()<{ undone: Set<number> }>('AF');
  seqs.forEach((s) => AF.undone.add(s));
  g()<() => void>('afSave')();
  window.location.reload();
}

/** Start every live source syncing, staggered like the demo's Sync all. Returns how many started. */
export function syncAllLive(): number {
  const l = sources().filter((s) => s.status === 'live' && !s.syncing);
  l.forEach((s, i) => window.setTimeout(() => invoke('source.sync', { source_id: s.id }), i * 120));
  return l.length;
}

/* ---- source tables: layout only (positions), not journaled in the demo either ---- */
export function moveTable(src: string, name: string, x: number, y: number) {
  const t = tableModel(src)?.t.find((t) => t.n === name);
  if (t) { t.x = x; t.y = y; bump(); }
}
export function alignTables(src: string) {
  const m = tableModel(src);
  if (!m) return;
  m.t.forEach((t) => { (t as { x: number | null }).x = null; });
  g()<(m: TableModel) => void>('tgLayout')(m);
  bump();
}

/* ---- near-real flows (5.10); the demo changes these directly, without an action ---- */
const bumpVer = (s: Source, change: string) => {
  const [a, b] = s.cfgVer.split('.');
  s.cfgVer = a + '.' + (+b + 1);
  s.audit.unshift({ ver: s.cfgVer, who: nowLabel(), ts: Date.now(), change });
};
const srcEvent = (s: Partial<Source>, type: string, ack: string, note: string) => g()<(...a: unknown[]) => void>('srcEvent')(s, type, ack, note);
const rbLog = (k: string, t: string) => g()<(k: string, t: string) => void>('rbLog')(k, t);
const smLogAdd = (s: Source, t: string, kind?: string) => g()<(...a: unknown[]) => void>('smLogAdd')(s, t, kind);

/** Pause or resume scheduled syncs. Returns the new state and the number of workflows that read the source. */
export function togglePause(id: string): { paused: boolean; workflows: number } | null {
  const s = source(id);
  if (!s) return null;
  s.paused = !s.paused;
  const who = nowLabel();
  srcEvent(s, s.paused ? 'source.paused' : 'source.resumed', 'acknowledged', s.paused ? 'Scheduled syncs stopped by ' + who : 'Scheduled syncs resumed by ' + who);
  rbLog(s.paused ? 'source.paused' : 'source.resumed', s.vendor + ' · by ' + who);
  bump();
  return { paused: !!s.paused, workflows: wfUsing(id).length };
}

export function disconnectSource(id: string) {
  const s = source(id);
  if (!s) return;
  const who = nowLabel();
  s.disconnected = true; s.paused = false; s.status = 'unavailable'; s.discBy = who; s.lastSync = null; s.fresh = '—'; s.freshMin = null;
  bumpVer(s, 'Disconnected; settings kept for reconnect');
  srcEvent(s, 'source.disconnected', 'acknowledged', 'Disconnected by ' + who);
  rbLog('source.disconnected', s.vendor + ' · by ' + who);
  smLogAdd(s, 'Disconnected by ' + who, 'warn');
  bump();
}

/** Re-authentication finished: renew the credential; a stale source is reconnected through source.reconnect. */
export function reauthenticated(id: string): 'reconnect' | 'renewed' | null {
  const s = source(id);
  if (!s) return null;
  s.credAt = Date.now(); s.credDays = 180;
  rbLog('source.reauthenticated', s.vendor + ' · by ' + nowLabel());
  if (s.status === 'stale') return 'reconnect';
  bumpVer(s, 'Re-authenticated; credential renewed');
  bump();
  return 'renewed';
}

export function recordTest(s: Partial<Source>, ok: boolean, failedAt: string) {
  srcEvent(s, 'source.tested', ok ? 'acknowledged' : 'error', ok ? 'Connection test passed' : 'Connection test failed at ' + failedAt);
  bump();
}

/** The connect flow's last step: the new source, its accepted mappings and its draft ingest workflow (the demo's frCxFinish). */
export function finishConnect(catId: string, authLabel: string, scopes: string[], n: number, accepted: MapRow[]): string | null {
  const G = g();
  const c = catalog().find((y) => y.id === catId);
  if (!c) return null;
  const t = c.type, T0 = srcTypes(), X = G<Record<string, SrcType>>('FR_XTYPES');
  if (!T0[t]) T0[t] = X[t];
  const m = t === 'db' ? 'jdbc' : t === 'store' ? 'file' : t === 'dw' ? 'delta' : 'api', id = c.id, now = Date.now(), who = nowLabel();
  const ev = scopes.includes('events');
  const T = T0[t];
  const s: Source = {
    id, type: t, vendor: c.vendor, ver: 'Connected ' + G<(d: Date) => string>('fmtDY')(G<() => Date>('asOfNow')()),
    url: m === 'file' ? 'sftp://' + c.id + '.northfield.example/outbound' : 'https://' + c.id + '.northfield.example/api',
    status: m === 'file' ? 'manual' : 'live', mode: m === 'file' ? 'Controlled CSV import' : ev ? 'API + events' : 'Polling · 30 min',
    interval: m === 'file' || ev ? 0 : 30, auth: authLabel, freshMin: 1, compl: 92, conf: 88, rw: scopes.includes('write') ? 'Read / write' : 'Read',
    inputs: c.desc, read: ['GET /records'], write: scopes.includes('write') ? ['POST /records'] : [], step: [1], authority: [], owner: 'Integration Engineering',
    records: n, frConnectedAt: now, cat: T.cat, name: T.label, short: T.short, env: 'Production', cfgVer: '1.0', lastSync: now, updatedAt: now, fresh: '1 min',
    runs: [{ id: 'SYNC-' + hashId(id + now).slice(0, 5).toUpperCase(), ts: now, trigger: 'Manual', rows: n, dur: 4.2, result: 'success', note: 'First sync' }],
    method: m, cfg: cfgDefaults(m), credAt: now, credDays: 180, audit: [{ ver: '1.0', who, ts: now, change: 'Connected from the catalogue' }],
  };
  Object.assign(s, { updatedBy: who, c0: 92, k0: 88 });
  sources().push(s);
  allMappings()[id] = accepted.map((r) => [r[0], r[1], r[2], r[3], 'Accepted from the agent’s suggestion']);
  c.connected = true;
  G<() => void>('rebuildLookups')();
  G<(s: Source) => void>('wfAddForSource')(s);
  const list = workflows(), w = list[list.length - 1];
  w.frNew = true;
  srcEvent(s, 'source.connected', 'acknowledged', 'Connected from the catalogue by ' + who);
  rbLog('source.connected', s.vendor + ' · ' + s.auth + ' · by ' + who);
  smLogAdd(s, 'Connected · first sync ' + G<(n: number) => string>('fmtN')(n) + ' records');
  bump();
  return w.id;
}
