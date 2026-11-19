/**
 * A live case: the Decision Workbench stage pages (#/product/<ID>/stage/<n>), the case Overview and Full analysis.
 * Typed wrappers over the demo's stage helpers (stData, stState, afRun, afNextStep …) so every sentence, number and
 * rule matches index.html. Detail tabs and Full analysis are long read-only HTML blocks the demo builds; they come back
 * as trusted HTML strings (the demo escapes every value) and keep the demo's markup, so its CSS applies unchanged.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bump, engine, engineSet } from '../engine/engine';
import type { ActionResult } from './types';

const g = () => engine();
const fn = <T extends (...a: any[]) => any>(name: string) => g()<T>(name);

// ---------- records ----------
export interface CostTerm { kind: string; label: string; amt: number }
export interface Route {
  id: string; plan: string; net: number; p10: number; p90: number; why?: string; target?: string;
  excluded?: boolean; failReason?: string; terms: CostTerm[]; gates: string[];
}
export interface Evidence { k: string; label: string; state: string; source: string; note?: string; fresh?: string }
export interface ExecStep { k: string; label: string; sys: string; state: string; ack?: { by: string; ref: string; at: string } | null }
export interface CaseRec {
  id: string; owner: string; location: string; assetId: string; product: string; mfr: string; cls: string;
  received: string; stage: string; grade?: string;
  routes: Route[]; recommendation: Route | null; chosen?: Route | null;
  submitted?: { by: string; at: string } | null;
  approval?: { ref: string; by: string; at: string; rationale: string } | null;
  packet?: { rationale: string; at: string; by: string } | null;
  outcome?: { net: number; by?: string; at?: string } | null;
  exec?: { ref: string; steps: ExecStep[] } | null;
  blocked?: { action: string; owner: string; reason: string } | null;
  requested?: { ref: string; at: string } | null;
  evidence: Evidence[];
  snapshot?: { id: string } | null;
}

export const caseById = (id: string): CaseRec | undefined => g()<Record<string, CaseRec>>('CASE_BY_ID')[id];
/** May the signed-in account open this case's stage pages (tenant, warehouse and page access)? */
export const caseVisible = (id: string): boolean => fn<(id: string) => boolean>('dpVisible')(id);

/**
 * The demo's helpers read the current route from location.hash (parse(), hq('step'), tiCase()). Keep the engine's
 * location in step with the React route before drawing anything from it.
 */
export function syncEngineRoute(pathAndSearch: string): void {
  const loc = g()<{ hash: string }>('location');
  const h = '#' + pathAndSearch;
  if (loc.hash !== h) loc.hash = h;
}

// ---------- stages ----------
export interface StageDef { n: number; k: string; t: string; trig: string; agent: string; person: string; sys: string[] }
export interface Phase { k: string; t: string; n: number[]; h: string }
export interface RunStage { n: number; t: string; label: string; state: string; result?: string; at?: string | null; by?: string; blocked?: { owner?: string; reason?: string } }
export interface Run { stage: number; stages: RunStage[]; done: boolean }
export type TagKind = 'done' | 'todo' | 'block' | 'wait' | 'cur';
export interface StageTag { k: TagKind; icon: string; word: string; who?: string; since?: string | null; why?: string }
export interface Fact { l: string; v: string; p: string /* provenance badge, HTML */ }
export interface StageData { res: string; facts: Fact[]; docs: string[]; mean: string; when?: string | null; who: string; tabs: [string, string, string][] }
export interface NextStep { kind: 'act' | 'ack' | 'approve' | 'wait' | 'blocked' | 'done'; n: number; label: string; action?: string; input?: Record<string, unknown>; role?: string }

