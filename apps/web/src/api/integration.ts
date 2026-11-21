/**
 * Connection Fabric (#/integration): sources, catalogue, source map, source tables, canonical models, event stream,
 * conflicts, manual import and monitor. Changes go through invoke(), the near-real flows too (pause, resume,
 * disconnect, re-authenticate, test a connection, connect from the catalogue: di/actions/fabric_sources.py).
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


export type SrcStatus = 'live' | 'stale' | 'manual' | 'unavailable';
export interface SyncRun { id: string; ts: number; trigger: string; rows: number; dur: number; result: string; note: string }
export interface AuditEntry { ver: string; who: string; ts: number; change: string }
export interface Source {
  id: string; type: string; cat: string; name: string; short: string; vendor: string; ver: string; env: string; url: string;
  status: SrcStatus; mode: string; interval: number; auth: string; freshMin: number | null; fresh: string; compl: number; conf: number;
  rw: string; inputs: string; read: string[]; write: string[]; step: number[]; authority: string[]; owner: string; records: number;
  note?: string; cfgVer: string; lastSync: number | null; updatedAt: number; runs: SyncRun[]; audit: AuditEntry[];
  method: string; cfg: Record<string, string | number>; credAt: number; credDays: number; credential?: Credential;
  syncing?: boolean; syncPct?: number; paused?: boolean; disconnected?: boolean; discBy?: string | null; frConnectedAt?: number;
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
  status: 'open' | 'resolved'; since: string; escalated?: { by: string; at: string; to?: string };
  /** every source's value; resolved: who closed it and the note (which value was kept, and why) */
  values?: { source: string; src: string; val: string }[]; authorityId?: string; resolved?: { by: string; at: string | null; note?: string | null };
}
/** conflict.resolve beyond the demo's accept-the-authority: keep another source's value or enter one, with a reason. */
export interface ConflictChoice { choose: 'authority' | 'other' | 'value'; source?: string; value?: string; reason?: string }
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
  mapping?: { version: number | null; versions: MapVersion[] };
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
/** One step of a workflow over the Monitor's window: p95 duration (s) and the records it still holds, by rule. */
export interface MonitorStep { id: string; label: string; p95: number | null; held: Record<string, number>; heldN: number }
/** The Monitor's per-workflow row: the real runs of the last 24 hours (`real`), or the demo's stats when it has none. */
export interface MonitorWorkflow {
  id: string; name: string; runsN: number; okN: number; last: Workflow['last']; stat: string; real: boolean; runs24: number; ok24: number; success: number | null; p95: number | null; avg: number | null;
  lastState: string | null; steps: MonitorStep[];
}
interface MonitorAnswer { hourly: HourBucket[]; totals: Totals; workflows: (MonitorWorkflow & Workflow)[] }
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
  const T = ref('SRC_TYPES'), extra = sources().filter((s) => !T[s.type]);
  return extra.length ? { ...T, ...Object.fromEntries(extra.map((s) => [s.type, typeOf(s.type)])) } : T;
}
export const srcCats = (): Record<string, string> => ref('SRC_CATS');
export const srcCatNote = (): Record<string, string> => ref('SRC_CAT_NOTE');
export const authOpts = (): string[] => ref('AUTH_OPTS');
export const canon = (): Canon[] => ref('CANON');
export const canonExample = (n: string): unknown => ref('CANON_EX')[n];
export const canonPrefix = (): Record<string, string> => ref('CANON_PFX');
export const events = (): StreamEvent[] => (may('events') ? cached<{ events: StreamEvent[] }>(BASE + '/events').events : []);
export function catalog(): CatalogItem[] {
  const o = overview();
  if (o) return o.catalog;
  const ids = new Set(sources().map((s) => s.id));
  return ref('CATALOG').map((c) => ({ ...c, connected: ids.has(c.id) }));
}
export const frCats = (): string[] => ref('FR_CATS');
export const frDecisions = (): [string, string, string[]][] => ref('FR_DEC');
export const intSub = (tab: string): string => ref('FR_INT_SUB')[tab] ?? '';
export const intKids = (): [string, string, string, string?][] => ref('FR_INT_KIDS');
export const sampleCsv = (): string => ref('SAMPLE_CSV');
export const facilities = (): string[] => ref('FACILITIES');
export const tenantList = (): string[] => ref('TENANTS');
export function tableModelIds(): string[] {
  return Object.keys(tablesAnswer()?.models ?? mapAnswer()?.table_models ?? {});
}
export const tableSuggestions = (src: string): { n: string; cl: string; desc: string; cols: string[] }[] =>
  ref('TBL_AVAIL')[src] ?? [];
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
  ref('SRC_TYPES')[t] || ref('FR_XTYPES')[t] || { label: t, short: t, cat: 'internal', target: 'Asset & component', vendors: [] };
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
/** The Monitor's per-workflow rows (the workflows that ran), with their 24-hour and per-step stats. */
export const monitorWorkflows = (): MonitorWorkflow[] => monitorAnswer()?.workflows ?? [];
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
  const J = ref('JSTEPS');
  const m = ref('JMAP')[n] || n;
  const j = J[m - 1];
  return { n: m, label: j[1], kind: j[2], desc: j[3] };
}

