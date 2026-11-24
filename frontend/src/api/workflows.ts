/**
 * Workflow Studio: typed reads over the workflow list, the step catalogue (XF, FXD, ACT_TYPES, TOOLS), the workflow
 * checks and the run simulation. Changes go through invoke() with the demo's action ids: workflow.save,
 * workflow.publish, workflow.setStatus, workflow.create, workflow.duplicate, workflow.delete, workflow.run (and
 * workflow.validate as a read), and the server's workflow.saveTemplate, workflow.reprocess and workflow.applyFix for
 * the controls the demo ran in the browser, and workflow.restore for the History tab's versions (plan 6 C8).
 *
 * backend/di/services/screens/workflows.py has the mapping, export by export:
 * - the list, the recent runs and the attention list: GET /api/screens/workflows; one workflow's graph, saved
 *   version, template, history and failed records: GET /api/screens/workflows/{id};
 * - sources: GET /api/screens/integration/sources; field mappings: GET /api/screens/integration/models; the agents
 *   (agentsUsing): GET /api/screens/mcp/agents; the static lists: ref();
 * - the canvas checks and the test-run simulation run in the browser on the unsaved draft (src/api/workflowGraph.ts);
 *   the page merges in the server's full checks for the same draft (workflow.validate with `graph`: serverChecks);
 * - a run is followed on the stream (kind `workflow`) by the run key workflow.run returns.
 *
 * The canvas edits a copy of the graph held by the page (src/pages/workflows/draftStore.ts).
 */
import * as G from './workflowGraph';
import { invoke } from './actions';
import { ApiError, cached, onStream, ref, session } from './client';
import type { ActionResult } from './types';

export type StepKind = 'fixed' | 'conn' | 'wconn' | 'act' | 'xf' | 'map' | 'tool';
/** `cfg`: the block's settings that differ from its defaults (di/workflow/blocks.py); absent: all defaults. */
export interface WfNode { id: string; k: StepKind; ref: string; x: number; y: number; fail?: boolean; ai?: number; cfg?: Record<string, unknown> }
export interface WfEdge { id: string; a: string; b: string; locked: boolean }
export interface WfGraph { nodes: WfNode[]; edges: WfEdge[] }
export interface Trigger { t: string; min?: number }
export type WfStatus = 'published' | 'draft' | 'paused';
export type WfStat = WfStatus | 'failing';
export type RunState = 'queued' | 'running' | 'success' | 'warning' | 'failed' | 'upstream_failed' | 'held' | 'waiting' | 'skipped';

export interface LastRun { ts: number; state: RunState; dur: number; rows: number; note: string }
export interface Workflow {
  id: string; name: string; status: WfStatus; ver: string; cat: 'Ingest' | 'Outbound' | 'Decision'; kind: 'pipe' | 'dec';
  src: string | null; owner: string; trig: Trigger; desc: string; running: boolean; dirty: boolean;
  last: LastRun | null; runsN: number; okN: number; updated: number | string;
  /** `retries`: the retries setting the run used (once one is saved). A real run (plan 6 C5, C7) also has the records
   * in and out of each step (`counts`), the tries per step (`attempts`), the records it held and its run key. */
  lastRun?: {
    id: string; ts: number; t0: number; trig: string; states: Record<string, RunState>; dur: Record<string, number>; order: string[]; status: string; note: string; retries?: number;
    counts?: Record<string, Counts>; attempts?: Record<string, number>; held?: number; key?: string;
  };
  frFix?: string; frReproc?: string; retries?: number; alert?: string; aiNote?: string;
  /** 'paused' when its source is paused in the Connection Fabric (the server's "Paused upstream", plan 6 C10). */
  upstream?: 'paused';
}
export interface RunRow { id: string; wf: string; name: string; ts: number; trig: string; dur: number; rows: number; state: RunState; note: string }
export interface HistoryRow { id: string; ts: number; state: RunState; dur: number; rows: number; trig: string; note: string }
/** A run's figures as the server counts them: records read (`in`), still held (failed_record) and `out` = in - held
 *  (null for a failed run); null while it runs. A seeded run that never ran in the app is `{ real: false }`. */
