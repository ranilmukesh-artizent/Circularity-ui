/**
 * Workflow Studio: typed reads over the workflow list, the step catalogue (XF, FXD, ACT_TYPES, TOOLS), the workflow
 * checks and the run simulation. Changes go through invoke() with the demo's action ids: workflow.save,
 * workflow.publish, workflow.setStatus, workflow.create, workflow.duplicate, workflow.delete, workflow.run (and
 * workflow.validate as a read).
 *
 * apps/api/di/screens/workflows.py has the mapping, export by export:
 * - the list, the recent runs and the attention list: GET /api/screens/workflows; one workflow's graph, saved
 *   version, template, history and failed records: GET /api/screens/workflows/{id};
 * - sources: GET /api/screens/integration/sources; field mappings: GET /api/screens/integration/models; the agents
 *   (agentsUsing): GET /api/screens/mcp/agents; the static lists: ref();
 * - the canvas checks and the test-run simulation run in the browser on the unsaved draft (src/api/workflowGraph.ts);
 * - a run is followed on the stream (kind `workflow`) by the run key workflow.run returns.
 *
 * The canvas edits a copy of the graph held by the page (src/pages/workflows/draftStore.ts).
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import * as G from './workflowGraph';
import { invoke } from './actions';
import { ApiError, cached, onStream, ref, session } from './client';
import type { ActionResult } from './types';

export type StepKind = 'fixed' | 'conn' | 'wconn' | 'act' | 'xf' | 'map' | 'tool';
export interface WfNode { id: string; k: StepKind; ref: string; x: number; y: number; fail?: boolean; ai?: number }
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
  lastRun?: { id: string; ts: number; t0: number; trig: string; states: Record<string, RunState>; dur: Record<string, number>; order: string[]; status: string; note: string };
  frFix?: string; frReproc?: string; retries?: number; alert?: string; aiNote?: string;
}
export interface RunRow { id: string; wf: string; name: string; ts: number; trig: string; dur: number; rows: number; state: RunState; note: string }
export interface HistoryRow { id: string; ts: number; state: RunState; dur: number; rows: number; trig: string; note: string }
export interface Check { sev: 'error' | 'warn' | 'info'; id: string; msg: string }
export interface StepInfo { label: string; sub: string; tag: string; in: boolean; out: boolean; desc: string }
export interface Source {
  id: string; name: string; vendor: string; short?: string; status: 'live' | 'stale' | 'manual' | 'unavailable'; mode: string; auth: string;
  read: string[]; write: string[]; cat: string; fresh: string; owner: string; type: string; url?: string; paused?: boolean; deleted?: boolean;
}
/** A test run on the canvas (the demo's S.wf.run). */
export interface TestRun {
  status: 'running' | 'held' | 'failed' | 'success'; warn?: boolean; states: Record<string, RunState>; dur: Record<string, number | string>;
  order: string[]; i: number; approved: boolean; t0: number; id: string; trig: string;
}
export interface Counts { in: number; out: number; rej: number }
type Attention = { ic: string; h: string; t: string; s: string; arg: string; go?: string };

// ---------------------------------------------------------------- the API answers
interface ListAnswer { workflows: Workflow[]; runs: RunRow[]; attention: Attention[]; now?: number }
interface Detail {
  workflow: Workflow & { graph: WfGraph };
  saved: { graph: WfGraph; name: string; owner: string; trig: Trigger } | null;
  template: WfGraph | null;
  history: HistoryRow[];
  failed_rows: { rec: string; field: string; value: string; rule: string }[];
}
type ApiSource = Source & { compl?: number; health?: { workflows?: string[] } };

const listA = () => cached<ListAnswer>('/api/screens/workflows');
const detailA = (id: string) => cached<Detail>('/api/screens/workflows/' + encodeURIComponent(id));
const sourcesA = () => cached<{ sources: ApiSource[] }>('/api/screens/integration/sources').sources;
const mappingsA = () => cached<{ mappings: Record<string, string[][]> }>('/api/screens/integration/models').mappings;

/** The reference lists and sources the ported graph logic reads. */
function lk(): G.Lookups {
  return {
    sources: sourcesA(), mappings: mappingsA(), XF: ref('XF'), FR_XF: ref('FR_XF'), FXD: ref('FXD'), ACT_TYPES: ref('ACT_TYPES'), TOOLS: ref('TOOLS'),
    MAP_TARGET: ref('MAP_TARGET'), SH: ref('SH'), DELIVER: ref('DELIVER'), CH_ARR: ref('CH_ARR'), CH_DEL: ref('CH_DEL'),
  };
}

