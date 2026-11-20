/**
 * Home and the five utility pages (My Tasks, Alerts, Reports, Data Checks, Settings): typed reads over the demo's
 * helpers (frKpis, frAlerts, aomeItems, afBriefing, frActivity, runInvariants, FR_REP …) and the few view-level
 * changes those pages make (acknowledge or assign an alert, run the data checks, Home preferences).
 * GET /api/screens/home/* and /api/checks, the reference lists, the session, and view settings
 * kept in this browser (di/screens/home.py and di/screens/checks.py have the mapping).
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { invoke } from './actions';
import { cached, http, invalidate, peek, ref, session, withQuery } from './client';
import { alerts as navAlerts, navigation } from './nav';
import { can as canDo, canPage, currentAccount } from './session';
import { bump } from './store';
import { sessionScoped, setView, view } from './view';

const H = '/api/screens/home';

export interface Delta { cls: string; text: string; tip: string }

/** A status chip (the demo's frSt): tone is ok | info | warn | bad | line. */
export interface Status { tone: string; label: string }
const FR_ST = (): Record<string, [string, string]> => ref('FR_ST');
export const status = (k: string, label?: string): Status => {
  const s = FR_ST()[k] ?? [k, 'line'];
  return { tone: s[1], label: label ?? s[0] };
};

// ---------- time and region (the demo's asOfNow, fmtDY, rgTime: also used by the Command Center's clock) ----------
const T0 = Date.now();
const TZ_SHORT: Record<string, string> = {
  UTC: 'UTC', 'Asia/Kolkata': 'IST', 'Asia/Tokyo': 'JST', 'Europe/Berlin': 'CET', 'Europe/Helsinki': 'EET', 'America/New_York': 'ET',
};
/** The world's "now": the seeded as-of date plus the time since the app started. */
export const asOfNow = (): Date => new Date(new Date(ref('AS_OF')).getTime() + Date.now() - T0);
/** 07 Oct 2026 (UTC). */
export const fmtDY = (d: Date | string | number): string =>
  new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
/** 07 Oct 2026, 09:30 IST in the region's time zone. */
export function rgTime(d: Date | string | number): string {
  const tz = view().rg.tz;
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz })
    .format(new Date(d)) + ' ' + (TZ_SHORT[tz] ?? tz);
}

// ---------- browser-side state: Home preferences, alert assignments, the live pause, checks run time ----------
const acctId = (): string => session()?.account.id ?? '';
function lsGet<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null') as T | null;
  } catch {
    return null;
  }
}
function lsSet(key: string, v: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* private window: lasts for this page only */
  }
}
// this session's alert hand-overs, live-feed pause and last checks run (not kept across sign-in and sign-out)
const local = sessionScoped<{ assign: Record<string, string>; paused: boolean; checksAt: Date | null }>(() => ({ assign: {}, paused: false, checksAt: null }));
type HomeUi = Record<string, any>;
const uiKey = () => 'circ-home-ui-' + acctId();
const ui = (): HomeUi => lsGet<HomeUi>(uiKey()) ?? {};
const setUi = (patch: HomeUi) => {
  lsSet(uiKey(), { ...ui(), ...patch });
  bump();
};

// ---------- session-level facts ----------
export const role = (): string => currentAccount()?.role ?? '';
export const isTechnical = (): boolean => {
  const m = ui().mode;
  return m ? m === 'technical' : role() === 'Developer' || role() === 'Admin';
};
export const providerLabel = (): string => 'Circularity Agent';
/** Translate a menu label for the region's language (the demo's tr; I18N comes with the reference lists). */
export const translate = (t: string): string => {
  const lang = view().rg.lang;
  return (lang !== 'en' && ref('I18N')[lang]?.[t]) || t;
};

export function greeting(): { date: string; greet: string } {
  const now = asOfNow(), tz = view().rg.tz;
  const h = +new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hour12: false, timeZone: tz }).format(now);
  return {
    greet: h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening',
    date: new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone: tz }).format(now),
  };
}