export interface RunFigure { real: boolean; key?: string; in?: number | null; out?: number | null; held?: number | null }
/** Held records of one step, field and rule (each record once). */
export interface HeldGroup { step: string; label: string; field: string; rule: string; n: number }
/** The latest real run: its records read, held and passed, and its held records grouped. */
export interface RunQuality { real: true; key: string; run: string; state: string; in: number | null; held: number; valid: number | null; groups: HeldGroup[] }
export interface Check { sev: 'error' | 'warn' | 'info'; id: string; msg: string }
export interface StepInfo { label: string; sub: string; tag: string; in: boolean; out: boolean; desc: string }
export interface Source {
  id: string; name: string; vendor: string; short?: string; status: 'live' | 'stale' | 'manual' | 'unavailable'; mode: string; auth: string;
  read: string[]; write: string[]; cat: string; fresh: string; owner: string; type: string; url?: string; paused?: boolean; deleted?: boolean;
  /** A source made in the Connection Fabric (from the list's `live`): the model its mapping feeds, how it takes instructions. */
  target?: string; deliver?: string[];
}
/** A test run on the canvas (the demo's S.wf.run). */
export interface TestRun {
  status: 'running' | 'held' | 'failed' | 'success'; warn?: boolean; states: Record<string, RunState>; dur: Record<string, number | string>;
  order: string[]; i: number; approved: boolean; t0: number; id: string; trig: string;
  /** The tries per step of a real run (plan 6 C7); a test run has none. */
  attempts?: Record<string, number>;
  /** A test run (workflow.testRun, plan 6 C9): a dry run on the server with real records in and out of each step,
   *  each step's first records before and after it, and what was held. */
  dry?: boolean; counts?: Record<string, Counts>; samples?: Record<string, StepSamples>; rows?: number; held?: number; note?: string;
}
/** A record as a test run shows it: its id and data (after mapping, its canonical facts; a rejected one, its rule). */
export interface SampleRec { ext_id: string; resource: string; data?: Record<string, unknown>; facts?: { model: string; key: string; field: string; value: unknown }[]; rule?: string; field?: string; reason?: string }
export interface StepSamples { before: SampleRec[]; after: SampleRec[] }
/** What workflow.testRun answers. */
export interface TestRunResult {
  id: string; name: string; dry: true; status: 'held' | 'failed' | 'success'; states: Record<string, RunState>; counts: Record<string, Counts>;
  dur: Record<string, number>; order: string[]; samples: Record<string, StepSamples>; rows: number; held: number; note: string; approved: boolean;
}
export interface Counts { in: number; out: number; rej: number }
type Attention = { ic: string; h: string; t: string; s: string; arg: string; go?: string };

