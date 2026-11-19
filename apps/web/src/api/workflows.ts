/**
 * Workflow Studio: typed reads over the engine's workflow list (S.wf), the step catalogue (XF, FXD, ACT_TYPES, TOOLS),
 * the workflow checks (wfValidate) and the run simulation (wfEval). Changes go through invoke() with the demo's
 * action ids: workflow.save, workflow.publish, workflow.setStatus, workflow.create, workflow.duplicate,
 * workflow.delete, workflow.run (and workflow.validate as a read).
 *
 * The canvas edits a copy of the graph held by the page (src/pages/workflows/draft.ts); nothing here mutates the
 * engine's workflow objects except the small view flags the demo keeps on them (fix applied, reprocessed, settings).
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bump, engine } from '../engine/engine';
import { invoke, read } from './actions';
import type { ActionResult } from './types';

const e = () => engine();

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

// ---- the list ----
export function workflows(): Workflow[] {
  e()('wfInit')();
  return e()<{ list: Workflow[] }>('S.wf').list;
}
export const workflow = (id: string): Workflow | undefined => workflows().find((w) => w.id === id);
export const recentRuns = (): RunRow[] => (workflows(), e()<{ runs: RunRow[] }>('S.wf').runs);
export const wfStat = (w: Workflow): WfStat => e()<(w: Workflow) => WfStat>('wfStat')(w);
export const trigText = (t: Trigger): string => e()<(t: Trigger) => string>('trigText')(t);
export const ageShort = (ms: number): string => e()<(ms: number) => string>('ageShort')(ms);
/** "4 min ago" */
export const ago = (ms: number): string => e()<(ms: number) => string>('frAgo')(ms);
export const RUN_LABEL = (): Record<string, string> => e()('WF_STL');
export const RUN_CHIP = (): Record<string, string> => e()('WF_STC');
export const NOWF = (): string => e()('NOWF');

/** The agent panel and search read the open workflow from the engine (S.wf.cur). */
export function setOpenWorkflow(id: string | null): void {
  workflows();
  const S = e()<{ wf: { cur: Workflow | null; kind: string } }>('S');
  const w = id ? workflow(id) ?? null : null;
  S.wf.cur = w;
  if (w) S.wf.kind = w.kind;
}

/** Items that need attention in the right column: failing workflows, expired credentials, high failure rates. */
export const attention = (): { ic: string; h: string; t: string; s: string; arg: string; go?: string }[] => e()('frWfAttn')();

// ---- graphs ----
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
export const WF_W = 176, WF_H = 62, WF_WH = 640;
export const worldWidth = (kind: 'pipe' | 'dec'): number => (kind === 'pipe' ? 1680 : 1240);

/** A copy of the workflow's current graph (built from its template on first use). */
export function graphOf(id: string): WfGraph {
  const w = workflow(id);
  return w ? clone(e()<(w: Workflow) => WfGraph>('wfGraphOf')(w)) : { nodes: [], edges: [] };
}
/** The last saved version, for Discard. */
export function savedOf(id: string): { graph: WfGraph; name: string; owner: string; trig: Trigger } | null {
  const w = workflow(id) as (Workflow & { saved?: string | null }) | undefined;
  if (!w?.saved) return null;
  const o = JSON.parse(w.saved);
  return { graph: o.g, name: o.m.name, owner: o.m.owner, trig: o.m.trig };
}
/** A fresh graph from the workflow's template, for Reset to template. */
export function templateOf(id: string): WfGraph {
  const w = workflow(id) as (Workflow & { tpl: unknown }) | undefined;
  return w ? clone(e()<(t: unknown) => WfGraph>('wfBuild')(w.tpl)) : { nodes: [], edges: [] };
}
export const stepInfo = (n: WfNode): StepInfo => e()<(n: WfNode) => StepInfo>('wfInfo')(n);
/** Errors, warnings and notes, each with the step it belongs to (sorted errors first). */
export const validate = (g: WfGraph, kind: 'pipe' | 'dec'): Check[] => e()<(g: WfGraph, k: string) => Check[]>('wfValidate')(g, kind);
/** null when a → b may be connected, otherwise the reason it may not. */
export const canLink = (g: WfGraph, a: string, b: string): string | null => e()<(g: WfGraph, a: string, b: string) => string | null>('wfCanLink')(g, a, b);
export const runOrder = (g: WfGraph): string[] => e()<(g: WfGraph) => string[]>('wfOrder')(g);
export function analyze(g: WfGraph): { pred: Record<string, string[]>; succ: Record<string, string[]>; desc: (id: string) => Set<string> } {
  return e()('wfAnalyze')(g);
}
/** The state a step reaches in a test run, given the states of the steps before it. */
export function evalStep(run: TestRun, g: WfGraph, n: WfNode): RunState {
  return e()('wfEval')(run, analyze(g), n);
}
/** The last real run, painted on the canvas when the workflow opens. */
export const runFromLast = (id: string): TestRun | null => { const w = workflow(id); return w ? e()('wfRunFromLast')(w) : null; };
export const runTimes = (r: TestRun): Record<string, { s: number; e: number; d: number; ex: boolean }> => e()('wfRunTimes')(r);
export const hashId = (s: string): string => e()<(s: string) => string>('hashId')(s);

