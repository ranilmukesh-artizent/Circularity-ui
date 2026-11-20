/**
 * Connection Fabric (#/integration): sources, catalogue, source map, source tables, canonical models, event stream,
 * conflicts, manual import and monitor. Typed reads over the engine; changes go through invoke() where the demo has an
 * action, and through the small helpers at the bottom for the demo's near-real flows (pause, disconnect, re-authenticate,
 * connect from the catalogue) that the demo itself does not journal.
 *
 * With VITE_BACKEND=api: GET /api/screens/integration/{sources, sources/{id}, overview, map, tables, models, events,
 * conflicts, monitor}, the Workflow Studio list (/api/screens/workflows) and the reference lists; the mapping, export by
 * export, is in di/screens/integration.py. Each endpoint needs its Connection Fabric section, so a read the account may
 * not make answers empty instead of asking. Sources, freshness, runs, records, conflicts and latency are the
 * connectors' real data, not the demo's. A sync is the real source.sync action, followed on the live stream.
 */
import { bump, engine } from '../engine/engine';
import { invoke } from './actions';
import { API } from './backend';
import { ApiError, cached, http, invalidate, onStream, peek, ref, session, withQuery } from './client';
import { visibleCases } from './product';
import { canPage, canRoute } from './session';

/* eslint-disable @typescript-eslint/no-explicit-any */
const g = () => engine();

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
  /** API only: the connector's own state (live, failing, auth_expired, unavailable); `status` shows failing and auth_expired as stale. */
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
export const sources = (): Source[] => (API ? apiSources() : g()<Source[]>('SOURCES'));
export const source = (id: string | null | undefined): Source | undefined => (id ? sources().find((s) => s.id === id) : undefined);
export function allMappings(): Record<string, MapRow[]> {
  if (!API) return g()<Record<string, MapRow[]>>('MAPPINGS');
  return modelsAnswer()?.mappings ?? mapAnswer()?.mappings ?? {};
}
export function mappings(id: string): MapRow[] {
  if (!API) return g()<Record<string, MapRow[]>>('MAPPINGS')[id] ?? [];
  return (may('models', 'map') ? allMappings()[id] : detail(id)?.mappings) ?? [];
}
export const connMethods = (): Record<string, ConnMethod> => (API ? ref('CONN_METHODS') : g()('CONN_METHODS'));
export function srcTypes(): Record<string, SrcType> {
  if (!API) return g()('SRC_TYPES');
  // a connected source of a type outside SRC_TYPES (from the catalogue's extra types) is listed too, as the demo adds it on connect
  const T = ref<Record<string, SrcType>>('SRC_TYPES'), extra = sources().filter((s) => !T[s.type]);
  return extra.length ? { ...T, ...Object.fromEntries(extra.map((s) => [s.type, typeOf(s.type)])) } : T;
}
export const srcCats = (): Record<string, string> => (API ? ref('SRC_CATS') : g()('SRC_CATS'));
export const srcCatNote = (): Record<string, string> => (API ? ref('SRC_CAT_NOTE') : g()('SRC_CAT_NOTE'));
export const authOpts = (): string[] => (API ? ref('AUTH_OPTS') : g()('AUTH_OPTS'));
export const canon = (): Canon[] => (API ? ref('CANON') : g()('CANON'));
export const canonExample = (n: string): unknown => (API ? ref<Record<string, unknown>>('CANON_EX') : g()<Record<string, unknown>>('CANON_EX'))[n];
export const canonPrefix = (): Record<string, string> => (API ? ref('CANON_PFX') : g()('CANON_PFX'));
export const events = (): StreamEvent[] => (API ? (may('events') ? cached<{ events: StreamEvent[] }>(BASE + '/events').events : []) : g()('EVENTS'));
export function catalog(): CatalogItem[] {
  if (!API) return g()('CATALOG');
  const o = overview();
  if (o) return o.catalog;
  const ids = new Set(sources().map((s) => s.id));
  return ref<CatalogItem[]>('CATALOG').map((c) => ({ ...c, connected: ids.has(c.id) }));
}
export const frCats = (): string[] => (API ? ref('FR_CATS') : g()('FR_CATS'));
export const frDecisions = (): [string, string, string[]][] => (API ? ref('FR_DEC') : g()('FR_DEC'));
export const intSub = (tab: string): string => (API ? ref<Record<string, string>>('FR_INT_SUB') : g()<Record<string, string>>('FR_INT_SUB'))[tab] ?? '';
export const intKids = (): [string, string, string, string?][] => (API ? ref('FR_INT_KIDS') : g()('FR_INT_KIDS'));
export const sampleCsv = (): string => (API ? ref('SAMPLE_CSV') : g()('SAMPLE_CSV'));
export const facilities = (): string[] => (API ? ref('FACILITIES') : g()('FACILITIES'));
export const tenantList = (): string[] => (API ? ref('TENANTS') : g()('TENANTS'));
export function tableModelIds(): string[] {
  if (!API) return Object.keys(g()<Record<string, unknown>>('TBL_MODELS'));
  return Object.keys(tablesAnswer()?.models ?? mapAnswer()?.table_models ?? {});
}
export const tableSuggestions = (src: string): { n: string; cl: string; desc: string; cols: string[] }[] =>
  (API ? ref<Record<string, any[]>>('TBL_AVAIL') : g()<Record<string, any[]>>('TBL_AVAIL'))[src] ?? [];