// ---------------------------------------------------------------- the API answers
export interface WfTemplate { id: string; from: string; name: string; cat: string; kind: string; src: string | null; owner: string; trig: Trigger }
/** `live`: each source's status for the checks as the server reads it now (plan 6 C10, di/workflow/live.py). */
interface ListAnswer { workflows: Workflow[]; runs: RunRow[]; attention: Attention[]; templates?: WfTemplate[]; now?: number; live?: G.LiveState }
export interface Saved { graph: WfGraph; name: string; owner: string; trig: Trigger; retries?: number; alert?: string }
interface Detail {
  workflow: Workflow & { graph: WfGraph };
  saved: Saved | null;
  template: WfGraph | null;
  history: HistoryRow[];
  /** One per history entry: the run's real in / out / held, or `{ real: false }` for a seeded run (plan 6 follow-up). */
  run_figures?: RunFigure[];
  failed_rows: { rec: string; field: string; value: string; rule: string }[];
  /** The latest real run's figures and held records by step, field and rule; null when the last run is seeded. */
  quality?: RunQuality | null;
  versions?: WfVersion[];
  published_ver?: string | null;
  /** The signed-in person's autosaved working copy (plan 6 C9, workflow.draft.save), or null. */
  draft?: ServerDraft | null;
}
/** A working copy kept on the server (di/services/actions/workflow_drafts.py). `base`: the ver|updated it was taken from. */
export interface ServerDraft { graph: WfGraph; name: string; owner?: string; trig?: Trigger; retries?: number; alert?: string; base?: string; at?: string }
/** A kept version of a workflow (plan 6 C8): `current` is the saved one, `published` the one runs use. */
export interface WfVersion { ver: string; at: string; by: string; note: string; current: boolean; published: boolean }
/** What changed from version a to version b (GET /api/screens/workflows/{id}/compare). */
export interface VersionDiff {
  a: string; b: string;
  blocks: { added: { id: string; label: string }[]; removed: { id: string; label: string }[]; changed: { id: string; label: string; fields: { field: string; from: unknown; to: unknown }[] }[] };
  links: { added: { a: string; b: string }[]; removed: { a: string; b: string }[] };
  settings: { key: string; from: unknown; to: unknown }[];
}
type ApiSource = Source & { compl?: number; health?: { workflows?: string[] } };
/** A block setting (di/workflow/blocks.py FieldSpec). */
export type FieldType = 'text' | 'number' | 'select' | 'multi' | 'bool' | 'fields' | 'rules' | 'mapping';
export interface FieldSpec {
  key: string; label: string; type: FieldType; default: unknown; required: boolean; choices: string[] | null; help: string;
  min: number | null; max: number | null; source: string | null;
}
export interface BlockSpec { ref: string; readonly: boolean; fields: FieldSpec[] }
export interface Rule { field: string; check: string; arg?: string }
interface BlocksAnswer { blocks: BlockSpec[]; resources?: Record<string, string[]>; operations?: Record<string, string[]>; palette?: Xf[] }

const listA = () => cached<ListAnswer>('/api/screens/workflows');
const detailA = (id: string) => cached<Detail>('/api/screens/workflows/' + encodeURIComponent(id));
const sourcesA = () => cached<{ sources: ApiSource[] }>('/api/screens/integration/sources').sources;
const mappingsA = () => cached<{ mappings: Record<string, string[][]> }>('/api/screens/integration/models').mappings;

/** The reference lists and sources the ported graph logic reads; the sources with the status the server's checks read
 *  (paused, disconnected ... over the demo's statuses), so the canvas checks agree with workflow.validate. */
function lk(): G.Lookups {
  return {
    sources: G.liveSources(sourcesA(), listA().live), mappings: mappingsA(), XF: transforms(), FR_XF: frTransforms(), FXD: ref('FXD'), ACT_TYPES: ref('ACT_TYPES'), TOOLS: ref('TOOLS'),
    MAP_TARGET: ref('MAP_TARGET'), SH: ref('SH'), DELIVER: ref('DELIVER'), CH_ARR: ref('CH_ARR'), CH_DEL: ref('CH_DEL'),
  };
}

/** Enough of the lookups for the source helpers (srcOr, srcLabel), without the field mappings. */
const srcL = () => ({ sources: sourcesA(), SH: ref('SH') }) as unknown as G.Lookups;
/** The source lookups with the list's overlay: a source made in the Connection Fabric's target and delivery. */
const srcLive = () => ({ sources: G.liveSources(sourcesA(), listA().live), SH: ref('SH'), MAP_TARGET: ref('MAP_TARGET'), DELIVER: ref('DELIVER') });

/** Run f, waiting for the reads it suspends on (for event handlers and timers, which cannot suspend). */
async function settle<T>(f: () => T): Promise<T> {
  for (;;) {
    try {
      return f();
    } catch (x) {
      if (x instanceof Promise) await x;
      else throw x;
    }
  }
}

// ---------------------------------------------------------------- the clock
const seenAt = new WeakMap<object, number>();
const T0 = Date.now();
/** "Now" on the clock the run times are on: the workspace clock. */
export function nowMs(): number {
  const a = listA();
  if (!seenAt.has(a)) seenAt.set(a, Date.now());
  return a.now != null ? a.now + (Date.now() - seenAt.get(a)!) : Date.parse(ref('AS_OF')) + (Date.now() - T0);
}