/** Records in and out of each step, from the given run states (or the last run). */
export function runCounts(id: string, g: WfGraph, states: Record<string, RunState> | null): Record<string, Counts> {
  const w = workflow(id);
  if (!w) return {};
  const lr = states ? { ...(w.lastRun ?? {}), states } : w.lastRun;
  return e()('frRunCounts')({ ...w, graph: g, lastRun: lr });
}
/** Every run of this workflow, latest first (real runs, then earlier ones derived from its counts). */
export const history = (id: string): HistoryRow[] => { const w = workflow(id); return w ? e()('frWfHistory')(w) : []; };
/** The invalid rows of the latest run, with the field and the rule each broke. */
export const failedRows = (id: string): { rec: string; field: string; value: string; rule: string }[] => {
  const w = workflow(id);
  return w ? e()('frFailedRows')(w) : [];
};
/** Errors in a run row: every row of a failed run, otherwise the fixed share validation rejects. */
export function runErrors(id: string, r: HistoryRow): number {
  return r.state === 'failed' ? r.rows : Math.max(1, Math.round(r.rows * (0.004 + (parseInt(hashId(id + 'rej'), 16) % 9) / 1000)));
}

// ---- systems ----
export const sources = (): Source[] => e()('SOURCES');
export const source = (id: string): Source => e()<(id: string) => Source>('srcOr')(id);
export const sourceExists = (id: string): boolean => !!e()<(id: string) => Source | undefined>('SRC')(id);
export const sourceLabel = (s: Source): string => e()<(s: Source) => string>('srcLabel')(s);
export const sourceShortLabel = (id: string): string => e()<Record<string, string>>('SH')[id] ?? id;
export const mapTarget = (id: string): string => e()<Record<string, string>>('MAP_TARGET')[id] ?? '';
export const mappings = (id: string | null): string[][] => (id ? e()<Record<string, string[][]>>('MAPPINGS')[id] ?? [] : []);
export const deliverOf = (id: string): string[] => e()<Record<string, string[]>>('DELIVER')[id] ?? [];
export const deliverMap = (): Record<string, string[]> => e()('DELIVER');
export const channelsOf = (s: Source): string[] => e()<(s: Source) => string[]>('srcCh')(s);
export const CH = () => ({ arr: e()<Record<string, string>>('CH_ARR'), ing: e()<Record<string, string>>('CH_ING'), del: e()<Record<string, string>>('CH_DEL') });
export const sourceCategoryLabel = (s: Source): string => e()<Record<string, string>>('FR_CATOF')[s.type] ?? s.short ?? '';
export const usedBy = (srcId: string): string[] => e()<(id: string) => string[]>('wfUsing')(srcId);
/** The demo's vendor mark (an inline SVG or initials badge) as trusted markup. */
export const logoHtml = (s: Source): string => e()<(s: Source) => string>('vlogo')(s);
/** The step's icon tile on the canvas (vendor mark or tinted icon), as trusted markup. */
export const nodeIconHtml = (n: WfNode): string => e()<(n: WfNode) => string>('frNodeIcon')(n);
/** Tinted icon tile (frIt). */
export const iconTileHtml = (ic: string, h: string, cls = ''): string => e()<(a: string, b: string, c: string) => string>('frIt')(ic, h, cls);
/** The source status chip (stChip). */
export const statusChipHtml = (st: string): string => e()<(s: string) => string>('stChip')(st) ?? '';

// ---- step catalogue (palette and inspector) ----
export interface Xf { id: string; label: string; sub: string; desc: string; group?: string; ingest?: string; ic?: string; start?: boolean; sink?: boolean }
export const transforms = (): Xf[] => e()('XF');
export const frTransforms = (): Xf[] => e()('FR_XF');
export const actTypes = (): { id: string; ch: string; label: string; sub: string; desc: string }[] => e()('ACT_TYPES');
export const tools = (): { id: string; rw: 'read' | 'write'; approval: string; desc: string }[] => e()('TOOLS');
export const agentsUsing = (tool: string): string[] =>
  e()<{ name: string; tools: string[] }[]>('AGENTS').filter((a) => a.tools.includes(tool)).map((a) => a.name);