/** Home preferences the demo keeps in AF.ui (saved with the agent state): frMode, frAct, frPer, frRt, mode. */
export const homeUi = (k: string): string | undefined => ui()[k];
export function setHomeUi(k: string, v: string): void {
  setUi({ [k]: v });
}

/** Per-account preferences the demo keeps in localStorage (frLs): 'qa', 'mods', 'notif'. */
const frKey = (k: string) => 'circ-fr-' + k + (acctId() ? '-' + acctId() : '');
export const frPref = <T>(k: string): T | null => lsGet<T>(frKey(k));
export function setFrPref<T>(k: string, v: T): void {
  lsSet(frKey(k), v);
  bump();
}

// ---------- briefing, tasks, alerts ----------
export interface BriefLine { text: string; go: string; n: number }
export const briefing = (): BriefLine[] => cached<BriefLine[]>(H + '/briefing');

export interface TaskItem { t: string; d: string; btn: string; act?: string; arg?: string; go?: string; group?: string }
export const taskItems = (): TaskItem[] => cached<TaskItem[]>(H + '/tasks');
/** The demo's frTaskGroup (the API sends it with each task). */
export const taskGroupOf = (i: TaskItem): string => {
  if (i.group) return i.group;
  const t = (i.t + ' ' + i.btn + ' ' + (i.go || '')).toLowerCase();
  return /integration|source map|stale|unavailable/.test(t) ? 'integration' : /evidence|inspection|record|result|receiving|wms/.test(t) ? 'evidence'
    : /confirm|acknowledge|outcome|check/.test(t) ? 'confirm' : 'decide';
};
/** [id, label, icon, hue, what Do it for me asks] */
export const taskGroups = (): [string, string, string, string, string][] => ref('FR_TG');

/** Run a task row's own button (only notifyAck exists today): through the action registry. */
export async function runTaskAct(act: string, arg: string) {
  if (act === 'notifyAck') return await invoke('notify.acknowledge', { id: arg });
  return { ok: false as const, error: { code: 'not_found' as const, message: 'That action is not available here.' } };
}

export interface Alert { id: string; kind: string; ic: string; h: string; t: string; s: string; sev: number; go: string; ack: boolean; ref?: string }
/** The same list as the bell and the menu (nav.ts), with this browser's acknowledgements. */
export const alerts = (): Alert[] => navAlerts() as Alert[];
export const alertAssignee = (id: string): string | undefined => local.current.assign[id];
export const alertKinds = (): [string, string][] => ref('FR_AK');

/** Acknowledge an alert (the demo's frAlAck): a notification addressed to me is acknowledged through notify.acknowledge. */
export async function acknowledgeAlert(id: string): Promise<boolean> {
  const a = alerts().find((x) => x.id === id);
  if (!a) return false;
  let acked = false;
  if (a.kind === 'note' && a.ref) {
    // addressed to me: it is one of my tasks (Actions on me lists the open notifications sent to me)
    const tasks = peek<TaskItem[]>(H + '/tasks') ?? (await http<TaskItem[]>(H + '/tasks'));
    if (tasks.some((t) => t.act === 'notifyAck' && t.arg === a.ref)) acked = (await invoke('notify.acknowledge', { id: a.ref })).ok;
  }
  setView({ acks: { ...view().acks, [id]: true } });
  return acked;
}

export function assignAlert(id: string, toRole: string): void {
  local.current.assign = { ...local.current.assign, [id]: toRole };
  bump();
}

// ---------- Home: KPIs, activity, middle panel, figures ----------
export interface Kpi { ic: string; h: string; k: string; v: string | number; n?: number | null; l: string; sub?: string; go?: string; delta?: Delta; sp?: number[] }
/** Home's KPI tiles for the signed-in account's role (the argument is kept for callers; the server knows the role). */
export const kpis = (_r: string): Kpi[] => cached<Kpi[]>(H + '/kpis');

