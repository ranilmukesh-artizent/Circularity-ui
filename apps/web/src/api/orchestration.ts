/**
 * Process orchestration (#/orchestration): the case run (ten stages, their activity lines and timing), the run trace,
 * run details and the agents and services. The live board's playback is view state and lives in the page.
 * With VITE_BACKEND=api: GET /api/screens/orchestration/cases and /run/{id}, actions, and the reference lists
 * (di/screens/orchestration.py has the mapping). The picked case and the failure drill are view state, kept here.
 * The live board follows real progress: every stream event refetches the run (client.ts), its signature changes when
 * the case moves on, and the board plays on from the stage it left.
 */
import { engine } from '../engine/engine';
import { invoke } from './actions';
import { API } from './backend';
import { cached, ref, withQuery } from './client';
import { fmtDate } from './format';
import { bump } from './store';
import type { ActionResult } from './types';
import { view } from './view';

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
export interface Escalation { case_id: string; blocker: string; owner: string; to: string; toLabel: string; msg: string }

type Raw = any; // eslint-disable-line @typescript-eslint/no-explicit-any
type LrModelRef = Record<string, { v: string; kind: 'ML' | 'DL'; algo: string; task: string; data: string }>;

// ---------------------------------------------------------------- API answers and view state
interface CasesAnswer { cases: OrCase[]; default: string | null; agents: AgentInfo[] }
interface RunAnswer {
  model: RunModel; timeline: { segs: Segment[]; total: number }; sig: string;
  stage_models: { key: string; version: string; validation: string }[][];
  next: NextStep & { action?: string; input?: Record<string, unknown> }; escalation: Escalation;
  journal: JournalEntry[]; agent_calls: AgentCall[]; events: RunEvent[]; trace_id: string;
}
/** The demo's S.or: the case picked on this page and the presenter's failure drill. */
const or = { case: null as string | null, fail: '' };

const casesAnswer = (): CasesAnswer => cached<CasesAnswer>(withQuery('/api/screens/orchestration/cases', { tenant: view().tenant }));
const runAnswer = (id: string): RunAnswer =>
  cached<RunAnswer>(withQuery('/api/screens/orchestration/run/' + encodeURIComponent(id), { fail: or.fail }));

// ---------------------------------------------------------------- cases
export const orCases = (): OrCase[] => (API ? casesAnswer().cases : e()<() => OrCase[]>('orCases')());
/** The case shown: the one picked earlier, else RT-1048, else the first in scope. */
export function orCase(): OrCase | undefined {
  if (!API) return e()<() => OrCase | undefined>('orCase')();
  const a = casesAnswer();
  return a.cases.find((c) => c.id === or.case) ?? a.cases.find((c) => c.id === a.default);
}
const caseById = (id: string): Raw => e()<Record<string, Raw>>('CASE_BY_ID')[id];
export const orCaseById = (id: string): OrCase | undefined => (API ? casesAnswer().cases.find((c) => c.id === id) : caseById(id));
/** Remember the case picked on this page (the demo's S.or.case, also read by the presenter tools). */
export function setOrCase(id: string): void {
  if (API) {
    or.case = id;
    return;
  }
  const s = e()<{ or: { case: string | null; play: number | null } }>('S').or;
  s.case = id;
  s.play = null;
}
/** The presenter's failure drill: '' when off, else the 0-based stage index that fails. */
export const failDrill = (): string => (API ? or.fail : String(e()<{ or: { fail: string } }>('S').or.fail ?? ''));
/** Turn the failure drill on ('0'..'9') or off (''); with the engine the presenter tools set it. */
export function setFailDrill(v: string): void {
  if (API) or.fail = v;
  else e()<{ or: { fail: string } }>('S').or.fail = v;
  bump();
}

// ---------------------------------------------------------------- the run
/** The ten stages with their activity lines (the demo's lrModel). */
export const runModel = (id: string): RunModel => (API ? runAnswer(id).model : e()<(c: Raw) => RunModel>('lrModel')(caseById(id)));
/** When each stage and line plays, in ms (the demo's lrTimeline). */
export const runTimeline = (id: string, m: RunModel): { segs: Segment[]; total: number } =>
  API ? runAnswer(id).timeline : e()<(c: Raw, m: RunModel) => { segs: Segment[]; total: number }>('lrTimeline')(caseById(id), m);
/** Changes when the case moves on (the demo's lrSig). */
export const runSignature = (id: string): string => (API ? runAnswer(id).sig : e()<(c: Raw) => string>('lrSig')(caseById(id)));
export const LR_PACE = { open: 400, gap: 150, settle: 300, min: 900, span: 500, tick: 100 };

export const runStates = (): Record<string, [string, string]> =>
  API ? ref<Record<string, [string, string]>>('RUN_ST') : e()<Record<string, [string, string]>>('RUN_ST');

