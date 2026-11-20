/**
 * Connection Fabric (#/integration): sources, catalogue, source map, source tables, canonical models, event stream,
 * conflicts, manual import and monitor. Changes go through invoke(); the near-real flows the server has no action for
 * yet (pause, disconnect, re-authenticate, connect from the catalogue) are refused by the pages with notOnServer().
 *
 * GET /api/screens/integration/{sources, sources/{id}, overview, map, tables, models, events, conflicts, monitor}, the
 * Workflow Studio list (/api/screens/workflows) and the reference lists; the mapping, export by export, is in
 * di/screens/integration.py. Each endpoint needs its Connection Fabric section, so a read the account may not make
 * answers empty instead of asking. Sources, freshness, runs, records, conflicts and latency are the connectors' real
 * data. A sync is the real source.sync action, followed on the live stream.
 */
import { invoke } from './actions';
import { ApiError, cached, http, invalidate, onStream, peek, ref, session, withQuery } from './client';
import { visibleCases } from './product';
import { canPage, canRoute } from './session';
import { bump } from './store';

/* eslint-disable @typescript-eslint/no-explicit-any */

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
  /** The connector's own state (live, failing, auth_expired, unavailable); `status` shows failing and auth_expired as stale. */
  connectorStatus?: string;
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

/* ---------------------------------------------------------------- the API answers */
const BASE = '/api/screens/integration';
/** May the account read this section of the Connection Fabric? Reads it may not make return empty answers. */
const may = (...secs: string[]) => secs.some((s) => canPage('integration', s));
const SRC_SECS = ['overview', 'map', 'tables', 'models', 'monitor'];

interface Health {
  needs_attention: boolean; failing: boolean; cred_days: number | null; success: number | null; failed7: number; latency: number | null;
  sla: number; in_sla: boolean; tables: number; fields: number; mapped: number; workflows: string[]; channels: string[]; category: string;
}
type ApiSource = Source & { health?: Health };
interface Detail {
  source: ApiSource; sync_history: { ts: number; ok: boolean; rows: number; dur: string }[]; series: number[]; failed: number;
  mappings: MapRow[]; models: Record<string, MapRow[]>; table_model: TableModel | null; comments: Comment[];
}
interface OverviewAnswer {
  integrations: (Omit<Integration, 'src' | 'c'> & { src: string | null; catalog: string | null })[];
  recommendations: (Omit<Rec, 's' | 'c'> & { source: string | null; catalog: string | null })[];
  catalog: CatalogItem[]; available: string[];
}
interface MapAnswer {
  kpis: { workflows_published: number }; exceptions: MapException[]; activity: SmLog[]; open_conflicts: number; hourly: HourBucket[]; totals: Totals;
  mappings: Record<string, MapRow[]>; source_models: Record<string, Record<string, MapRow[]>>; table_models: Record<string, TableModel>;
}
interface MonitorAnswer { hourly: HourBucket[]; totals: Totals; workflows: (Workflow & { stat: string })[] }
interface ConflictAnswer { conflicts: Conflict[]; total: number; counts: { open: number; closed: number; systems: number } }

/** A read that may be refused (not found, out of scope): undefined instead of the error; a pending fetch still suspends. */
function orNone<T>(f: () => T): T | undefined {
  try {
    return f();
  } catch (err) {
    if (err instanceof ApiError) return undefined;
    throw err;
  }
}

/** Syncs started here and not yet reported finished on the stream (source id → started at). */
const syncsPending = new Map<string, number>();

function apiSources(): ApiSource[] {
  if (!may(...SRC_SECS)) return [];
  const list = cached<{ sources: ApiSource[] }>(BASE + '/sources').sources;
  for (const s of list) {
    s.syncing = syncsPending.has(s.id) || s.runs[0]?.result === 'running';
    for (const r of s.runs) r.dur ??= 0;
  }
  return list;
}
const health = (s: Source): Health | undefined => (s as ApiSource).health ?? apiSources().find((x) => x.id === s.id)?.health;

/** One source in detail; `days` sets the window of the daily series and the failed count (1 to 180). */
const detail = (id: string, days = 30): Detail | undefined =>
  may(...SRC_SECS) ? orNone(() => cached<Detail>(withQuery(BASE + '/sources/' + encodeURIComponent(id), { days: days === 30 ? null : Math.min(180, Math.max(1, days)) }))) : undefined;
