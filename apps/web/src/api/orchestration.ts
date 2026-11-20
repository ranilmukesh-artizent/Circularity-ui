/**
 * Process orchestration (#/orchestration): the case run (ten stages, their activity lines and timing), the run trace,
 * run details and the agents and services. The live board's playback is view state and lives in the page.
 */
import { engine } from '../engine/engine';
import { invoke } from './actions';
import type { ActionResult } from './types';

const e = () => engine();

export interface OrCase { id: string; product: string; owner: string; stage: string; approval?: { ref: string; by: string } | null; submitted?: { by: string } | null;
  exec?: { steps: { label: string; state: string }[] } | null; outcome?: { net: number } | null }
export interface RunLine {
  agent: string | null; who: string; tool: string | null; sys: string; verb: string; what: string; ms: number; audit: string[];
  st: 'done' | 'queued' | 'wait' | 'fail'; model: string | null;
}
export interface RunStage { n: number; t: string; state: string; result: string; by: string; at: string | Date | null; lines: RunLine[] }
export interface RunModel { run: { id: string; stage: number; stages: { n: number; t: string; state: string; by?: string; at?: string | Date | null; result?: string }[] }; st: RunStage[]; cur: number }
export interface Segment { n: number; start: number; end: number; lines: { start: number; land: number }[] }
export interface NextStep { kind: 'act' | 'approve' | 'ack' | 'wait' | 'blocked' | 'done'; n: number; label: string; role?: string }
export interface ModelCard { key: string; version: string; kind: 'ML' | 'DL'; algo: string; task: string; validation: string; data: string }
export interface JournalEntry { id: string; by: string; prep?: string | null; input: Record<string, unknown>; out?: Record<string, unknown> | null; at: string | Date; run?: string }
export interface AgentCall { run: string; action: string; input: string; msg: string; badge: string; ok: boolean; code?: string; ms: number }
export interface RunEvent { id: string; ts: string | Date; type: string; note?: string; ack?: string }
export interface AgentInfo { id: string; name: string; step: string; scopes: string[]; limit: string }

type Raw = any; // eslint-disable-line @typescript-eslint/no-explicit-any

export const orCases = (): OrCase[] => e()<() => OrCase[]>('orCases')();
/** The case shown: the one picked earlier, else RT-1048, else the first in scope. */
export const orCase = (): OrCase | undefined => e()<() => OrCase | undefined>('orCase')();
const caseById = (id: string): Raw => e()<Record<string, Raw>>('CASE_BY_ID')[id];
export const orCaseById = (id: string): OrCase | undefined => caseById(id);
/** Remember the case picked on this page (the demo's S.or.case, also read by the presenter tools). */
export function setOrCase(id: string): void {
  const or = e()<{ or: { case: string | null; play: number | null } }>('S').or;
  or.case = id;
  or.play = null;
}
/** The presenter's failure drill: '' when off, else the 0-based stage index that fails. */
export const failDrill = (): string => String(e()<{ or: { fail: string } }>('S').or.fail ?? '');

/** The ten stages with their activity lines (the demo's lrModel). */
export const runModel = (id: string): RunModel => e()<(c: Raw) => RunModel>('lrModel')(caseById(id));
/** When each stage and line plays, in ms (the demo's lrTimeline). */
export const runTimeline = (id: string, m: RunModel): { segs: Segment[]; total: number } =>
  e()<(c: Raw, m: RunModel) => { segs: Segment[]; total: number }>('lrTimeline')(caseById(id), m);
/** Changes when the case moves on (the demo's lrSig). */
export const runSignature = (id: string): string => e()<(c: Raw) => string>('lrSig')(caseById(id));
export const LR_PACE = { open: 400, gap: 150, settle: 300, min: 900, span: 500, tick: 100 };

export const runStates = (): Record<string, [string, string]> => e()<Record<string, [string, string]>>('RUN_ST');