/** The models a stage used, with their algorithm and validation (the demo's model cards). */
export function stageModels(id: string, s: RunStage): ModelCard[] {
  if (API) {
    const M = ref<LrModelRef>('LR_MODELS');
    return (runAnswer(id).stage_models[s.n - 1] ?? []).map(({ key, version, validation }) => ({
      key, version, kind: M[key].kind, algo: M[key].algo, task: M[key].task, validation, data: M[key].data,
    }));
  }
  const c = caseById(id);
  const ks = e()<(c: Raw, n: number, l: RunLine[]) => string[]>('lrStageModels')(c, s.n, s.lines);
  const M = e()<Record<string, { kind: 'ML' | 'DL'; algo: string; task: string; data: string; val: (v: string) => string }>>('LR_MODELS');
  return ks.map((k) => {
    const v = e()<(c: Raw, k: string) => string>('lrModelVer')(c, k);
    return { key: k, version: v, kind: M[k].kind, algo: M[k].algo, task: M[k].task, validation: M[k].val(v), data: M[k].data };
  });
}
export function modelTag(id: string, k: string): string {
  if (!API) return e()<(c: Raw, k: string) => string>('lrModelTag')(caseById(id), k);
  const M = ref<LrModelRef>('LR_MODELS');
  const v = runAnswer(id).stage_models.flat().find((m) => m.key === k)?.version ?? M[k]?.v;
  return k + ' ' + v + ' · ' + M[k]?.algo;
}

export const nextStep = (id: string): NextStep => (API ? runAnswer(id).next : e()<(c: Raw) => NextStep>('afNextStep')(caseById(id)));
/**
 * Do the case's next step as the signed-in person (the demo's runNext): it invokes the one action the step allows.
 * The approval step is opened on the case instead. With the engine an enterprise acknowledgement goes through invoke as
 * the system; with di-api only the enterprise systems acknowledge (the worker, B13b), so that step is not done here.
 */
export async function runNext(id: string): Promise<ActionResult & { step?: NextStep }> {
  if (!API) return e()<(id: string) => ActionResult & { step?: NextStep }>('runNext')(id);
  const st = runAnswer(id).next;
  if (st.kind === 'act' && st.action) return { ...(await invoke(st.action, st.input ?? { case_id: id })), step: st };
  if (st.kind === 'approve') return { ok: true, output: { opened: 'approval' }, key: null, action: 'approve', step: st };
  if (st.kind === 'ack')
    return { ok: false, error: { code: 'conflict', message: 'Acknowledgements come from the enterprise systems; the board updates when one arrives.' }, step: st };
  return { ok: false, error: { code: st.kind === 'done' ? 'duplicate' : 'conflict', message: st.label }, step: st };
}

export function escalationDraft(id: string, nx: NextStep): Escalation {
  if (API) return runAnswer(id).escalation;
  const d = e()<(c: Raw, s: NextStep) => { data: Omit<Escalation, 'toLabel'> }>('afEscalation')(caseById(id), nx).data;
  const a = e()<(id: string) => { label: string } | undefined>('ACCT')(d.to);
  return { ...d, toLabel: a ? a.label : d.to };
}
export const sendEscalation = (d: Escalation, msg: string): Promise<ActionResult<{ to: string }>> =>
  invoke<{ to: string }>('escalation.send', { case_id: d.case_id, to: d.to, msg, blocker: d.blocker });

// ---------------------------------------------------------------- run details and trace
/** Recorded actions for the case (journal), agent tool calls that mention it, and its events. */
export const caseJournal = (id: string): JournalEntry[] =>
  API ? runAnswer(id).journal : e()<(id: string) => JournalEntry[]>('afCaseJournal')(id);
export function agentCalls(id: string): AgentCall[] {
  if (API) return runAnswer(id).agent_calls;
  const runs = e()<{ ui: { runs?: { id: string; calls?: Omit<AgentCall, 'run'>[] }[] } }>('AF').ui.runs ?? [];
  return runs.flatMap((r) => (r.calls ?? []).filter((k) => k.input.includes(id)).map((k) => ({ run: r.id, ...k })));
}
export const caseEvents = (id: string): RunEvent[] =>
  API ? runAnswer(id).events : e()<(RunEvent & { caseId?: string })[]>('EVENTS').filter((x) => x.caseId === id);
/** case_id=RT-1048, tenant=… (the demo's afSummary). */
export const inputSummary = (i: Record<string, unknown>): string =>
  Object.entries(i || {})
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => k + '=' + (typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v).slice(0, 40)))
    .join(', ');

export const stageAgent = (n: number): string =>
  (API ? ref<Record<string, string>>('AF_STAGE_AGENT') : e()<Record<number, string>>('AF_STAGE_AGENT'))[n];
export const traceId = (id: string): string => (API ? runAnswer(id).trace_id : 'trace-' + e()<(s: string) => string>('hashId')(id).toLowerCase());
/** 07 Oct 09:12 (the demo's orT). */
export const orT = (d: Date | string | number | null | undefined): string => {
  if (!d) return '—';
  return fmtDate(d) + ' ' + new Date(d).toISOString().slice(11, 16);
};
/** 12 min / 1.5 h / 2.0 days (the demo's orDur). */
export const orDur = (a: Date | null, b: Date | null): string => {
  if (!a || !b) return '—';
  const m = Math.max(0, (+b - +a) / 6e4);
  return m < 60 ? Math.round(m) + ' min' : m < 2880 ? (m / 60).toFixed(1) + ' h' : (m / 1440).toFixed(1) + ' days';
};

export const agents = (): AgentInfo[] => (API ? casesAnswer().agents : e()<AgentInfo[]>('AGENTS'));
export const handoffModel = (): [string, string, string][] =>
  API ? ref<[string, string, string][]>('HANDOFF_MODEL') : e()<[string, string, string][]>('HANDOFF_MODEL');
export const poolsOn = (): boolean => !!(API ? ref<{ pools: boolean }>('FEAT') : e()<{ pools: boolean }>('FEAT')).pools;