// ---- the list ----
export function workflows(): Workflow[] {
  return listA().workflows;
}
export const workflow = (id: string): Workflow | undefined => workflows().find((w) => w.id === id);
export const recentRuns = (): RunRow[] => listA().runs;
export const wfStat = (w: Workflow): WfStat => G.wfStat(w);
export const trigText = (t: Trigger): string => G.trigText(t);
export const ageShort = (ms: number): string => G.ageShort(ms);
/** "4 min ago" */
export const ago = (ms: number): string => G.frAgo(ms);
export const RUN_LABEL = (): Record<string, string> => ref('WF_STL');
export const RUN_CHIP = (): Record<string, string> => ref('WF_STC');
export const NOWF = (): string => ref('NOWF');

/** Items that need attention in the right column: failing workflows, expired credentials, high failure rates. */
export const attention = (): Attention[] => listA().attention;
/** The templates saved from workflows (S.frTpl), oldest first; New workflow lists them. */
export const templates = (): WfTemplate[] => listA().templates ?? [];

/** Follow a run started with runWorkflow (by the run key it returned) until it finishes; returns the unsubscribe. */
export function followRun(key: string, done: (r: RunRow) => void): () => void {
  const off = onStream((kind, data) => {
    const p = (data as { payload?: { collection?: string; id?: string; data?: RunRow } } | null)?.payload;
    if (kind !== 'workflow' || p?.collection !== 'workflow_runs' || p.id !== key || !p.data || p.data.state === 'running') return;
    off();
    done(p.data);
  });
  return off;
}

// ---- graphs ----
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
export const WF_W = G.WF_W, WF_H = G.WF_H, WF_WH = 640;
export const worldWidth = (kind: 'pipe' | 'dec'): number => (kind === 'pipe' ? 1680 : 1240);

/** A copy of the workflow's current graph (built from its template on first use). */
export function graphOf(id: string): WfGraph {
  const w = workflow(id);
  if (!w) return { nodes: [], edges: [] };
  return clone(detailA(id).workflow.graph);
}
/** Version stamp of the graph graphOf returns (the working copy is refreshed when it changes). */
export function graphStamp(id: string): string {
  const w = detailA(id).workflow;
  return w ? w.ver + '|' + String(w.updated) : '';
}
/** The last saved version, for Discard. */
export function savedOf(id: string): Saved | null {
  return workflow(id) ? clone(detailA(id).saved) : null;
}
/** A fresh graph from the workflow's template, for Reset to template. */
export function templateOf(id: string): WfGraph {
  return (workflow(id) && clone(detailA(id).template)) || { nodes: [], edges: [] };
}
export const stepInfo = (n: WfNode): StepInfo => G.info(lk(), n);
/** Errors, warnings and notes, each with the step it belongs to (sorted errors first). */
export const validate = (g: WfGraph, kind: 'pipe' | 'dec'): Check[] => G.validate({ ...lk(), ...blocksL() }, g, kind);
type ServerCheck = { msg: string; node: string; sev: Check['sev'] };
/** The server's full checks for a draft (workflow.validate with the graph): the browser's rules plus the live sources
 *  and the fields records really carry, each with its step. null when the call is refused or fails. */
export async function serverChecks(id: string, graph: WfGraph): Promise<Check[] | null> {
  const r = await invoke<{ errors: ServerCheck[]; warnings: ServerCheck[] }>('workflow.validate', { id, graph });
  if (!r.ok) return null;
  return [...r.output.errors, ...r.output.warnings].map((x) => ({ sev: x.sev, id: x.node, msg: x.msg }));
}
/** The browser's checks with the server's for the same draft; the server's win on a duplicate. */
export const mergeChecks = (browser: Check[], server: Check[] | null | undefined, g: WfGraph): Check[] => G.mergeChecks(browser, server, g);
/** The saved version a published workflow can publish (newer than the one runs use), or null. */
export const republishVer = (w: Workflow): string | null => G.republishVer(w, publishedVersion(w.id));
/** null when a → b may be connected, otherwise the reason it may not. */
export const canLink = (g: WfGraph, a: string, b: string): string | null => G.canLink(lk(), g, a, b);
export const runOrder = (g: WfGraph): string[] => G.order(g);
export function analyze(g: WfGraph): { pred: Record<string, string[]>; succ: Record<string, string[]>; desc: (id: string) => Set<string> } {
  return G.analyze(g);
}
/** The last real run, painted on the canvas when the workflow opens. */
export function runFromLast(id: string): TestRun | null {
  const w = workflow(id);
  if (!w) return null;
  const l = w.lastRun;
  if (!l) return null;
  const ids = new Set(detailA(id).workflow.graph.nodes.map((n) => n.id));
  return {
    status: (l.status === 'warning' ? 'success' : l.status) as TestRun['status'], warn: l.status === 'warning', states: { ...l.states }, dur: l.dur,
    order: l.order.filter((x) => ids.has(x)), i: l.order.length, approved: true, t0: l.t0, id: l.id, trig: l.trig,
    ...(l.attempts ? { attempts: { ...l.attempts } } : {}),
    // the records in and out of each step that the run really counted (Task instances shows them)
    ...(l.counts ? { counts: { ...l.counts } } : {}),
  };
}
export const runTimes = (r: TestRun): Record<string, { s: number; e: number; d: number; ex: boolean }> => G.runTimes(r, nowMs());
export const hashId = (s: string): string => G.hashId(s);