const overview = (): OverviewAnswer | undefined => (may('overview') ? cached<OverviewAnswer>(BASE + '/overview') : undefined);
const mapAnswer = (): MapAnswer | undefined => (may('map') ? cached<MapAnswer>(withQuery(BASE + '/map', { limit: 2000 })) : undefined);
const monitorAnswer = (): MonitorAnswer | undefined => (may('monitor') ? cached<MonitorAnswer>(BASE + '/monitor') : undefined);
const tablesAnswer = (): { models: Record<string, TableModel> } | undefined => (may('tables') ? cached<{ models: Record<string, TableModel> }>(BASE + '/tables') : undefined);
const modelsAnswer = (): { mappings: Record<string, MapRow[]>; source_models: Record<string, Record<string, MapRow[]>> } | undefined =>
  may('models') ? cached(BASE + '/models') : undefined;

/* ---- reference data ---- */
export const sources = (): Source[] => apiSources();
export const source = (id: string | null | undefined): Source | undefined => (id ? sources().find((s) => s.id === id) : undefined);
export function allMappings(): Record<string, MapRow[]> {
  return modelsAnswer()?.mappings ?? mapAnswer()?.mappings ?? {};
}
export function mappings(id: string): MapRow[] {
  return (may('models', 'map') ? allMappings()[id] : detail(id)?.mappings) ?? [];
}
export const connMethods = (): Record<string, ConnMethod> => ref('CONN_METHODS');
export function srcTypes(): Record<string, SrcType> {
  // a connected source of a type outside SRC_TYPES (from the catalogue's extra types) is listed too, as the demo adds it on connect
  const T = ref<Record<string, SrcType>>('SRC_TYPES'), extra = sources().filter((s) => !T[s.type]);
  return extra.length ? { ...T, ...Object.fromEntries(extra.map((s) => [s.type, typeOf(s.type)])) } : T;
}
export const srcCats = (): Record<string, string> => ref('SRC_CATS');
export const srcCatNote = (): Record<string, string> => ref('SRC_CAT_NOTE');
export const authOpts = (): string[] => ref('AUTH_OPTS');
export const canon = (): Canon[] => ref('CANON');
export const canonExample = (n: string): unknown => ref<Record<string, unknown>>('CANON_EX')[n];
export const canonPrefix = (): Record<string, string> => ref('CANON_PFX');
export const events = (): StreamEvent[] => (may('events') ? cached<{ events: StreamEvent[] }>(BASE + '/events').events : []);
export function catalog(): CatalogItem[] {
  const o = overview();
  if (o) return o.catalog;
  const ids = new Set(sources().map((s) => s.id));
  return ref<CatalogItem[]>('CATALOG').map((c) => ({ ...c, connected: ids.has(c.id) }));
}
export const frCats = (): string[] => ref('FR_CATS');
export const frDecisions = (): [string, string, string[]][] => ref('FR_DEC');
export const intSub = (tab: string): string => ref<Record<string, string>>('FR_INT_SUB')[tab] ?? '';
export const intKids = (): [string, string, string, string?][] => ref('FR_INT_KIDS');
export const sampleCsv = (): string => ref('SAMPLE_CSV');
export const facilities = (): string[] => ref('FACILITIES');
export const tenantList = (): string[] => ref('TENANTS');
export function tableModelIds(): string[] {
  return Object.keys(tablesAnswer()?.models ?? mapAnswer()?.table_models ?? {});
}
export const tableSuggestions = (src: string): { n: string; cl: string; desc: string; cols: string[] }[] =>
  ref<Record<string, any[]>>('TBL_AVAIL')[src] ?? [];