export const stages = (): StageDef[] => g()<StageDef[]>('AF_STAGES');
export const phases = (): Phase[] => g()<Phase[]>('ST_PH');
export const phaseOf = (n: number): Phase => phases().find((p) => p.n.includes(n))!;
export const stageTitle = (n: number): string => stages()[n - 1].t;
/** What a stage that has not started will do (JSTEPS_AF). */
export const stageWillHappen = (n: number): string => g()<string[][]>('JSTEPS_AF')[n - 1][3];
export const runOf = (c: CaseRec): Run => fn<(c: CaseRec) => Run>('afRun')(c);
export const stageState = (c: CaseRec, n: number, run?: Run): StageTag => fn<(c: CaseRec, n: number, r?: Run) => StageTag>('stState')(c, n, run);
export const stageSentence = (c: CaseRec, n: number, t: StageTag): string => fn<(c: CaseRec, n: number, t: StageTag) => string>('stSentence')(c, n, t);
export const stageData = (c: CaseRec, n: number): StageData => fn<(c: CaseRec, n: number) => StageData>('stData')(c, n);
/** Where a case opens for the signed-in role: a stage number or 'overview'. */
export const landing = (c: CaseRec): number | 'overview' => fn<(c: CaseRec) => number | 'overview'>('stLand')(c);
export const nextStep = (c: CaseRec): NextStep => fn<(c: CaseRec) => NextStep>('afNextStep')(c);
/** "07 Oct 14:20" (time only when it is not midnight UTC). */
export const when = (d: string | Date | null | undefined): string => fn<(d: unknown) => string>('stWhen')(d);
/** Lower-case the first letter, as the demo's sentences do. */
export const lc = (t: string): string => (t ? t.charAt(0).toLowerCase() + t.slice(1) : t);
/** Route (without "#/") of a stage, the Overview or Full analysis. */
export function stageHref(id: string, n: number | 'overview' | 'full', tab?: string | null): string {
  return 'product/' + id + (n === 'overview' ? '/overview' : n === 'full' ? '/full' : '/stage/' + n + (tab ? '?tab=' + tab : ''));
}
/** The system logos a stage names (HTML). */
export const stageLogosHtml = (n: number): string => fn<(n: number) => string>('stLogos')(n);
/** Approvals go to the Approver when decisions are delegated, otherwise to Admin. */
export const approverRole = (): 'Approver' | 'Admin' => (g()<{ deleg: { decisions: boolean } }>('S').deleg.decisions ? 'Approver' : 'Admin');
/** The active instruction step's time-limit clock (escalation), if any. */
export function activeClock(c: CaseRec): { level?: number; lim?: string; to?: string } | null {
  const a = c.exec?.steps.find((y) => y.state === 'active');
  return a ? fn<(...a: unknown[]) => any>('exClock')(c, a, fn<() => Date>('asOfNow')()) : null;
}
/** Remembered detail tab per case and stage (S.stTabs). */
export function rememberedTab(id: string, n: number): string | undefined {
  return g()<{ stTabs?: Record<string, string> }>('S').stTabs?.[id + '|' + n];
}
export function rememberTab(id: string, n: number, k: string): void {
  const S = g()<{ stTabs?: Record<string, string> }>('S');
  (S.stTabs ??= {})[id + '|' + n] = k;
}

// ---------- case header bits ----------
export const assetModel = (c: CaseRec): string => fn<(c: CaseRec) => string>('asModel')(c);
export const assetSerial = (c: CaseRec): string => fn<(c: CaseRec) => string>('asSerial')(c);
export const assetPhotoHtml = (c: CaseRec, cls: string): string => fn<(c: CaseRec, cls: string) => string>('asPhoto')(c, cls).replace(' loading="lazy"', '');
export const predictedVsActualHtml = (pred: number, act: number): string => fn<(p: number, a: number) => string>('stPva')(pred, act);
export const badgeHtml = (k: string): string => fn<(k: string) => string>('afBadge')(k);
/** The coloured icon tile (frIt) beside "What it means". */
export const iconTileHtml = (ic: string, hue: string, cls: string): string => fn<(i: string, h: string, c: string) => string>('frIt')(ic, hue, cls);
/** Full analysis (stFull): today's Treatment Intelligence page with every section open. */
export const fullAnalysisHtml = (c: CaseRec): string => fn<(c: CaseRec) => string>('stFull')(c);