/** Records in and out of each step. For the last run (no states, or its states): what the run really counted
 * (`lastRun.counts`, plan 6 C5), none for a seeded run that never ran; for a test run's states, the browser's estimate. */
export function runCounts(id: string, g: WfGraph, states: Record<string, RunState> | null): Record<string, Counts> {
  const w = workflow(id);
  if (!w) return {};
  const l = w.lastRun;
  const same = (a: Record<string, RunState>, b: Record<string, RunState>) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every((k) => a[k] === b[k]);
  if (l && (states == null || same(states, l.states))) return { ...(l.counts ?? {}) };
  return G.runCounts(w, g, states ?? {});
}
/** The runs of this workflow that happened, latest first. */
export function history(id: string): HistoryRow[] {
  const w = workflow(id);
  if (!w) return [];
  return detailA(id).history;
}
/** Every kept version of this workflow, newest first (plan 6 C8). */
export const versions = (id: string): WfVersion[] => (workflow(id) ? detailA(id).versions ?? [] : []);
/** The version runs use, or null when the workflow is not published. */
export const publishedVersion = (id: string): string | null => (workflow(id) ? detailA(id).published_ver ?? null : null);
/** What changed from version a to version b (default: the current one), computed on the server. Suspends. */
export const compareVersions = (id: string, a: string, b?: string): VersionDiff =>
  cached<VersionDiff>('/api/screens/workflows/' + encodeURIComponent(id) + '/compare?a=' + encodeURIComponent(a) + (b ? '&b=' + encodeURIComponent(b) : ''));
/** The invalid rows of the latest run, with the field and the rule each broke. */
export const failedRows = (id: string): { rec: string; field: string; value: string; rule: string }[] => {
  const w = workflow(id);
  if (!w) return [];
  return detailA(id).failed_rows;
};
/** The figures of each history entry, in the history's order (empty entries when the server sends none). */
export const runFigures = (id: string): RunFigure[] => (workflow(id) ? detailA(id).run_figures ?? [] : []);
/** The latest real run's figures and held records, or null when the workflow has not really run. */
export const runQuality = (id: string): RunQuality | null => (workflow(id) ? detailA(id).quality ?? null : null);
/** The demo's estimate of errors in a seeded run row (one that never ran in the app): every row of a failed run,
 *  otherwise a fixed share. Real runs use runFigures. */
export function runErrors(id: string, r: HistoryRow): number {
  return r.state === 'failed' ? r.rows : Math.max(1, Math.round(r.rows * (0.004 + (parseInt(hashId(id + 'rej'), 16) % 9) / 1000)));
}