export const frSample = (type: string): [string, string, string, string, number][] => {
  const S = API ? ref<Record<string, [string, string, string, string, number][]>>('FR_SAMPLE') : g()<Record<string, [string, string, string, string, number][]>>('FR_SAMPLE');
  return (S[type] || S.db).map((r) => r.slice() as [string, string, string, string, number]);
};
export const frAuthOptions = (): [string, string, string][] => (API ? ref('FR_AUTH') : g()('FR_AUTH'));
export function caseExists(id: string): boolean {
  if (!API) return !!g()<Record<string, unknown>>('CASE_BY_ID')[id];
  return !!session() && id in cached<Record<string, unknown>>('/api/screens/nav/scope');
}
export function rbPath(p: string): boolean {
  if (!API) return !!g()<(p: string) => unknown>('rbPath')(p);
  const h = String(p).replace(/^#?\/?/, '').split('/');
  return canRoute({ page: h[0], a: h[1] || null, b: h[2] || null }) === true;
}
export const nowLabel = (): string => (API ? session()?.account.label ?? '—' : g()<() => string>('who')());

/* ---- derived (the demo's own helpers; with the API, the `health` each source comes with) ---- */
export function integrations(): Integration[] {
  if (!API) return g()<() => Integration[]>('frIntegrations')();
  const o = overview();
  if (!o) return [];
  const cat = new Map(o.catalog.map((c) => [c.id, c]));
  return o.integrations.map(({ src, catalog: c, ...x }) => ({ ...x, src: source(src), c: c ? cat.get(c) : undefined }));
}
export function recommendations(): Rec[] {
  if (!API) return g()<() => Rec[]>('frRecs')();
  const o = overview();
  if (!o) return [];
  return o.recommendations.map(({ source: s, catalog: c, ...x }) => ({ ...x, s: source(s), c: o.catalog.find((y) => y.id === c) }));
}
export const connected = (): Source[] => (API ? sources().filter((s) => s.status !== 'unavailable') : g()<() => Source[]>('frConnected')());
export function available(): CatalogItem[] {
  if (!API) return g()<() => CatalogItem[]>('frAvail')();
  const o = overview();
  return o ? o.available.map((id) => o.catalog.find((c) => c.id === id)!).filter(Boolean) : [];
}
export const needsAttention = (s: Source): boolean => (API ? !!health(s)?.needs_attention : g()<(s: Source) => boolean>('frNeedsAttn')(s));
export const srcFailing = (s: Source): boolean => (API ? !!health(s)?.failing : g()<(s: Source) => boolean>('frSrcFailing')(s));
export const credDays = (s: Source): number => (API ? health(s)?.cred_days ?? 0 : g()<(s: Source) => number>('frCredDays')(s));
export function series(s: Source, n: number): number[] {
  if (!API) return g()<(s: Source, n: number) => number[]>('frSeries')(s, n);
  const a = detail(s.id, n)?.series ?? [];
  return a.length >= n ? a.slice(-n) : Array<number>(n - a.length).fill(0).concat(a);
}
export const successRate = (s: Source): number => (API ? health(s)?.success ?? 0 : g()<(s: Source) => number>('frSuccess')(s));
export function failedRecords(s: Source, n: number): number {
  if (!API) return g()<(s: Source, n: number) => number>('frFailedRecs')(s, n);
  return n === 7 ? health(s)?.failed7 ?? 0 : detail(s.id, n)?.failed ?? 0;
}
export const typeOf = (t: string): SrcType => {
  if (!API) return g()<(t: string) => SrcType>('frTypeOf')(t);
  return ref<Record<string, SrcType>>('SRC_TYPES')[t] || ref<Record<string, SrcType>>('FR_XTYPES')[t] || { label: t, short: t, cat: 'internal', target: 'Asset & component', vendors: [] };
};
export const catOf = (s: Source): string => (API ? health(s)?.category ?? 'Custom' : g()<(s: Source) => string>('frCatOf')(s));
export const tableCount = (id: string): number => (API ? health(source(id) ?? ({ id } as Source))?.tables ?? 0 : g()<(id: string) => number>('frTblN')(id));
export const fieldCount = (id: string): number => (API ? health(source(id) ?? ({ id } as Source))?.fields ?? 0 : g()<(id: string) => number>('frFldN')(id));
export function srcModels(s: Source): Record<string, MapRow[]> {
  if (!API) return g()<(s: Source) => Record<string, MapRow[]>>('frSrcModels')(s);
  return (modelsAnswer() ?? mapAnswer())?.source_models[s.id] ?? detail(s.id)?.models ?? {};
}
export function tableModel(id: string): TableModel | null {
  if (!API) return g()<(id: string) => TableModel | null>('tgModel')(id);
  return (tablesAnswer()?.models ?? mapAnswer()?.table_models)?.[id] ?? null;
}
export function syncHistory(s: Source): { ts: number; ok: boolean; rows: number; dur: string }[] {
  if (!API) return g()<(s: Source) => { ts: number; ok: boolean; rows: number; dur: string }[]>('frSyncHist')(s);
  return detail(s.id)?.sync_history ?? [];
}
export const slaMinutes = (s: Source): number => (API ? health(s)?.sla ?? 60 : g()<(s: Source) => number>('frSla')(s));
export const latency = (s: Source): number | null => (API ? health(s)?.latency ?? null : g()<(s: Source) => number | null>('frLat')(s));
export const wfUsing = (id: string): string[] => (API ? health(source(id) ?? ({ id } as Source))?.workflows ?? [] : g()<(id: string) => string[]>('wfUsing')(id));
export const exceptions = (): MapException[] => (API ? mapAnswer()?.exceptions ?? [] : g()<() => MapException[]>('smExceptions')());
export const srcChannels = (s: Source): string[] => (API ? health(s)?.channels ?? [] : g()<(s: Source) => string[]>('srcCh')(s));
export function commentsOf(key: string): Comment[] {
  if (!API) return g()<(k: string) => Comment[]>('cmList')(key);
  return key.startsWith('src:') ? detail(key.slice(4))?.comments ?? [] : [];
}
export const smLog = (): SmLog[] => (API ? mapAnswer()?.activity ?? [] : g()<{ smLog: SmLog[] }>('S').smLog);
/** Open decisions (awaiting approval or re-evaluation) the account may see: the Product area's cases. */
export const openDecisionCount = (): number =>
  (API ? visibleCases() : g()<() => { stage: string }[]>('visCases')()).filter((c) => c.stage === 'awaiting_approval' || c.stage === 'reeval').length;

export function totals(): Totals {
  if (API) return (mapAnswer() ?? monitorAnswer())?.totals ?? { ok: 0, warn: 0, bad: 0, run: 0, pct: 100 };
  return g()<() => Totals>('hhTotals')();
}
export function hourly(): HourBucket[] {
  if (API) return (mapAnswer() ?? monitorAnswer())?.hourly ?? [];
  g()<() => void>('hhInit')();
  return g()<{ hh: HourBucket[] }>('S').hh;
}
/** The workflows: Workflow Studio's list, or, for accounts without the studio, the Monitor's workflows that ran. */
export function workflows(): Workflow[] {
  if (API) {
    if (may('studio')) return cached<{ workflows: Workflow[] }>('/api/screens/workflows').workflows;
    return monitorAnswer()?.workflows ?? [];
  }
  g()<() => void>('wfInit')();
  return g()<{ wf: { list: Workflow[] } }>('S').wf.list;
}
export const wfStat = (w: Workflow): string => (API ? (w as Workflow & { stat?: string }).stat ?? w.status : g()<(w: Workflow) => string>('wfStat')(w));
/** Published workflows (the Source Map's tile). */
export function publishedWorkflowCount(): number {
  if (API && !may('studio')) return mapAnswer()?.kpis.workflows_published ?? 0;
  return workflows().filter((w) => w.status === 'published').length;
}

/* ---- conflicts: the full queue is long with real data (hundreds), so it is read a page at a time ---- */
export interface ConflictPage { list: Conflict[]; total: number; open: number; closed: number; systems: number }
let lastConflicts: string | null = null;
/** The first `limit` conflicts (open, escalated and resolved, newest first), with the queue's counts. */
export function conflictPage(limit = 60): ConflictPage {
  if (!API) {
    const C = g()<Conflict[]>('CONFLICTS'), open = C.filter((c) => c.status === 'open').length;
    return { list: C, total: C.length, open, closed: C.length - open, systems: new Set(C.flatMap((c) => [c.a.src, c.b.src])).size };
  }
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
export const conflicts = (): Conflict[] => conflictPage(200).list;
/** Open conflicts in the queue (the Conflict Queue tab and the flow diagram). */
export function openConflictCount(): number {
  if (!API) return g()<Conflict[]>('CONFLICTS').filter((c) => c.status === 'open').length;
  if (may('conflicts')) return conflictPage().open;
  return mapAnswer()?.open_conflicts ?? 0;
}

/* ---- formatting and small pure helpers (the demo's, ported) ---- */
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
export function hashId(s: string): string {
  let h = 2166136261;
  for (const ch of s) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).toUpperCase().padStart(8, '0');
}
export const vHue = (v: string): number => {
  let h = 7;
  for (const c of v) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
};
/** The two letters of a vendor's logo tile. */
export const vendorInitials = (v: string): string => v.replace(/[^A-Za-z0-9 ]/g, '').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
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
export const methodMode = (m: string, iv: number): string =>
  m === 'native' ? 'Native connector · Polling · ' + iv + ' min' : m === 'jdbc' ? 'JDBC · Polling · ' + iv + ' min'
    : m === 'api' ? (iv ? 'API extractor · Polling · ' + iv + ' min' : 'API extractor · API + events') : m === 'event' ? 'Event API · Events'
      : m === 'delta' ? 'Delta Sharing · API read (live)' : 'Flat file · CSV import';
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
  const J = API ? ref<[number, string, string, string][]>('JSTEPS') : g()<[number, string, string, string][]>('JSTEPS');
  const m = (API ? ref<number[]>('JMAP')[n] : g()<(n: number) => number>('jmap')(n)) || n;
  const j = J[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

/** Static, trusted markup fragments from the demo (vendor logos, journey step chips, highlighted JSON); the pages draw these as React. */
export const vlogoHtml = (vendor: string): string => `<span class="vlogo" style="--h:${vHue(vendor)}" aria-hidden="true">${esc(vendorInitials(vendor))}</span>`;
export const stepHtml = (n: number): string => {
  const j = journeyStep(n);
  return `<span class="stp ${j.kind === 'built' ? '' : j.kind}" title="Journey step ${j.n}: ${esc(j.label)} — ${esc(j.desc)}"><b>${j.n}</b>${esc(j.label)}</span>`;
};
export const jsonHtml = (o: unknown): string =>
  esc(JSON.stringify(o, null, 2))
    .replace(/&quot;([^&]+?)&quot;:/g, '<span class="k">"$1"</span>:')
    .replace(/: &quot;(.*?)&quot;/g, ': <span class="s">"$1"</span>')
    .replace(/: (-?\d+(\.\d+)?)/g, ': <span class="n">$1</span>');

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
  if (!API) return invoke<{ id: string; authority: string; kind: string }>('conflict.resolve', { id });
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

/** Undo journaled actions: the journal is replayed without them on the next load (the demo's afUndo); with the API, POST /api/journal/undo. */
export function undoActions(seqs: number[]) {
  if (API) {
    void http('/api/journal/undo', { method: 'POST', body: { seqs } }).finally(invalidate);
    return;
  }
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

export interface SyncResult { ok: boolean; rows: number; reason?: string }
/**
 * Report when a sync started with syncSource() finishes. The engine finishes it on a timer; the server runs it as a
 * worker job whose sync run reaches the live stream (kind `sync`) when it ends.
 */
export function followSync(id: string, done: (r: SyncResult) => void): void {
  if (API) {
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
    return;
  }
  const wait = () => {
    const x = source(id);
    if (!x) return;
    if (x.syncing) { window.setTimeout(wait, 200); return; }
    const run = x.runs[0];
    if (!run) return;
    done({ ok: run.result !== 'failed', rows: run.rows, reason: 'the feed token has expired. Refresh the token to resume.' });
  };
  window.setTimeout(wait, 300);
}

/* ---- source tables: layout only (positions), not journaled in the demo either ---- */
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
  if (API) layoutTables(m);
  else g()<(m: TableModel) => void>('tgLayout')(m);
  bump();
}

/* ---- near-real flows (5.10); the demo changes these directly, without an action. The server has no action for them
   yet: with the API they change nothing and say so (null or false), and the page tells the person. ---- */
const bumpVer = (s: Source, change: string) => {
  const [a, b] = s.cfgVer.split('.');
  s.cfgVer = a + '.' + (+b + 1);
  s.audit.unshift({ ver: s.cfgVer, who: nowLabel(), ts: Date.now(), change });
};
const srcEvent = (s: Partial<Source>, type: string, ack: string, note: string) => g()<(...a: unknown[]) => void>('srcEvent')(s, type, ack, note);
const rbLog = (k: string, t: string) => g()<(k: string, t: string) => void>('rbLog')(k, t);
const smLogAdd = (s: Source, t: string, kind?: string) => g()<(...a: unknown[]) => void>('smLogAdd')(s, t, kind);
/** What the page says when the server has no action for a near-real flow yet. */
export const notOnServer = (what: string) => what + ' is not available on the server yet.';

/** Pause or resume scheduled syncs. Returns the new state and the number of workflows that read the source. */
export function togglePause(id: string): { paused: boolean; workflows: number } | null {
  if (API) return null;
  const s = source(id);
  if (!s) return null;
  s.paused = !s.paused;
  const who = nowLabel();
  srcEvent(s, s.paused ? 'source.paused' : 'source.resumed', 'acknowledged', s.paused ? 'Scheduled syncs stopped by ' + who : 'Scheduled syncs resumed by ' + who);
  rbLog(s.paused ? 'source.paused' : 'source.resumed', s.vendor + ' · by ' + who);
  bump();
  return { paused: !!s.paused, workflows: wfUsing(id).length };
}

/** Disconnect a source, keeping its settings for a reconnect. false when it could not be done. */
export function disconnectSource(id: string): boolean {
  if (API) return false;
  const s = source(id);
  if (!s) return false;
  const who = nowLabel();
  s.disconnected = true; s.paused = false; s.status = 'unavailable'; s.discBy = who; s.lastSync = null; s.fresh = '—'; s.freshMin = null;
  bumpVer(s, 'Disconnected; settings kept for reconnect');
  srcEvent(s, 'source.disconnected', 'acknowledged', 'Disconnected by ' + who);
  rbLog('source.disconnected', s.vendor + ' · by ' + who);
  smLogAdd(s, 'Disconnected by ' + who, 'warn');
  bump();
  return true;
}

/** Re-authentication finished: renew the credential; a stale source is reconnected through source.reconnect. */
export function reauthenticated(id: string): 'reconnect' | 'renewed' | null {
  const s = source(id);
  if (!s) return null;
  if (API) return s.status === 'stale' ? 'reconnect' : null;
  s.credAt = Date.now(); s.credDays = 180;
  rbLog('source.reauthenticated', s.vendor + ' · by ' + nowLabel());
  if (s.status === 'stale') return 'reconnect';
  bumpVer(s, 'Re-authenticated; credential renewed');
  bump();
  return 'renewed';
}

/** Note a connection test in the event stream (the engine's; the server has no record of browser-side tests). */
export function recordTest(s: Partial<Source>, ok: boolean, failedAt: string) {
  if (API) return;
  srcEvent(s, 'source.tested', ok ? 'acknowledged' : 'error', ok ? 'Connection test passed' : 'Connection test failed at ' + failedAt);
  bump();
}

/** The connect flow's last step: the new source, its accepted mappings and its draft ingest workflow (the demo's frCxFinish). */
export function finishConnect(catId: string, authLabel: string, scopes: string[], n: number, accepted: MapRow[]): string | null {
  if (API) return null;
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