export interface ActivityRow { ic: string; h: string; title: string; badge?: string; sub: string; ago: string; st?: Status; links: { label: string; act: string; arg: string }[] }
export function activity(win: string): ActivityRow[] {
  return cached<ActivityRow[]>(withQuery(H + '/activity', { win }));
}

export interface RingSeg { v: number; c: string; l: string }
export interface MiddlePanel {
  id?: string; title: string; sub: string; link?: { go: string; label: string };
  ring?: { segs: RingSeg[]; center: string; sub: string; label?: string };
  bars?: { l: string; v: number; c: string; w: number }[];
}
/** The middle panel on Home for the signed-in account's role (the demo's frMiddle). */
export function middlePanel(_r: string): MiddlePanel {
  return cached<MiddlePanel>(H + '/middle');
}

export interface Figure { k: string; ic: string; h: string; v: string; l: string; sub: string; delta?: Delta }
/** Key figures for a period of '30', '90' or '365' days (the demo's frFigures). */
export function figures(per: string): Figure[] {
  return cached<Figure[]>(withQuery(H + '/figures', { per }));
}

// ---------- Home: watchlist, attention card, quick actions, modules, ask ----------
export interface Watch { id: string; text: string; fired?: boolean }
export const watches = (): Watch[] => (ui().watches || []).filter((x: Watch) => !x.fired);
export function unwatch(id: string): void {
  setUi({ watches: ((ui().watches || []) as Watch[]).filter((x) => x.id !== id) });
}

export interface Attention { head: string; line: string; btn: string; go: string }
export function attention(): Attention | null {
  const r = role(), al = alerts().filter((a) => !a.ack);
  if (r === 'Developer' || r === 'Admin') {
    const f = al.filter((a) => a.kind === 'wf' || a.kind === 'src');
    if (f.length) return { head: f.length + ' integration issue' + (f.length > 1 ? 's' : '') + ' need attention', line: 'Resolve failing workflows and stale sources to keep data fresh and decisions current.', btn: 'View issues', go: 'alerts' };
  }
  const e = al.filter((a) => a.kind === 'esc' || a.kind === 'note');
  if (e.length) return { head: e.length + ' item' + (e.length > 1 ? 's' : '') + ' need attention', line: 'Escalations and notifications waiting for an owner.', btn: 'View issues', go: 'alerts' };
  const need = taskItems().length;
  return need ? { head: need + ' task' + (need > 1 ? 's' : '') + ' wait on you', line: 'Open My Tasks to clear the oldest first.', btn: 'My Tasks', go: 'tasks' } : null;
}

/** The demo's quick actions per role (FR_QA): [route or handler, label, icon]. */
const FR_QA: Record<string, [string, string, string][]> = {
  Admin: [['wfNew', 'New workflow', 'plus'], ['frConnect', 'Connect a source system', 'unplug'], ['checks', 'Run data checks', 'checks'], ['command', 'View Command Center', 'command'], ['product/received', 'Open Decision Workbench', 'product']],
  Developer: [['wfNew', 'New workflow', 'plus'], ['frConnect', 'Connect a source system', 'unplug'], ['checks', 'Run data checks', 'checks'], ['integration/events', 'Event stream', 'stream'], ['integration/map', 'Source map', 'graph']],
  Planner: [['product/received', 'Returned assets', 'box'], ['command/aome', 'Request evidence', 'search'], ['frCompare', 'Compare routes', 'scale'], ['product/received', 'Open Decision Workbench', 'product']],
  Approver: [['command/approvals', 'Approval inbox', 'inbox'], ['alerts', 'Escalations', 'clock'], ['frCompare', 'Compare routes', 'scale']],
  Engineer: [['command/aome', 'Record a result', 'clipboard'], ['product/received', 'Inspection queue', 'cal']],
  Finance: [['command/outcomes', 'Confirm outcomes', 'checks'], ['analytics', 'Reconcile and learn', 'analytics'], ['reports', 'Reports', 'report']],
  'Warehouse Manager': [['product/expected', 'Plan receiving', 'truck'], ['command/handed', 'Steps waiting', 'warehouse']],
  Executive: [['command', 'Command Center', 'command'], ['analytics', 'Analytics', 'analytics'], ['reports', 'Reports', 'report']],
};
/** Quick actions for the role: `go` is a route; otherwise `act` names the demo handler (wfNew, frConnect, frCompare). */
export interface QuickAction { label: string; icon: string; go?: string; act?: string }
export function quickActions(): QuickAction[] {
  const PAGES = ref('PAGES');
  const isRoute = (q: string[]) => /\//.test(q[0]) || !!PAGES[q[0]];
  const all: string[][] = (FR_QA[role()] || FR_QA.Planner).filter((q) => !isRoute(q) || canPage(q[0].split('/')[0], q[0].split('/')[1] || undefined));
  return all.map((q) => (isRoute(q) ? { go: q[0], label: q[1], icon: q[2] } : { act: q[0], label: q[1], icon: q[2] }));
}