// ---- systems ----
export const sources = (): Source[] => sourcesA();
export const source = (id: string): Source => G.srcOr(srcL(), id);
export const sourceExists = (id: string): boolean => sourcesA().some((s) => s.id === id);
export const sourceLabel = (s: Source): string => G.srcLabel(srcL(), s);
export const sourceShortLabel = (id: string): string => G.srcShort(srcL(), id);
export const mapTarget = (id: string): string => G.srcTarget(srcLive(), id) ?? '';
export const mappings = (id: string | null): string[][] => (id ? mappingsA()[id] ?? [] : []);
/** DELIVER, with the sources made in the Connection Fabric that take instructions. */
export const deliverMap = (): Record<string, string[]> => {
  const made = srcLive().sources.filter((s) => s.deliver?.length).map((s) => [s.id, s.deliver!] as const);
  return made.length ? { ...ref('DELIVER'), ...Object.fromEntries(made) } : ref('DELIVER');
};
export const deliverOf = (id: string): string[] => G.srcDeliver(srcLive(), id);
export const channelsOf = (s: Source): string[] => G.srcCh(s);
export const CH = () => ({ arr: ref('CH_ARR'), ing: ref('CH_ING'), del: ref('CH_DEL') });
export const sourceCategoryLabel = (s: Source): string => ref('FR_CATOF')[s.type] ?? s.short ?? '';
export const usedBy = (srcId: string): string[] => sourcesA().find((s) => s.id === srcId)?.health?.workflows ?? [];

// ---- the vendor marks and icon tiles (drawn by src/pages/workflows/WorkflowMarks.tsx) ----
/** Whether a vendor shows its logo, when the app has one, rather than its initials (the demo's FEAT.logos). */
export const vendorLogos = (): boolean => !!ref('FEAT').logos;
/** A step's mark on the canvas: its system's vendor mark, or a tinted icon tile. */
export type NodeMark = { source: Source } | { ic: string; h: string };
const XF_IC: Record<string, string> = {
  x_gw: 'api', x_evt: 'stream', x_file: 'file', x_val: 'checks', x_utc: 'clock', x_fx: 'dollar', x_lookup: 'lookup', x_units: 'scale', x_ident: 'link',
  x_late: 'clock', x_env: 'shield', x_man: 'file', x_cb: 'download', x_notify: 'bell', x_trig: 'file', x_unzip: 'file', x_chunk: 'layers',
};
const FR_NIC: Record<string, string> = { conn: 'database', wconn: 'send', map: 'mapping', act: 'send', tool: 'bot' };
/** The step's mark on the canvas (the demo's frNodeIcon). */
export function nodeMark(n: WfNode): NodeMark {
  if (n.k === 'conn' || n.k === 'wconn') return { source: source(n.ref) };
  if (n.k === 'xf') {
    const x = frTransforms().find((y) => y.id === n.ref);
    return { ic: x?.ic ?? XF_IC[n.ref] ?? 'workflow', h: x?.sink ? (n.ref === 'x_err' ? 'alert' : 'agent') : 'insp' };
  }
  if (n.k === 'fixed') {
    const f = ref('FXD')[n.ref];
    return { ic: f.canon ? 'database' : n.ref === 'appr' ? 'user' : n.ref === 'gates' ? 'shield' : 'file', h: 'dec' };
  }
  return { ic: FR_NIC[n.k] ?? 'workflow', h: n.k === 'map' ? 'money' : 'agent' };
}

// ---- step catalogue (palette and inspector) ----
export interface Xf { id: string; label: string; sub: string; desc: string; group?: string; ingest?: string; ic?: string; start?: boolean; sink?: boolean }
/** The tiles of blocks the demo has none for (plan 8: Open case), from the block catalogue; none for an account that
 *  cannot read it (it cannot open the Studio either). */
function extraTransforms(): Xf[] {
  try {
    return blocksA().palette ?? [];
  } catch (x) {
    if (x instanceof ApiError) return [];
    throw x;
  }
}
export const transforms = (): Xf[] => [...ref('XF'), ...extraTransforms()];
export const frTransforms = (): Xf[] => [...ref('FR_XF'), ...extraTransforms()];
export const actTypes = (): { id: string; ch: string; label: string; sub: string; desc: string }[] => ref('ACT_TYPES');
export const tools = (): { id: string; rw: 'read' | 'write'; approval: string; desc: string }[] => ref('TOOLS');
function agents(): { name: string; tools: string[] }[] {
  try {
    return cached<{ agents: { name: string; tools: string[] }[] }>('/api/screens/mcp/agents').agents;
  } catch (x) {
    if (x instanceof ApiError) return []; // an account without the MCP agents page sees no agent names
    throw x;
  }
}
export const agentsUsing = (tool: string): string[] => agents().filter((a) => a.tools.includes(tool)).map((a) => a.name);
export const fixedStep = (id: string): { label: string; fields?: string[]; canon?: boolean } => ref('FXD')[id];
export const sourceGroups = (): [string, string[], string][] => ref('FR_SRCG');