/** The models a stage used, with their algorithm and validation (the demo's model cards). */
export function stageModels(id: string, s: RunStage): ModelCard[] {
  const c = caseById(id);
  const ks = e()<(c: Raw, n: number, l: RunLine[]) => string[]>('lrStageModels')(c, s.n, s.lines);
  const M = e()<Record<string, { kind: 'ML' | 'DL'; algo: string; task: string; data: string; val: (v: string) => string }>>('LR_MODELS');
  return ks.map((k) => {
    const v = e()<(c: Raw, k: string) => string>('lrModelVer')(c, k);
    return { key: k, version: v, kind: M[k].kind, algo: M[k].algo, task: M[k].task, validation: M[k].val(v), data: M[k].data };
  });
}
export const modelTag = (id: string, k: string): string => e()<(c: Raw, k: string) => string>('lrModelTag')(caseById(id), k);

export const nextStep = (id: string): NextStep => e()<(c: Raw) => NextStep>('afNextStep')(caseById(id));
/**
 * Do the case's next step as the signed-in person (the demo's runNext): it invokes the one action the step allows
 * (an enterprise acknowledgement goes through invoke as the system). The approval step is opened on the case instead.
 */
export const runNext = (id: string): ActionResult & { step?: NextStep } => e()<(id: string) => ActionResult & { step?: NextStep }>('runNext')(id);

export interface Escalation { case_id: string; blocker: string; owner: string; to: string; toLabel: string; msg: string }
export function escalationDraft(id: string, nx: NextStep): Escalation {
  const d = e()<(c: Raw, s: NextStep) => { data: Omit<Escalation, 'toLabel'> }>('afEscalation')(caseById(id), nx).data;
  const a = e()<(id: string) => { label: string } | undefined>('ACCT')(d.to);
  return { ...d, toLabel: a ? a.label : d.to };
}
export const sendEscalation = (d: Escalation, msg: string): Promise<ActionResult<{ to: string }>> =>
  invoke<{ to: string }>('escalation.send', { case_id: d.case_id, to: d.to, msg, blocker: d.blocker });

/** Recorded actions for the case (journal), agent tool calls that mention it, and its events. */
export const caseJournal = (id: string): JournalEntry[] => e()<(id: string) => JournalEntry[]>('afCaseJournal')(id);
export function agentCalls(id: string): AgentCall[] {
  const runs = e()<{ ui: { runs?: { id: string; calls?: Omit<AgentCall, 'run'>[] }[] } }>('AF').ui.runs ?? [];
  return runs.flatMap((r) => (r.calls ?? []).filter((k) => k.input.includes(id)).map((k) => ({ run: r.id, ...k })));
}
export const caseEvents = (id: string): RunEvent[] => e()<(RunEvent & { caseId?: string })[]>('EVENTS').filter((x) => x.caseId === id);
export const inputSummary = (i: Record<string, unknown>): string => e()<(i: Record<string, unknown>) => string>('afSummary')(i);

export const stageAgent = (n: number): string => e()<Record<number, string>>('AF_STAGE_AGENT')[n];
export const traceId = (id: string): string => 'trace-' + e()<(s: string) => string>('hashId')(id).toLowerCase();
/** 07 Oct 09:12 (the demo's orT). */
export const orT = (d: Date | string | number | null | undefined): string => e()<(d: unknown) => string>('orT')(d);
/** 12 min / 1.5 h / 2.0 days (the demo's orDur). */
export const orDur = (a: Date | null, b: Date | null): string => e()<(a: Date | null, b: Date | null) => string>('orDur')(a, b);

export const agents = (): AgentInfo[] => e()<AgentInfo[]>('AGENTS');
export const handoffModel = (): [string, string, string][] => e()<[string, string, string][]>('HANDOFF_MODEL');
export const poolsOn = (): boolean => !!e()<{ pools: boolean }>('FEAT').pools;