export interface Module { id: string; label: string; sub: string; icon: string; hue: string; go: string }
const toModule = (x: any): Module => ({
  id: x.id, label: translate(x.label), sub: translate(x.sub), icon: x.icon,
  hue: ref('FR_MODH')[x.id],
  go: x.id,
});
type ModCfg = { order?: string[]; hide?: string[] };
/** The module cards in the account's order, without hidden ones (frMods). */
export function modules(): Module[] {
  const cfg = frPref<ModCfg>('mods') || {}, ord = cfg.order || [], hid = cfg.hide || [];
  return allModules()
    .sort((a, b) => (ord.indexOf(a.id) + 1 || 99) - (ord.indexOf(b.id) + 1 || 99))
    .filter((m) => !hid.includes(m.id));
}
/** Every module the account may see, for Customize (the menu's groups, which are already filtered). */
export const allModules = (): Module[] => navigation().filter((x) => x.id !== 'home').map(toModule);

export const askModes = (): [string, string, string, string][] => ref('FR_MODES');
export const askStarters = (): string[] => {
  const st = ref('AF_STARTERS');
  return st[role()] || st.Planner;
};
export function askExamples(): string[] {
  const l = ref('AF_INTENTS')
    .filter((I) => I.title && I.area !== 'presenter' && (I.area !== 'integration' || canPage('integration')) && (I.area !== 'case' || canPage('product', 'case')))
    .map((I) => I.title as string);
  return [...new Set(l)].slice(0, 40);
}
export const canManageWorkflows = (): boolean => canDo('manageWorkflows');
/** Refusal shown when a role cannot change workflows (NOWF). */
export const noWorkflowsMessage = (): string => ref('NOWF');
/** $12k / −$1.20M (the demo's kfmt). */
export const kfmt = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  return a >= 1e6 ? s + '$' + (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? s + '$' + Math.round(a / 1e3) + 'k' : s + '$' + Math.round(a);
};