// ---- block settings (GET /api/screens/workflows/blocks; di/workflow/blocks.py) ----
const blocksA = () => cached<BlocksAnswer>('/api/screens/workflows/blocks');
/** Every palette block's settings: its fields with their types, defaults and choices, keyed by spec key (an xf node's
 *  transform id, else the node kind: conn, wconn, map, act, fixed, tool). */
export function blockSpecs(): Record<string, BlockSpec> {
  return Object.fromEntries(blocksA().blocks.map((b) => [b.ref, b]));
}
/** The resources each connection reads (the choices of a connector's Resources setting). */
export const blockResources = (): Record<string, string[]> => blocksA().resources ?? {};
/** Each target system's writes (the choices of a write connector's Target operation; a target not listed takes none). */
export const blockOperations = (): Record<string, string[]> => blocksA().operations ?? {};
/** The catalogue for the checks; an account that cannot read it gets the checks without settings. */
function blocksL(): Pick<G.Lookups, 'blocks' | 'resources' | 'operations'> {
  try {
    return { blocks: blockSpecs(), resources: blockResources(), operations: blockOperations() };
  } catch (x) {
    if (x instanceof ApiError) return {};
    throw x;
  }
}
/** A node's block spec (null for a block the catalogue does not know). */
export const blockSpecOf = (n: WfNode): BlockSpec | null => blockSpecs()[G.specKey(n)] ?? null;
/** A node's settings with the defaults filled in. */
export const nodeSettings = (n: WfNode): Record<string, unknown> => G.nodeCfg(blockSpecs(), n);
/** One setting's problems, for the inspector (the same rule as the checks). */
export const settingErrors = (f: FieldSpec, v: unknown, n: WfNode): string[] =>
  G.fieldErrors(f, v, { resources: n.k === 'conn' ? blockResources()[n.ref] ?? null : null, operations: n.k === 'wconn' ? blockOperations()[n.ref] ?? [] : null });

// ---- changes (invoke) ----
/** Save the draft; `retries` and `alert` are the Settings tab's run settings (frWfSet), saved with the workflow. */
export const saveWorkflow = (i: { id: string; name: string; owner: string; trig: Trigger; graph: WfGraph; note?: string; retries?: number; alert?: string }) =>
  invoke<{ id: string; ver: string; name: string }>('workflow.save', i);
/** Save as template (frWfTpl): one per workflow; it appears under New workflow. */
export const saveAsTemplate = (id: string) => invoke<{ id: string; name: string; from: string }>('workflow.saveTemplate', { id });
/** A new draft from a saved template (frTplUse). */
export const createFromTemplate = (tpl: string) => invoke<{ id: string; name: string }>('workflow.create', { type: 'template', tpl });
/** Send the latest run's held records back through validation (frReproc). */
export const reprocessFailed = (id: string) =>
  invoke<{ id: string; name: string; n: number; reprocessed: number; held: number }>('workflow.reprocess', { id });
/** Apply the investigation's suggested fix (frFixApply). */
export const applySuggestedFix = (id: string) => invoke<{ id: string; name: string; ver: string; fix: string }>('workflow.applyFix', { id });
/** Put an earlier version's graph and settings back as a new version (workflow.restore). */
export const restoreVersion = (id: string, ver: string) =>
  invoke<{ id: string; name: string; ver: string; from: string }>('workflow.restore', { id, ver });
export const publishWorkflow = (id: string, graph?: WfGraph) =>
  invoke<{ id: string; ver: string; name: string; trig: string }>('workflow.publish', graph ? { id, graph } : { id });
export const setWorkflowStatus = (id: string, status: WfStatus) =>
  invoke<{ id: string; was: WfStatus; status: WfStatus; name: string }>('workflow.setStatus', { id, status });