/* ---- changes through the action registry ---- */
export const syncSource = (id: string) => invoke('source.sync', { source_id: id });
export const reconnectSource = (id: string) => invoke('source.reconnect', { source_id: id });
/** Rotate credentials: the new secret (8 characters or more) is stored encrypted on the server and never returned. */
export interface Credential { kind: string; version: number; last4: string; issued_at: number | string | null; expires_at: number | string | null }
export const rotateCredentials = (id: string, days: number, secret: string) =>
  invoke<{ source_id: string; ver: string; stale: boolean; credential: Credential | null }>('credentials.rotate', { source_id: id, days, secret });
export const deleteSource = (id: string) => invoke<{ source_id: string; name: string; vendor: string }>('source.delete', { source_id: id });
export interface Draft {
  type: string; name: string; vendor: string; ver: string; env: string; url: string; method: string;
  cfg: Record<string, string | number>; interval: number | ''; auth: string; owner: string;
}
export const saveSource = (mode: 'new' | 'edit', id: string, d: Draft, maps: string[][], ops: { read: string[]; write: string[] }) =>
  invoke<{ mode: 'new' | 'edit'; source_id: string; name: string; vendor?: string; ver?: string; csv?: boolean; wasOff?: boolean }>('source.update', {
    mode, id, d, maps, ops, note: '',
  });
export async function resolveConflict(id: string, choice?: ConflictChoice) {
  // the server names the authority and the kind; the queue's copy is the fallback
  const c = (lastConflicts ? peek<ConflictAnswer>(lastConflicts)?.conflicts : undefined)?.find((x) => x.id === id);
  const r = await invoke<{ id: string; kept: string; field: string; authority: string; kind: string; choose?: string; value?: unknown; keptName?: string }>(
    'conflict.resolve', choice && choice.choose !== 'authority' ? { id, ...choice } : { id },
  );
  if (r.ok) r.output = { ...r.output, authority: r.output.authority || c?.authority || r.output.kept, kind: r.output.kind || c?.kind || r.output.field };
  return r;
}
export const escalateConflict = (id: string) => invoke('conflict.escalate', { id });
export interface ImportRow { asset_id: string; qty: string; grade: string; location: string; owner: string; received: string; errors: string[] }
/** The import.commit input: the demo's counts and hash (of every validated row, so the same file loads once), plus
 *  the valid rows themselves, which the server checks again and loads, tagged manual, and the rejected rows, which it
 *  holds as failed records (plan 6 B3). */
export function importInput(ok: number, err: number, rows: ImportRow[]) {
  const pick = ({ asset_id, qty, grade, location, owner, received }: ImportRow) => ({ asset_id, qty, grade, location, owner, received });
  const valid = rows.filter((r) => !r.errors.length).map(pick);
  const rejected = rows.filter((r) => r.errors.length).map(pick);
  return { ok, err, hash: hashId(JSON.stringify(rows)), rows: valid, rejected };
}
export const commitImport = (ok: number, err: number, rows: ImportRow[]) => invoke('import.commit', importInput(ok, err, rows));
export const updateTables = (input: Record<string, unknown>) =>
  invoke<{ op: string; name?: string; fks?: number; from?: string; to?: string; table?: Table; index?: number; gone?: string[][]; fk?: string[] }>('tables.update', input);
export const addComment = (key: string, text: string) => invoke('comment.add', { key, text });

/** Undo journaled actions: POST /api/journal/undo. */
export function undoActions(seqs: number[]) {
  void http('/api/journal/undo', { method: 'POST', body: { seqs } }).finally(invalidate);
}