// ---------- Reports ----------
export interface Report { id: string; t: string; ic: string; h: string; d: string }
type Cell = string | number;
export const reports = (): Report[] => cached<Report[]>(H + '/reports');
/** A report served by its own page instead of rows here (the audit extract lives in the audit area). */
export const reportLink = (id: string): string | null => (id === 'audit' ? 'audit/log' : null);
/** Rows (header first) of a report for a tenant ('All' or one) and period ('30' | '90' | '365'). */
export function reportRows(id: string, tenant: string, period: string): Cell[][] {
  return reportLink(id) ? [[]] : cached<Cell[][]>(withQuery(H + '/reports/' + encodeURIComponent(id), { tenant, period }));
}
/** The demo's frCsv. */
export const toCsv = (rows: Cell[][]): string =>
  rows.map((r) => r.map((v) => { const s = String(v == null ? '' : v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(',')).join('\n');
/** Exports and views are not journalled yet: these only refresh the page. */
export const logReportExported = (_title: string) => { bump(); };
export const logReportViewed = (_title: string) => { bump(); };
export const asOfLabel = (): string => {
  return view().rg.tz === 'UTC' ? fmtDY(ref('AS_OF')) : rgTime(asOfNow());
};

// ---------- Data Checks ----------
export interface Check { name: string; ok: boolean; detail: string }
export interface CheckNotRun { name: string; reason: string }
interface ChecksAnswer { checks: (Check & { data?: string; af?: boolean })[]; not_run: (CheckNotRun & { af?: boolean })[]; passed: number; total: number }
export const checks = (): Check[] => cached<ChecksAnswer>('/api/checks').checks.map(({ name, ok, detail }) => ({ name, ok, detail }));
/** The demo's checks the backend cannot run (they test the demo page itself), each with why. */
export const checksNotRun = (): CheckNotRun[] => cached<ChecksAnswer>('/api/checks').not_run.map(({ name, reason }) => ({ name, reason }));
/** The demo's frCheckOwner. */
export const checkOwner = (name: string): string =>
  /source|feed|mapping|integration|workflow|event/i.test(name) ? 'Developer' : /money|net|cost|recover|value|\$|baseline|avoid/i.test(name) ? 'Finance'
    : /approv|decision|route|gate/i.test(name) ? 'Decision Services' : 'Platform';
export const checksRunAt = (): Date => local.current.checksAt ?? asOfNow();
export function runChecks(): { ok: number; total: number } {
  local.current.checksAt = asOfNow();
  const r = checks(), ok = r.filter((x) => x.ok).length;
  invalidate(); // the page shows the fresh answer when it arrives
  return { ok, total: r.length };
}

// ---------- Settings ----------
export const roleDescription = (): string => session()?.description ?? '';
export const region = (): { lang: string; tz: string; cur: string } => view().rg;
export const regionOptions = () => {
  return {
    lang: ref('RG_LANG'),
    tz: ref('RG_TZ'),
    cur: Object.entries(ref('RG_CUR')).map(([k, v]) => [k, v[0] + ' ' + v[3]] as [string, string]),
  };
};
export function setRegion(k: 'lang' | 'tz' | 'cur', v: string): void {
  setView({ rg: { ...view().rg, [k]: v } });
}
export const notifTypes = (): [string, string][] => ref('FR_NOTIF');
/** Agent autonomy per action type for a role: [type, level label]. */
export function autonomy(r: string): [string, string][] {
  const types = ref('AF_AUTO_TYPES'), levels = ref('AF_LEVELS');
  const label = (lv: string) => (levels.find((l) => l[0] === lv) || [])[1] || '';
  // Admin's settings are read where the account may see them (Access › Agent autonomy); otherwise each type's default
  const matrix = canPage('access', 'autonomy') ? cached<{ autonomy?: { matrix: Record<string, Record<string, string>> } }>('/api/screens/access').autonomy?.matrix : undefined;
  const rank = ref('AF_LV_RANK');
  return types.map((t) => {
    const v = matrix?.[r]?.[t.k] ?? t.def;
    return [t.t, label(rank[v] > rank[t.max] ? t.max : v)];
  });
}
/** The presenter flag (the demo's presenterOn): ?presenter=1 or this device's setting. */
export const presenterOn = (): boolean => {
  try {
    const q = /[?&]presenter=([01])/.exec(window.location.search);
    if (q) localStorage.setItem('circ-presenter', q[1]);
    return localStorage.getItem('circ-presenter') === '1';
  } catch {
    return false;
  }
};
export function setPresenter(on: boolean): void {
  try { localStorage.setItem('circ-presenter', on ? '1' : '0'); } catch { /* storage unavailable */ }
  bump();
}
export const livePaused = (): boolean => local.current.paused;
export function setLivePaused(off: boolean): void {
  local.current.paused = off;
  bump();
}