export const fixedStep = (ref: string): { label: string; fields?: string[]; canon?: boolean } => e()<Record<string, any>>('FXD')[ref];
export const sourceGroups = (): [string, string[], string][] => e()('FR_SRCG');
export const sourceCats = (): Record<string, string> => e()('SRC_CATS');

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
export const runWorkflow = (id: string): ActionResult<{ id: string; name: string }> => invoke('workflow.run', { id });
/** The checks on the saved graph, through the read action the agent uses. */
export const validateSaved = (id: string) =>
  read<{ id: string; name: string; errors: { msg: string }[]; warnings: { msg: string }[] }>('workflow.validate', { id });

// ---- view flags the demo keeps on the workflow (not journaled actions in the demo either) ----
function logEvent(type: string, note: string) {
  try { e()('rbLog')(type, note); } catch { /* the audit stream is best effort */ }
}
/** The JSON export (frWfJSON) of the saved workflow. */
export function exportJson(id: string): { file: string; json: string } | null {
  const w = workflow(id);
  if (!w) return null;
  const o = e()('frWfJSON')(w);
  logEvent('workflow.exported', w.id + ' · ' + w.name);
  return { file: w.id + '-' + w.name.replace(/[^A-Za-z0-9]+/g, '-').toLowerCase() + '.json', json: JSON.stringify(o, null, 2) };
}
export interface Template { id: string; from: string; name: string; tpl: WfGraph; cat: string; kind: string; src: string | null; owner: string; trig: Trigger }
export const templates = (): Template[] => e()<{ frTpl?: Template[] }>('S').frTpl ?? [];
export function saveAsTemplate(id: string): void {
  const S = e()<{ frTpl?: Template[] }>('S');
  const w = workflow(id);
  if (!w) return;
  const L = (S.frTpl ??= []);
  if (!L.some((t) => t.from === w.id))
    L.push({ id: 'TPL-' + (L.length + 1), from: w.id, name: w.name + ' template', tpl: graphOf(id), cat: w.cat, kind: w.kind, src: w.src, owner: w.owner, trig: { ...w.trig } });
  logEvent('workflow.template.saved', w.id + ' · ' + w.name);
  bump();
}
export function applySuggestedFix(id: string): void {
  const w = workflow(id);
  if (!w) return;
  const f = mappings(w.src)[0];
  w.frFix = f ? 'The renamed source field now maps to ' + f[2] + ' again (mapping kept as a new version).' : 'The step is reset to its last good configuration.';
  logEvent('workflow.fixed', w.id + ' · ' + w.frFix);
  bump();
}
export function reprocessFailed(id: string): number {
  const w = workflow(id);
  if (!w) return 0;
  const n = failedRows(id).length;
  w.frReproc = n + ' records at ' + new Date().toTimeString().slice(0, 5);
  logEvent('workflow.reprocessed', w.id + ' · ' + n + ' held records sent back through validation');
  bump();
  return n;
}
export function setRunSetting(id: string, k: 'retries' | 'alert', v: string): void {
  const w = workflow(id);
  if (!w) return;
  if (k === 'retries') w.retries = +v;
  else w.alert = v;
  bump();
}
/** The engine's source completeness for the data quality meters. */
export const sourceCompleteness = (id: string | null): number | null => {
  const s = id ? e()<(id: string) => { compl?: number } | undefined>('SRC')(id) : undefined;
  return s ? s.compl ?? 95 : null;
};
/** New workflow form: systems that can be read (ingest) or written (outbound). */
export const readableSources = (): Source[] => sources().filter((s) => s.read.length || s.status === 'unavailable');
export const writableSources = (): Source[] => sources().filter((s) => s.write.length);

// ---- small view helpers from the demo ----
/** The edge path between two points (wfPathXY): a curve forward, a rounded detour backward. */
export const edgePath = (sx: number, sy: number, tx: number, ty: number): string =>
  e()<(a: number, b: number, c: number, d: number) => string>('wfPathXY')(sx, sy, tx, ty);
/** Status pill label and colour class (FR_ST), e.g. failing → ['Failing', 'bad']. */
export const statusPill = (k: string): [string, string] => e()<Record<string, [string, string]>>('FR_ST')[k] ?? [k, 'line'];
/** The workflow's source system, or null for a decision workflow. */
export const systemOf = (w: Workflow): Source | null => (w.src ? source(w.src) : null);