export const frSample = (type: string): [string, string, string, string, number][] => {
  const S = ref<Record<string, [string, string, string, string, number][]>>('FR_SAMPLE');
  return (S[type] || S.db).map((r) => r.slice() as [string, string, string, string, number]);
};
export const frAuthOptions = (): [string, string, string][] => ref('FR_AUTH');
export function caseExists(id: string): boolean {
  return !!session() && id in cached<Record<string, unknown>>('/api/screens/nav/scope');
}
export function rbPath(p: string): boolean {
  const h = String(p).replace(/^#?\/?/, '').split('/');
  return canRoute({ page: h[0], a: h[1] || null, b: h[2] || null }) === true;
}
export const nowLabel = (): string => session()?.account.label ?? '—';

/* ---- derived (the `health` each source comes with) ---- */
export function integrations(): Integration[] {
  const o = overview();
  if (!o) return [];
  const cat = new Map(o.catalog.map((c) => [c.id, c]));
  return o.integrations.map(({ src, catalog: c, ...x }) => ({ ...x, src: source(src), c: c ? cat.get(c) : undefined }));
}
export function recommendations(): Rec[] {
  const o = overview();
  if (!o) return [];
  return o.recommendations.map(({ source: s, catalog: c, ...x }) => ({ ...x, s: source(s), c: o.catalog.find((y) => y.id === c) }));
}
export const connected = (): Source[] => sources().filter((s) => s.status !== 'unavailable');
export function available(): CatalogItem[] {
  const o = overview();
  return o ? o.available.map((id) => o.catalog.find((c) => c.id === id)!).filter(Boolean) : [];
}
export const needsAttention = (s: Source): boolean => !!health(s)?.needs_attention;
export const srcFailing = (s: Source): boolean => !!health(s)?.failing;
export const credDays = (s: Source): number => health(s)?.cred_days ?? 0;
export function series(s: Source, n: number): number[] {
  const a = detail(s.id, n)?.series ?? [];
  return a.length >= n ? a.slice(-n) : Array<number>(n - a.length).fill(0).concat(a);
}
export const successRate = (s: Source): number => health(s)?.success ?? 0;
export function failedRecords(s: Source, n: number): number {
  return n === 7 ? health(s)?.failed7 ?? 0 : detail(s.id, n)?.failed ?? 0;
}
export const typeOf = (t: string): SrcType =>
  ref<Record<string, SrcType>>('SRC_TYPES')[t] || ref<Record<string, SrcType>>('FR_XTYPES')[t] || { label: t, short: t, cat: 'internal', target: 'Asset & component', vendors: [] };
export const catOf = (s: Source): string => health(s)?.category ?? 'Custom';
export const tableCount = (id: string): number => health(source(id) ?? ({ id } as Source))?.tables ?? 0;
export const fieldCount = (id: string): number => health(source(id) ?? ({ id } as Source))?.fields ?? 0;
export function srcModels(s: Source): Record<string, MapRow[]> {
  return (modelsAnswer() ?? mapAnswer())?.source_models[s.id] ?? detail(s.id)?.models ?? {};
}
export function tableModel(id: string): TableModel | null {
  return (tablesAnswer()?.models ?? mapAnswer()?.table_models)?.[id] ?? null;
}
export function syncHistory(s: Source): { ts: number; ok: boolean; rows: number; dur: string }[] {
  return detail(s.id)?.sync_history ?? [];
}
export const slaMinutes = (s: Source): number => health(s)?.sla ?? 60;
export const latency = (s: Source): number | null => health(s)?.latency ?? null;
export const wfUsing = (id: string): string[] => health(source(id) ?? ({ id } as Source))?.workflows ?? [];
export const exceptions = (): MapException[] => mapAnswer()?.exceptions ?? [];
export const srcChannels = (s: Source): string[] => health(s)?.channels ?? [];
export function commentsOf(key: string): Comment[] {
  return key.startsWith('src:') ? detail(key.slice(4))?.comments ?? [] : [];
}
export const smLog = (): SmLog[] => mapAnswer()?.activity ?? [];
/** Open decisions (awaiting approval or re-evaluation) the account may see: the Product area's cases. */
export const openDecisionCount = (): number =>
  visibleCases().filter((c) => c.stage === 'awaiting_approval' || c.stage === 'reeval').length;

export function totals(): Totals {
  return (mapAnswer() ?? monitorAnswer())?.totals ?? { ok: 0, warn: 0, bad: 0, run: 0, pct: 100 };
}
export function hourly(): HourBucket[] {
  return (mapAnswer() ?? monitorAnswer())?.hourly ?? [];
}
/** The workflows: Workflow Studio's list, or, for accounts without the studio, the Monitor's workflows that ran. */
export function workflows(): Workflow[] {
  if (may('studio')) return cached<{ workflows: Workflow[] }>('/api/screens/workflows').workflows;
  return monitorAnswer()?.workflows ?? [];
}
export const wfStat = (w: Workflow): string => (w as Workflow & { stat?: string }).stat ?? w.status;
/** Published workflows (the Source Map's tile). */
export function publishedWorkflowCount(): number {
  if (!may('studio')) return mapAnswer()?.kpis.workflows_published ?? 0;
  return workflows().filter((w) => w.status === 'published').length;
}

/* ---- conflicts: the full queue is long with real data (hundreds), so it is read a page at a time ---- */
export interface ConflictPage { list: Conflict[]; total: number; open: number; closed: number; systems: number }
let lastConflicts: string | null = null;
/** The first `limit` conflicts (open, escalated and resolved, newest first), with the queue's counts. */
export function conflictPage(limit = 60): ConflictPage {
  if (!may('conflicts')) return { list: [], total: 0, open: 0, closed: 0, systems: 0 };
  const path = withQuery(BASE + '/conflicts', { status: 'all', limit });
  let a: ConflictAnswer;
  try {
    a = cached<ConflictAnswer>(path);
    lastConflicts = path;
  } catch (err) {
    // showing more: keep the shorter page on screen until the longer one arrives (it re-renders then)
    const prev = err instanceof Promise && lastConflicts ? peek<ConflictAnswer>(lastConflicts) : undefined;
    if (!prev) throw err;
    a = prev;
  }
  return { list: a.conflicts, total: a.total, ...a.counts };
}
/** Open conflicts in the queue (the Conflict Queue tab and the flow diagram). */
export function openConflictCount(): number {
  if (may('conflicts')) return conflictPage().open;
  return mapAnswer()?.open_conflicts ?? 0;
}

/* ---- formatting and small pure helpers (the demo's, ported) ---- */
export function hashId(s: string): string {
  let h = 2166136261;
  for (const ch of s) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).toUpperCase().padStart(8, '0');
}
export const ackKind = (a: string): string => (/^acknowledged$/.test(a) ? 'ok' : /conflict|stale|failed/.test(a) ? 'bad' : /sent/.test(a) ? 'line' : 'warn');
export const pct = (v: number, d = 0): string => (v * 100).toFixed(d) + '%';
export const isoTime = (d: unknown): string => new Date(d as string).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
export const srcAge = (m: number): string => (m < 1 ? 'just now' : m < 60 ? Math.round(m) + ' min' : m < 2880 ? Math.round(m / 60) + ' h' : Math.round(m / 1440) + ' days');
export function srcAgeText(s: Source): string {
  if (s.lastSync == null) return s.status === 'unavailable' ? 'Not connected' : 'Never synced';
  const sec = Math.max(0, Math.floor((Date.now() - s.lastSync) / 1000)), p = s.status === 'manual' ? 'Last import ' : 'Updated ';
  return p + (sec < 60 ? sec + ' s' : sec < 3600 ? Math.floor(sec / 60) + ' min ' + (sec % 60) + ' s' : sec < 172800 ? Math.floor(sec / 3600) + ' h ' + Math.floor((sec % 3600) / 60) + ' min' : Math.floor(sec / 86400) + ' days');
}
export function srcFresh(s: Source): number {
  if (s.lastSync == null) return 0;
  if (s.status === 'manual') return 45;
  const w = s.interval ? s.interval * 2 : 30, a = (Date.now() - s.lastSync) / 60000;
  return Math.max(4, Math.round(100 - Math.min(96, (a / w) * 100)));
}
export const cfgDefaults = (m: string): Record<string, string | number> => Object.fromEntries(connMethods()[m].fields.map((f) => [f.k, f.def]));
export function buildUrl(d: { method: string; cfg: Record<string, unknown>; url: string }): string {
  const c = d.cfg || {};
  if (d.method === 'jdbc') return 'jdbc:' + String(c.driver || '').toLowerCase().replace(/\s+/g, '') + '://' + c.host + ':' + c.port + '/' + c.database;
  if (d.method === 'delta') return String(c.endpoint || '');
  if (d.method === 'file') return c.delivery === 'SFTP drop' ? String(c.path || '') : '';
  return (d.url || '').trim();
}
export const tableHeight = (t: Table): number => 34 + Math.min(t.cols.length, 4) * 19 + (t.cols.length > 4 ? 18 : 0) + 38;
/** A journey step chip's content: number, label, kind (ext, built, human) and description (the demo's stp, after jmap). */
export function journeyStep(n: number): { n: number; label: string; kind: string; desc: string } {
  const J = ref<[number, string, string, string][]>('JSTEPS');
  const m = ref<number[]>('JMAP')[n] || n;
  const j = J[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

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
export async function resolveConflict(id: string) {
  // the server answers with the kept source's id and the field; the page names the authority and the kind
  const c = (lastConflicts ? peek<ConflictAnswer>(lastConflicts)?.conflicts : undefined)?.find((x) => x.id === id);
  const r = await invoke<{ id: string; kept: string; field: string; authority: string; kind: string }>('conflict.resolve', { id });
  if (r.ok) r.output = { ...r.output, authority: c?.authority ?? r.output.kept, kind: c?.kind ?? r.output.field };
  return r;
}
export const escalateConflict = (id: string) => invoke('conflict.escalate', { id });
export const commitImport = (ok: number, err: number, rows: unknown) =>
  invoke('import.commit', { ok, err, hash: hashId(JSON.stringify(rows)) });
export const updateTables = (input: Record<string, unknown>) =>
  invoke<{ op: string; name?: string; fks?: number; from?: string; to?: string }>('tables.update', input);
export const addComment = (key: string, text: string) => invoke('comment.add', { key, text });

/** Undo journaled actions: POST /api/journal/undo. */
export function undoActions(seqs: number[]) {
  void http('/api/journal/undo', { method: 'POST', body: { seqs } }).finally(invalidate);
}

/** Start every live source syncing, staggered like the demo's Sync all. Returns how many started. */
export function syncAllLive(): number {
  const l = sources().filter((s) => s.status === 'live' && !s.syncing);
  l.forEach((s, i) => window.setTimeout(() => invoke('source.sync', { source_id: s.id }), i * 120));
  return l.length;
}

export interface SyncResult { ok: boolean; rows: number; reason?: string }
/**
 * Report when a sync started with syncSource() finishes. The server runs it as a worker job whose sync run reaches the
 * live stream (kind `sync`) when it ends.
 */
export function followSync(id: string, done: (r: SyncResult) => void): void {
  syncsPending.set(id, Date.now());
  bump();
  const end = (r: SyncResult | null) => {
    stop();
    window.clearTimeout(t);
    syncsPending.delete(id);
    bump();
    if (r) done(r);
  };
  const stop = onStream((kind, data) => {
    const p = (data as { payload?: { source_id?: string; status?: string; records_read?: number } } | null)?.payload;
    if (kind !== 'sync' || !p || p.source_id !== id || p.status === 'running') return;
    const ok = p.status === 'ok' || p.status === 'partial';
    end({ ok, rows: p.records_read ?? 0, reason: ok ? undefined : 'see Sync & History for the reason.' });
  });
  const t = window.setTimeout(() => end(null), 5 * 60000); // no word from the worker: stop showing it as syncing
}

/* ---- source tables: layout only (positions), not journaled ---- */
/** tgLayout: clusters of up to two tables per row, three clusters per band. */
function layoutTables(m: TableModel) {
  const W = 190, G = 16, P = 44;
  let cx = 24, cy = 24, rowH = 0, col = 0;
  m.cl.forEach(([id]) => {
    const ts = m.t.filter((t) => t.cl === id);
    if (!ts.length) return;
    const per = ts.length > 2 ? 2 : ts.length, rows = Math.ceil(ts.length / per), hs: number[] = [];
    let bh = 0;
    for (let r = 0; r < rows; r++) {
      const h = Math.max(...ts.slice(r * per, r * per + per).map(tableHeight));
      hs.push(h);
      bh += h + G;
    }
    const bw = per * W + (per - 1) * G;
    if (col === 3) { cx = 24; cy += rowH + P + 10; rowH = 0; col = 0; }
    ts.forEach((t, i) => {
      const r = Math.floor(i / per), c = i % per;
      t.x = cx + c * (W + G);
      t.y = cy + 34 + hs.slice(0, r).reduce((a, b) => a + b + G, 0);
    });
    cx += bw + P + 14;
    rowH = Math.max(rowH, bh + 30);
    col++;
  });
  m.t.filter((t) => t.x == null).forEach((t, i) => { t.x = 24 + i * 210; t.y = cy + rowH + 40; });
}
export function moveTable(src: string, name: string, x: number, y: number) {
  const t = tableModel(src)?.t.find((t) => t.n === name);
  if (t) { t.x = x; t.y = y; bump(); }
}
export function alignTables(src: string) {
  const m = tableModel(src);
  if (!m) return;
  m.t.forEach((t) => { (t as { x: number | null }).x = null; });
  layoutTables(m);
  bump();
}

/* ---- near-real flows (5.10): pause, disconnect, re-authenticate and connect from the catalogue. The server has no
   action for them yet, so the pages change nothing and say so. ---- */
/** What the page says when the server has no action for a near-real flow yet. */
export const notOnServer = (what: string) => what + ' is not available on the server yet.';

/** Re-authentication finished: a stale source is reconnected through source.reconnect; otherwise null (no server action yet). */
export function reauthenticated(id: string): 'reconnect' | 'renewed' | null {
  const s = source(id);
  if (!s) return null;
  return s.status === 'stale' ? 'reconnect' : null;
}