/** Start every live source syncing, staggered like the demo's Sync all. Returns how many started. */
export function syncAllLive(): number {
  const l = sources().filter((s) => s.status === 'live' && !s.syncing && !s.paused);
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

/* ---- source tables: positions. A drag moves the card on screen at once; when it ends (and after Auto Align) the
   positions are saved with tables.update {op: 'layout'}, so they survive a reload and the next edit's re-read. ---- */
/** tgLayout: clusters of up to two tables per row, three clusters per band. */
export function layoutTables(m: TableModel) {
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
/** Save the positions of the named tables (all when none are named). */
export function saveTableLayout(src: string, names?: string[]) {
  const m = tableModel(src);
  if (!m) return Promise.resolve(null);
  const pos: Record<string, [number, number]> = {};
  m.t.filter((t) => !names || names.includes(t.n)).forEach((t) => { pos[t.n] = [t.x, t.y]; });
  return invoke<{ op: 'layout'; moved: number }>('tables.update', { src, op: 'layout', table: { pos } });
}
export function alignTables(src: string) {
  const m = tableModel(src);
  if (!m) return Promise.resolve(null);
  m.t.forEach((t) => { (t as { x: number | null }).x = null; });
  layoutTables(m);
  bump();
  return saveTableLayout(src);
}

/* ---- near-real flows (5.10): pause and resume, disconnect, re-authenticate, test a connection and connect from the
   catalogue, each a server action (di/actions/fabric_sources.py). ---- */
export const pauseSource = (id: string) =>
  invoke<{ source_id: string; name: string; vendor: string; paused: boolean; workflows: number }>('source.pause', { source_id: id });
export const resumeSource = (id: string) => invoke<{ source_id: string; name: string; vendor: string }>('source.resume', { source_id: id });
/** Disconnect; `confirm` is the vendor's name as the person typed it (the server checks it too). */
export const disconnectSource = (id: string, confirm: string) =>
  invoke<{ source_id: string; name: string; vendor: string }>('source.disconnect', { source_id: id, confirm });

/**
 * Re-authentication finished: a stale source is reconnected (source.reconnect: token refreshed, re-synced); any other
 * gets its credential renewed for 180 days (credentials.rotate, recorded as a re-authentication).
 */
export async function reauthenticated(id: string) {
  if (source(id)?.status === 'stale') return 'reconnect' as const;
  return invoke<{ source_id: string; ver: string }>('credentials.rotate', { source_id: id, days: 180, reauth: true });
}

export interface TestStep { ok: boolean; msg: string }
export interface TestInput { source_id: string; reauth?: boolean; auth?: string; secret?: string }
/** The connection test (source.test, a read): DNS, TLS, Auth, Permissions, Sample read, probed by the server; the steps
 *  up to the first failure. A catalogue system being connected is `cat:<id>`, probed with the key typed (`secret`). */
export const testConnection = (input: TestInput) =>
  invoke<{ source_id: string; steps: TestStep[]; ok: boolean; at: string }>('source.test', { ...input });
/** The drawer's one-line test of the settings being edited (source.test with `draft`). */
/* ---- the field mapping a sync applies (plan 6 A4: di/connectors/mapping.py) ---- */
export interface MapVersion { version: number; by: string; at: string; note: string | null; rows: number }
export interface MapPreviewFact {
  target: string; key: string; value: unknown; source_field: string | null; source_value: unknown; transform: string | null;
  status: 'kept' | 'changed' | 'added';
}
export interface MapPreview {
  source_id: string; version: number | null; record: { resource: string; ext_id: string; payload: unknown } | null;
  facts: MapPreviewFact[]; dropped: string[]; error: string | null;
}
/** The saved versions of a source's mapping, newest first; version null: the adapter's own mapping runs. */
export function mappingVersions(id: string): { version: number | null; versions: MapVersion[] } {
  return detail(id)?.mapping ?? { version: null, versions: [] };
}
/** A sample record of the source mapped with the draft rows (or the saved mapping): a read, nothing is saved. */
export const previewMapping = (id: string, maps?: string[][]) =>
  invoke<MapPreview>('mapping.preview', maps ? { source_id: id, maps } : { source_id: id });
/** Revert: a new mapping version equal to an older one; the next sync applies it. */
export const revertMapping = (id: string, version: number) =>
  invoke<{ source_id: string; version: number; ver: string; rows: number; maps: string[][] }>('mapping.revert', { source_id: id, version });

export const testDraft = (id: string, d: Draft, ops: { read: string[]; write: string[] }) =>
  invoke<{ ok: boolean; msg: string }>('source.test', {
    source_id: id,
    draft: { method: d.method, url: buildUrl(d), auth: d.auth, read: ops.read.filter((x) => x.trim()).length, write: ops.write.filter((x) => x.trim()).length },
  });

/** A suggested row: source field, sample, canonical model.field, normalised, confidence %, resource. */
export type SuggestedMap = [string, string, string, string, number, string?];
/**
 * Suggest mappings for a catalogue system (mapping.catalogSuggest, a read): the rows its template maps, each with a sample read
 * from the system now; only fields its records really have, none for a system with no circularity data.
 */
export const suggestMappings = (cat: string) =>
  invoke<{ catalog_id: string; rows: SuggestedMap[]; error: string | null }>('mapping.catalogSuggest', { catalog_id: cat });

/** The synthetic key the simulated system of a catalogue entry accepts (source.sandboxKey, a read): the Connect dialog prefills it. */
export const sandboxKey = (cat: string) => invoke<{ catalog_id: string; key: string }>('source.sandboxKey', { catalog_id: cat });

/** Finish connecting a catalogue system: the source, its accepted mappings and the key typed, stored encrypted
 *  (source.update, mode "catalog"); without a key the server stores the simulated system's sandbox key. */
export const connectFromCatalog = (cat: string, auth: string, scopes: string[], maps: SuggestedMap[], secret?: string) =>
  invoke<{ mode: 'catalog'; source_id: string; name: string; vendor: string; records: number | null; queued: boolean; csv: boolean }>('source.update', {
    mode: 'catalog', id: '', d: { catalog: cat, auth, scopes }, maps, ops: {}, ...(secret ? { secret } : {}),
  });