// ---------- approval card ----------
export const eligibleRoutes = (c: CaseRec): Route[] => c.routes.filter((x) => !x.excluded).sort((a, b) => b.net - a.net);
export const defaultSpend = (c: CaseRec, r: Route): number => fn<(c: CaseRec, r: Route) => number>('defaultSpend')(c, r);
/** The rationale the agent drafted (packet, or a fresh draft). */
export const draftRationale = (c: CaseRec): string => (c.packet ? c.packet.rationale : fn<(c: CaseRec) => string>('afDraftRationale')(c));
/** Approval limit of the signed-in account (Infinity when unlimited). */
export const approvalLimit = (): number => fn<(a: unknown) => number>('afLimitFor')(g()<{ acct: unknown }>('S').acct);
/** The raw instruction that approval sends, as highlighted JSON (HTML). */
export const instructionJsonHtml = (c: CaseRec): string => fn<(o: unknown) => string>('jsonHtml')(fn<(c: CaseRec) => unknown>('instrPayload')(c));
/** Spend and sale terms the approval card proposes for a route (ACT.approve's terms()). */
export function approvalTerms(c: CaseRec, t: Route): string {
  const money = fn<(n: number) => string>('money');
  const timing = (c as unknown as { timing?: string }).timing;
  return t.id === 'redeploy' ? `Transfer to ${t.target || 'receiving site'} by ${timing || 'Day 10'}; cancel planned purchase PO-${48000 + parseInt(c.id.slice(3))}`
    : t.id === 'resale' ? `Minimum acceptable price ${money(Math.max(0, t.p10))} · offer valid 14 days · fees as quoted`
    : t.id === 'hold' ? 'Review on 14 Nov 2026; re-evaluate if OPP-7712 is cancelled'
    : t.id === 'exit' ? 'Collection within 5 days; custody certificate required'
    : 'Reserve stock; release if the demand line is cancelled';
}

// ---------- the simulated enterprise systems ----------
/**
 * An enterprise system acknowledges the active instruction step. Only the simulated system calls this
 * (the demo's "Check for the next acknowledgement" and its auto-acknowledgement after approval).
 */
export function simulateSystemAck(caseId: string): ActionResult<{ label: string; by: string; ref_label: string }> {
  return fn<(...a: unknown[]) => ActionResult<{ label: string; by: string; ref_label: string }>>('invoke')('adapter.acknowledge', { case_id: caseId }, { via: 'system' });
}
/** The first step is acknowledged by the simulated system shortly after approval (afAutoAck). */
export const scheduleAutoAck = (caseId: string, step = 0): void => fn<(id: string, s: number) => void>('afAutoAck')(caseId, step);

/** The evidence pack (JSON) for download. */
export const evidencePack = (id: string): unknown => fn<(id: string) => unknown>('afEvidencePack')(id);