export const createWorkflow = (i: { type: string; src?: string; ch?: string; name?: string; graph?: WfGraph; desc?: string }) =>
  invoke<{ id: string; name: string }>('workflow.create', i);
export const duplicateWorkflow = (id: string) => invoke<{ id: string; name: string }>('workflow.duplicate', { id });
/** A new draft from the JSON Export JSON wrote (workflow.import, plan 6 C10); a refusal lists every problem in `error.problems` (P9-0.7). */
export const importWorkflow = (data: unknown) => invoke<{ id: string; name: string }>('workflow.import', { data });
/** The signed-in person's working copy kept on the server, read when the workflow opens (plan 6 C9). Suspends. */
export const serverDraftOf = (id: string): ServerDraft | null => (workflow(id) ? detailA(id).draft ?? null : null);
/** Autosave the working copy (workflow.draft.save); the canvas calls it after two seconds of quiet. */
export const saveDraft = (d: { id: string } & ServerDraft) => invoke<{ id: string; at: string }>('workflow.draft.save', { ...d });
/** Test run (workflow.testRun): a dry run of the draft's graph on the server over a sample of real records, writing
 *  nothing. It stops at Human approval ("held") unless `approved`. */
export const testRunWorkflow = (id: string, graph: WfGraph, approved = false, sample?: number) =>
  invoke<TestRunResult>('workflow.testRun', { id, graph, ...(approved ? { approved } : {}), ...(sample ? { sample } : {}) });
/** Drop the working copy kept on the server (after Save, Publish or Discard). */
export const discardDraft = (id: string) => invoke<{ id: string; discarded: boolean }>('workflow.draft.discard', { id });
export const deleteWorkflow = (id: string) => invoke<{ id: string; name: string }>('workflow.delete', { id });
/** Start a run. It returns at once with the run key (`run`); follow it with followRun. */
export const runWorkflow = (id: string): Promise<ActionResult<{ id: string; name: string; run?: string }>> =>
  invoke<{ id: string; name: string; run?: string }>('workflow.run', { id });

const exportFile = (w: Workflow, o: unknown) => ({ file: w.id + '-' + w.name.replace(/[^A-Za-z0-9]+/g, '-').toLowerCase() + '.json', json: JSON.stringify(o, null, 2) });
/** The JSON export (frWfJSON) of the saved workflow. */
export async function exportJson(id: string): Promise<{ file: string; json: string } | null> {
  return settle(() => {
    const w = workflow(id);
    if (!w) return null;
    const g = detailA(id).workflow.graph, L = lk();
    return exportFile(w, {
      id: w.id, name: w.name, version: w.ver, type: w.cat, status: w.status, owner: w.owner, trigger: w.trig,
      source: w.src ? G.srcOr(L, w.src).vendor : null, source_id: w.src, description: w.desc,
      // `cfg`: the block settings that differ from the defaults, so Import (workflow.import) recreates them
      steps: g.nodes.map((n) => ({ id: n.id, kind: n.k, ref: n.ref, label: G.info(L, n).label, x: n.x, y: n.y, ...(n.cfg ? { cfg: n.cfg } : {}) })),
      links: g.edges.map((x) => ({ from: x.a, to: x.b, fixed: !!x.locked })),
      exported_by: session()?.account.label ?? '', exported_at: new Date(nowMs()).toISOString(),
    });
  });
}
/** New workflow form: systems that can be read (ingest) or written (outbound). */
export const readableSources = (): Source[] => sources().filter((s) => s.read.length || s.status === 'unavailable');
export const writableSources = (): Source[] => sources().filter((s) => s.write.length);

// ---- small view helpers from the demo ----
/** The edge path between two points (wfPathXY): a curve forward, a rounded detour backward. */
export const edgePath = (sx: number, sy: number, tx: number, ty: number): string => G.pathXY(sx, sy, tx, ty);
/** Status pill label and colour class (FR_ST), e.g. failing → ['Failing', 'bad']. */
export const statusPill = (k: string): [string, string] => ref('FR_ST')[k] ?? [k, 'line'];
/** The workflow's source system, or null for a decision workflow. */
export const systemOf = (w: Workflow): Source | null => (w.src ? source(w.src) : null);