/** Enough of the lookups for the source helpers (srcOr, srcLabel), without the field mappings. */
const srcL = () => ({ sources: sourcesA(), SH: ref('SH') }) as unknown as G.Lookups;

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
  return a.now != null ? a.now + (Date.now() - seenAt.get(a)!) : Date.parse(ref<string>('AS_OF')) + (Date.now() - T0);
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
export function savedOf(id: string): { graph: WfGraph; name: string; owner: string; trig: Trigger } | null {
  return workflow(id) ? clone(detailA(id).saved) : null;
}
/** A fresh graph from the workflow's template, for Reset to template. */
export function templateOf(id: string): WfGraph {
  return (workflow(id) && clone(detailA(id).template)) || { nodes: [], edges: [] };
}
export const stepInfo = (n: WfNode): StepInfo => G.info(lk(), n);
/** Errors, warnings and notes, each with the step it belongs to (sorted errors first). */
export const validate = (g: WfGraph, kind: 'pipe' | 'dec'): Check[] => G.validate(lk(), g, kind);
/** null when a → b may be connected, otherwise the reason it may not. */
export const canLink = (g: WfGraph, a: string, b: string): string | null => G.canLink(lk(), g, a, b);
export const runOrder = (g: WfGraph): string[] => G.order(g);
export function analyze(g: WfGraph): { pred: Record<string, string[]>; succ: Record<string, string[]>; desc: (id: string) => Set<string> } {
  return G.analyze(g);
}
/** The state a step reaches in a test run, given the states of the steps before it. */
export function evalStep(run: TestRun, g: WfGraph, n: WfNode): RunState {
  return G.evalStep(lk(), run, G.analyze(g), n);
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
  };
}
export const runTimes = (r: TestRun): Record<string, { s: number; e: number; d: number; ex: boolean }> => G.runTimes(r, nowMs());
export const hashId = (s: string): string => G.hashId(s);

/** Records in and out of each step, from the given run states (or the last run). */
export function runCounts(id: string, g: WfGraph, states: Record<string, RunState> | null): Record<string, Counts> {
  const w = workflow(id);
  if (!w) return {};
  return G.runCounts(w, g, states ?? w.lastRun?.states ?? {});
}
/** Every run of this workflow, latest first (real runs, then earlier ones derived from its counts). */
export function history(id: string): HistoryRow[] {
  const w = workflow(id);
  if (!w) return [];
  return detailA(id).history;
}
/** The invalid rows of the latest run, with the field and the rule each broke. */
export const failedRows = (id: string): { rec: string; field: string; value: string; rule: string }[] => {
  const w = workflow(id);
  if (!w) return [];
  return detailA(id).failed_rows;
};
/** Errors in a run row: every row of a failed run, otherwise the fixed share validation rejects. */
export function runErrors(id: string, r: HistoryRow): number {
  return r.state === 'failed' ? r.rows : Math.max(1, Math.round(r.rows * (0.004 + (parseInt(hashId(id + 'rej'), 16) % 9) / 1000)));
}

// ---- systems ----
export const sources = (): Source[] => sourcesA();
export const source = (id: string): Source => G.srcOr(srcL(), id);
export const sourceExists = (id: string): boolean => sourcesA().some((s) => s.id === id);
export const sourceLabel = (s: Source): string => G.srcLabel(srcL(), s);
export const sourceShortLabel = (id: string): string => ref<Record<string, string>>('SH')[id] ?? id;
export const mapTarget = (id: string): string => ref<Record<string, string>>('MAP_TARGET')[id] ?? '';
export const mappings = (id: string | null): string[][] => (id ? mappingsA()[id] ?? [] : []);
export const deliverMap = (): Record<string, string[]> => ref('DELIVER');
export const deliverOf = (id: string): string[] => deliverMap()[id] ?? [];
export const channelsOf = (s: Source): string[] => G.srcCh(s);
export const CH = () => ({ arr: ref<Record<string, string>>('CH_ARR'), ing: ref<Record<string, string>>('CH_ING'), del: ref<Record<string, string>>('CH_DEL') });
export const sourceCategoryLabel = (s: Source): string => ref<Record<string, string>>('FR_CATOF')[s.type] ?? s.short ?? '';
export const usedBy = (srcId: string): string[] => sourcesA().find((s) => s.id === srcId)?.health?.workflows ?? [];