// ---------- Explain this decision (stage 6) ----------
export type ScenKey = 'purchase' | 'cost' | 'service' | 'market';
export interface Scen { purchase: number; cost: number; service: number; market: number; demandOff?: boolean; partUnavail?: boolean; newOnly?: boolean; certShort?: boolean }
export const scen = (): Scen => g()<{ scen: Scen }>('S').scen;
export function setScen(patch: Partial<Scen>): void {
  Object.assign(g()<{ scen: Scen }>('S').scen, patch);
  bump();
}
export function resetScen(): void {
  setScenSilently({ purchase: 1, cost: 1, service: 1, market: 1, demandOff: false, partUnavail: false, newOnly: false, certShort: false });
  g()<{ ti: { apply: string } }>('S').ti.apply = '';
  bump();
}
function setScenSilently(p: Partial<Scen>) { Object.assign(g()<{ scen: Scen }>('S').scen, p); }
/** "+30%" */
export const scenAdj = (v: number): string => fn<(v: number) => string>('tiAdj')(v);
export const confidence = (c: CaseRec, r: Route): string => fn<(c: CaseRec, r: Route) => string>('tiConf')(c, r);
/** The value drivers of the recommended route as bars (cxDrivers, HTML with data-ev on each row). */
export const driversHtml = (c: CaseRec, r: Route): string => fn<(c: CaseRec, r: Route) => string>('cxDrivers')(c, r);
/** What the stressed assumptions do to the ranking (tiResult, HTML). */
export const scenarioImpactHtml = (c: CaseRec): string => fn<(c: CaseRec, sr: unknown) => string>('tiResult')(c, fn<(c: CaseRec) => unknown>('scenRoutes')(c));
export interface SnapshotItem { k: string; label: string; ready: boolean; available: boolean; value: string; system: string; record: string; fetchedAt: string }
export function snapshotItems(c: CaseRec): SnapshotItem[] {
  const provFor = fn<(c: CaseRec, e: Evidence) => any>('provFor');
  return c.evidence.map((e) => {
    const p = provFor(c, e), ok = p.status === 'available';
    return { k: e.k, label: e.label, ready: e.state === 'ready', available: ok, value: ok ? String(p.value) : '—', system: String(p.vendor || p.sourceName || e.source), record: String(p.record || '—'), fetchedAt: ok ? new Date(p.fetchedAt).toISOString().slice(11, 16) + ' UTC' : '' };
  });
}
/** "EVS-… · frozen 2026-10-07 09:14:30 UTC" time of the evidence snapshot. */
export const snapshotFrozenAt = (c: CaseRec): string => fn<(d: unknown) => string>('isoT')(fn<(c: CaseRec) => Date>('snapTime')(c));

// ---------- the demo's own buttons inside the HTML blocks ----------
/** The payload behind an agent card button (afB → AF.btns[id]). */
export const agentButton = (id: string): Record<string, any> | undefined => g()<{ btns: Record<string, any> }>('AF').btns[id];
/** Is this demo action hidden from the signed-in role (rbRefuse without its toast)? */
export const actionDenied = (name: string): boolean => fn<() => Set<string>>('rbDenied')().has(name);

export interface LegacyHooks {
  toast(msg: string, ms?: number): void;
  modal(m: { title: string; body: string; foot: string; wide: boolean } | null): void;
  go(path: string): void;
}
/**
 * Run one of the demo's view-state handlers (ACT[name]: sliders, presets, ticks, compare, raw instruction …) for a
 * control inside a demo HTML block. Its toast, dialog and navigation calls are redirected to React for the duration
 * of the call and the demo's own re-draw is suppressed; React re-renders afterwards (unless `quiet`, used while a
 * slider is being dragged). State changes inside these handlers go through invoke() as in the demo.
 */
export function runLegacyAct(name: string, value: unknown, el: Element, ev: Event, hooks: LegacyHooks, quiet = false): boolean {
  const ACT = g()<Record<string, (v: unknown, el: Element, e: Event) => void>>('ACT');
  const f = ACT[name];
  if (!f) return false;
  const swaps: Record<string, unknown> = {
    toast: (m: string, ms?: number) => hooks.toast(m, ms),
    openModal: (title: string, body: string, foot: string, wide: boolean) => hooks.modal({ title, body, foot: foot || '', wide: !!wide }),
    openDrawer: (body: string, title: string, _sub: string, foot: string) => hooks.modal({ title, body, foot: foot || '', wide: true }),
    closeModal: () => hooks.modal(null),
    go: (p: string) => hooks.go(p),
    route: () => {},
  };
  const saved: Record<string, unknown> = {};
  for (const k of Object.keys(swaps)) { saved[k] = g()(k); engineSet(k, swaps[k]); }
  try {
    if (actionDenied(name)) hooks.toast('Not available for the ' + (g()<{ acct: { role: string } | null }>('S').acct?.role ?? 'signed-out') + ' view.');
    else f(value, el, ev);
  } catch (e) {
    console.warn('[case] ' + name, e);
  } finally {
    for (const k of Object.keys(saved)) engineSet(k, saved[k]);
  }
  if (!quiet) bump();
  return true;
}
/** Re-render after a quiet legacy handler (a slider released). */
export const refresh = (): void => bump();