// ---- the vendor marks and icon tiles (drawn by src/pages/workflows/WorkflowMarks.tsx) ----
/** Whether a vendor shows its logo, when the app has one, rather than its initials (the demo's FEAT.logos). */
export const vendorLogos = (): boolean => !!ref<Record<string, boolean>>('FEAT').logos;
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
    const x = ref<Xf[]>('FR_XF').find((y) => y.id === n.ref);
    return { ic: x?.ic ?? XF_IC[n.ref] ?? 'workflow', h: x?.sink ? (n.ref === 'x_err' ? 'alert' : 'agent') : 'insp' };
  }
  if (n.k === 'fixed') {
    const f = ref<Record<string, G.Fixed>>('FXD')[n.ref];
    return { ic: f.canon ? 'database' : n.ref === 'appr' ? 'user' : n.ref === 'gates' ? 'shield' : 'file', h: 'dec' };
  }
  return { ic: FR_NIC[n.k] ?? 'workflow', h: n.k === 'map' ? 'money' : 'agent' };
}

// ---- step catalogue (palette and inspector) ----
export interface Xf { id: string; label: string; sub: string; desc: string; group?: string; ingest?: string; ic?: string; start?: boolean; sink?: boolean }
const list = <T,>(n: string): T => ref<T>(n);
export const transforms = (): Xf[] => list('XF');
export const frTransforms = (): Xf[] => list('FR_XF');
export const actTypes = (): { id: string; ch: string; label: string; sub: string; desc: string }[] => list('ACT_TYPES');
export const tools = (): { id: string; rw: 'read' | 'write'; approval: string; desc: string }[] => list('TOOLS');
function agents(): { name: string; tools: string[] }[] {
  try {
    return cached<{ agents: { name: string; tools: string[] }[] }>('/api/screens/mcp/agents').agents;
  } catch (x) {
    if (x instanceof ApiError) return []; // an account without the MCP agents page sees no agent names
    throw x;
  }
}
export const agentsUsing = (tool: string): string[] => agents().filter((a) => a.tools.includes(tool)).map((a) => a.name);
export const fixedStep = (ref: string): { label: string; fields?: string[]; canon?: boolean } => list<Record<string, any>>('FXD')[ref];
export const sourceGroups = (): [string, string[], string][] => list('FR_SRCG');

// ---- changes (invoke) ----
export const saveWorkflow = (i: { id: string; name: string; owner: string; trig: Trigger; graph: WfGraph; note?: string }) =>
  invoke<{ id: string; ver: string; name: string }>('workflow.save', i);
export const publishWorkflow = (id: string, graph?: WfGraph) =>
  invoke<{ id: string; ver: string; name: string; trig: string }>('workflow.publish', graph ? { id, graph } : { id });
export const setWorkflowStatus = (id: string, status: WfStatus) =>
  invoke<{ id: string; was: WfStatus; status: WfStatus; name: string }>('workflow.setStatus', { id, status });
export const createWorkflow = (i: { type: string; src?: string; ch?: string; name?: string; graph?: WfGraph; desc?: string }) =>
  invoke<{ id: string; name: string }>('workflow.create', i);
export const duplicateWorkflow = (id: string) => invoke<{ id: string; name: string }>('workflow.duplicate', { id });
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
      source: w.src ? G.srcOr(L, w.src).vendor : null, description: w.desc,
      steps: g.nodes.map((n) => ({ id: n.id, kind: n.k, ref: n.ref, label: G.info(L, n).label, x: n.x, y: n.y })),
      links: g.edges.map((x) => ({ from: x.a, to: x.b, fixed: !!x.locked })),
      exported_by: session()?.account.label ?? '', exported_at: new Date(nowMs()).toISOString(),
    });
  });
}
/** The source completeness for the data quality meters. */
export const sourceCompleteness = (id: string | null): number | null => {
  const s = id ? sourcesA().find((x) => x.id === id) : undefined;
  return s ? s.compl ?? 95 : null;
};
/** New workflow form: systems that can be read (ingest) or written (outbound). */
export const readableSources = (): Source[] => sources().filter((s) => s.read.length || s.status === 'unavailable');
export const writableSources = (): Source[] => sources().filter((s) => s.write.length);

// ---- small view helpers from the demo ----
/** The edge path between two points (wfPathXY): a curve forward, a rounded detour backward. */
export const edgePath = (sx: number, sy: number, tx: number, ty: number): string => G.pathXY(sx, sy, tx, ty);
/** Status pill label and colour class (FR_ST), e.g. failing → ['Failing', 'bad']. */
export const statusPill = (k: string): [string, string] => list<Record<string, [string, string]>>('FR_ST')[k] ?? [k, 'line'];
/** The workflow's source system, or null for a decision workflow. */
export const systemOf = (w: Workflow): Source | null => (w.src ? source(w.src) : null);
