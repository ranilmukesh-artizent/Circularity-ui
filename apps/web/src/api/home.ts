/**
 * Home and the five utility pages (My Tasks, Alerts, Reports, Data Checks, Settings): typed reads over the demo's
 * helpers (frKpis, frAlerts, aomeItems, afBriefing, frActivity, runInvariants, FR_REP …) and the few view-level
 * changes those pages make (acknowledge or assign an alert, run the data checks, Home preferences).
 * With VITE_BACKEND=api: GET /api/screens/home/* and /api/checks, the reference lists, the session, and view settings
 * kept in this browser (di/screens/home.py and di/screens/checks.py have the mapping).
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bump, engine } from '../engine/engine';
import { invoke } from './actions';
import { API } from './backend';
import { cached, http, invalidate, peek, ref, session, withQuery } from './client';
import { alerts as navAlerts, navigation } from './nav';
import { can as canDo, canPage, currentAccount } from './session';
import { setView, view } from './view';

const g = <T = any>(name: string): T => engine()<T>(name);
const S = () => g<any>('S');
const call = <R = any>(name: string, ...a: unknown[]): R => g<(...x: unknown[]) => R>(name)(...a);
const H = '/api/screens/home';

// ---------- small parsers for the few helpers that return HTML fragments (engine) ----------
const text = (html: string): string => (html ? new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '' : '');

export interface Delta { cls: string; text: string; tip: string }
function parseDelta(html: string | undefined): Delta | undefined {
  if (!html) return undefined;
  const m = /class="frd ?([^"]*)"[^>]*data-tip="([^"]*)"[^>]*>([^<]*)</.exec(html);
  return m ? { cls: m[1].trim(), tip: text(m[2]), text: text(m[3]) } : undefined;
}

/** A status chip (the demo's frSt): tone is ok | info | warn | bad | line. */
export interface Status { tone: string; label: string }
function parseStatus(html: string | undefined): Status | undefined {
  if (!html) return undefined;
  const m = /class="frst ([^"]*)"><i><\/i>([^<]*)</.exec(html);
  return m ? { tone: m[1], label: text(m[2]) } : undefined;
}
const FR_ST = (): Record<string, [string, string]> => (API ? ref('FR_ST') : g('FR_ST'));
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
export const asOfNow = (): Date => (API ? new Date(new Date(ref<string>('AS_OF')).getTime() + Date.now() - T0) : call<Date>('asOfNow'));
/** 07 Oct 2026 (UTC). */
export const fmtDY = (d: Date | string | number): string =>
  new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
/** 07 Oct 2026, 09:30 IST in the region's time zone. */
export function rgTime(d: Date | string | number): string {
  const tz = view().rg.tz;
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz })
    .format(new Date(d)) + ' ' + (TZ_SHORT[tz] ?? tz);
}

// ---------- browser-side state (API mode): Home preferences, alert assignments, the live pause, checks run time ----------
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
const local: { assign: Record<string, string>; paused: boolean; checksAt: Date | null } = { assign: {}, paused: false, checksAt: null };
type HomeUi = Record<string, any>;
const uiKey = () => 'circ-home-ui-' + acctId();
const ui = (): HomeUi => lsGet<HomeUi>(uiKey()) ?? {};
const setUi = (patch: HomeUi) => {
  lsSet(uiKey(), { ...ui(), ...patch });
  bump();
};

// ---------- session-level facts ----------
export const role = (): string => (API ? currentAccount()?.role ?? '' : S().acct?.role ?? '');
export const isTechnical = (): boolean => {
  if (!API) return call<boolean>('afTech');
  const m = ui().mode;
  return m ? m === 'technical' : role() === 'Developer' || role() === 'Admin';
};
export const providerLabel = (): string => (API ? 'Circularity Agent' : call<{ label: string }>('afProvider').label);
/** Translate a menu label for the region's language (the demo's tr; I18N comes with the reference lists). */
export const translate = (t: string): string => {
  if (!API) return call<string>('tr', t);
  const lang = view().rg.lang;
  return (lang !== 'en' && ref<Record<string, Record<string, string>>>('I18N')[lang]?.[t]) || t;
};

export function greeting(): { date: string; greet: string } {
  const now = asOfNow(), tz = API ? view().rg.tz : S().rg.tz;
  const h = +new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hour12: false, timeZone: tz }).format(now);
  return {
    greet: h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening',
    date: new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone: tz }).format(now),
  };
}

/** Home preferences the demo keeps in AF.ui (saved with the agent state): frMode, frAct, frPer, frRt, mode. */
export const homeUi = (k: string): string | undefined => (API ? ui()[k] : call('afUi', k));
export function setHomeUi(k: string, v: string): void {
  if (API) return setUi({ [k]: v });
  call('afUi', k, v);
  bump();
}

/** Per-account preferences the demo keeps in localStorage (frLs): 'qa', 'mods', 'notif'. */
const frKey = (k: string) => 'circ-fr-' + k + (acctId() ? '-' + acctId() : '');
export const frPref = <T>(k: string): T | null => (API ? lsGet<T>(frKey(k)) : call('frLs', k));
export function setFrPref<T>(k: string, v: T): void {
  if (API) lsSet(frKey(k), v);
  else call('frLs', k, v);
  bump();
}

// ---------- briefing, tasks, alerts ----------
export interface BriefLine { text: string; go: string; n: number }
export const briefing = (): BriefLine[] => (API ? cached<BriefLine[]>(H + '/briefing') : call('afBriefing'));

export interface TaskItem { t: string; d: string; btn: string; act?: string; arg?: string; go?: string; group?: string }
export const taskItems = (): TaskItem[] => (API ? cached<TaskItem[]>(H + '/tasks') : call('aomeItems'));
/** The demo's frTaskGroup (the API sends it with each task). */
export const taskGroupOf = (i: TaskItem): string => {
  if (i.group) return i.group;
  const t = (i.t + ' ' + i.btn + ' ' + (i.go || '')).toLowerCase();
  return /integration|source map|stale|unavailable/.test(t) ? 'integration' : /evidence|inspection|record|result|receiving|wms/.test(t) ? 'evidence'
    : /confirm|acknowledge|outcome|check/.test(t) ? 'confirm' : 'decide';
};
/** [id, label, icon, hue, what Do it for me asks] */
export const taskGroups = (): [string, string, string, string, string][] => (API ? ref('FR_TG') : g('FR_TG'));

/** Run a task row's own button (only notifyAck exists today): through the action registry. */
export async function runTaskAct(act: string, arg: string) {
  if (act === 'notifyAck') return await invoke('notify.acknowledge', { id: arg });
  return { ok: false as const, error: { code: 'not_found' as const, message: 'That action is not available here.' } };
}

export interface Alert { id: string; kind: string; ic: string; h: string; t: string; s: string; sev: number; go: string; ack: boolean; ref?: string }
/** With the API: the same list as the bell and the menu (nav.ts), with this browser's acknowledgements. */
export const alerts = (): Alert[] => (API ? (navAlerts() as Alert[]) : call('frAlerts'));
export const alertAssignee = (id: string): string | undefined => (API ? local.assign[id] : S().frAssign?.[id]);
export const alertKinds = (): [string, string][] => (API ? ref('FR_AK') : g('FR_AK'));

const rbLog = (type: string, note: string) => call('rbLog', type, note);
const who = (): string => call('who');

/** Acknowledge an alert (the demo's frAlAck): a notification addressed to me is acknowledged through notify.acknowledge. */
export async function acknowledgeAlert(id: string): Promise<boolean> {
  const a = alerts().find((x) => x.id === id);
  if (!a) return false;
  if (API) {
    let acked = false;
    if (a.kind === 'note' && a.ref) {
      // addressed to me: it is one of my tasks (Actions on me lists the open notifications sent to me)
      const tasks = peek<TaskItem[]>(H + '/tasks') ?? (await http<TaskItem[]>(H + '/tasks'));
      if (tasks.some((t) => t.act === 'notifyAck' && t.arg === a.ref)) acked = (await invoke('notify.acknowledge', { id: a.ref })).ok;
    }
    setView({ acks: { ...view().acks, [id]: true } });
    return acked;
  }
  const s = S();
  let acked = false;
  if (a.kind === 'note' && s.notes.some((n: any) => n.id === a.ref && n.to === s.acct.id)) acked = (await invoke('notify.acknowledge', { id: a.ref })).ok;
  s.frAck[id] = true;
  rbLog('alert.acknowledged', id + ' · ' + a.t + ' · by ' + who());
  bump();
  return acked;
}

export function assignAlert(id: string, toRole: string): void {
  if (API) {
    local.assign = { ...local.assign, [id]: toRole };
    bump();
    return;
  }
  const s = S();
  s.frAssign = s.frAssign || {};
  s.frAssign[id] = toRole;
  rbLog('alert.assigned', id + ' → ' + toRole + ' · by ' + who());
  bump();
}

// ---------- Home: KPIs, activity, middle panel, figures ----------
export interface Kpi { ic: string; h: string; k: string; v: string | number; n?: number | null; l: string; sub?: string; go?: string; delta?: Delta; sp?: number[] }
/** Home's KPI tiles for a role (with the API: the signed-in account's role). */
export const kpis = (r: string): Kpi[] =>
  API ? cached<Kpi[]>(H + '/kpis') : call<any[]>('frKpis', r).map((o) => ({ ...o, delta: parseDelta(o.d), d: undefined }));

export interface ActivityRow { ic: string; h: string; title: string; badge?: string; sub: string; ago: string; st?: Status; links: { label: string; act: string; arg: string }[] }
export function activity(win: string): ActivityRow[] {
  if (API) return cached<ActivityRow[]>(withQuery(H + '/activity', { win }));
  return call<any[]>('frActivity', win).map((o) => {
    const b = /<span class="afb[^"]*"[^>]*>([^<]*)<\/span>/.exec(o.t || '');
    const links = [...String(o.x || '').matchAll(/data-act="([^"]*)" data-arg="([^"]*)">([^<]*)</g)].map((m) => ({ act: m[1], arg: text(m[2]), label: text(m[3]) }));
    return { ic: o.ic, h: o.h, title: text((o.t || '').replace(b?.[0] ?? '', '')).trim(), badge: b ? text(b[1]) : undefined, sub: text(o.s || ''), ago: o.ago, st: parseStatus(o.st), links };
  });
}

export interface RingSeg { v: number; c: string; l: string }
export interface MiddlePanel {
  id?: string; title: string; sub: string; link?: { go: string; label: string };
  ring?: { segs: RingSeg[]; center: string; sub: string; label?: string };
  bars?: { l: string; v: number; c: string; w: number }[];
}
/** The middle panel on Home per role (the demo's frMiddle; with the API, the signed-in account's role). */
export function middlePanel(r: string): MiddlePanel {
  if (API) return cached<MiddlePanel>(H + '/middle');
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
  if (r === 'Developer' || r === 'Admin') {
    call('wfInit');
    const c: Record<string, number> = { published: 0, failing: 0, draft: 0, paused: 0 };
    const list: any[] = S().wf.list;
    list.forEach((w) => c[call<string>('wfStat', w)]++);
    const srcN = new Set(list.filter((w) => w.src).map((w) => w.src)).size;
    return {
      id: 'frWfHealth', title: 'Workflow health', sub: 'Across ' + srcN + ' source systems', link: { go: 'integration/studio', label: 'View all →' },
      ring: {
        segs: [{ v: c.published, c: 'var(--ok)', l: 'Published' }, { v: c.failing, c: 'var(--bad)', l: 'Failing' }, { v: c.draft + c.paused, c: 'var(--muted)', l: 'Draft or paused' }],
        center: ((c.published / (list.length || 1)) * 100).toFixed(1) + '%', sub: 'Healthy', label: 'Workflow health',
      },
    };
  }
  const cs: any[] = call('visCases');
  if (r === 'Engineer') {
    const gr: Record<string, number> = {};
    cs.forEach((c) => { const k = c.grade ? 'Grade ' + c.grade : c.assessment === 'Pending' ? 'Not inspected' : c.condition; gr[k] = (gr[k] || 0) + 1; });
    const cols = ['var(--ok)', 'var(--h-money)', 'var(--h-dec)', 'var(--h-insp)', 'var(--muted)', 'var(--bad)'];
    return { title: 'Inspections by grade', sub: 'Every returned asset in your view', ring: { segs: Object.entries(gr).map(([l, v], i) => ({ v, l, c: cols[i % cols.length] })), center: String(cs.length), sub: 'assets' } };
  }
  if (r === 'Finance') {
    const rc = call<any[]>('visRows').filter((x) => x.status === 'reconciled');
    const inb = rc.filter((x) => Math.abs(x.actual - x.p50) <= Math.abs(x.p50) * 0.1).length, ab = rc.filter((x) => x.actual - x.p50 > Math.abs(x.p50) * 0.1).length;
    return {
      title: 'Predicted vs actual', sub: rc.length + ' reconciled decisions', link: { go: 'analytics/predicted', label: 'Analytics →' },
      ring: { segs: [{ v: inb, c: 'var(--ok)', l: 'Within ±10%' }, { v: ab, c: 'var(--h-money)', l: 'Above prediction' }, { v: rc.length - inb - ab, c: 'var(--bad)', l: 'Below prediction' }], center: ((inb / (rc.length || 1)) * 100).toFixed(0) + '%', sub: 'within ±10%' },
    };
  }
  if (r === 'Warehouse Manager') {
    const u = call<Record<string, number>>('ccUtil'), cols = ['var(--h-insp)', 'var(--h-money)', 'var(--h-dec)', 'var(--h-re)', 'var(--h-int)'];
    return { title: 'Receiving load', sub: 'Where assets are now', ring: { segs: Object.entries(u).map(([l, v], i) => ({ v, l, c: cols[i % 5] })), center: String(sum(Object.values(u))), sub: 'assets' } };
  }
  if (r === 'Executive') {
    const m = call<any>('metrics', call('visRows')), mx = Math.max(m.base, m.act, 1);
    const bar = (l: string, v: number, c: string) => ({ l, v, c, w: Math.max(2, (Math.abs(v) / mx) * 100) });
    return { title: 'Recovery waterfall', sub: m.rc.length + ' reconciled decisions', link: { go: 'analytics/waterfall', label: 'Analytics →' }, bars: [bar('Baseline', m.base, 'var(--muted)'), bar('Circularity uplift', m.uplift, 'var(--yellow)'), bar('Net recovery', m.act, 'var(--ok)')] };
  }
  const names: Record<string, string> = { approval: 'Awaiting approval', reeval: 'Re-evaluate', need: 'Needs evidence', await_insp: 'Awaiting inspection', approved: 'Approved', exec: 'Handed off', noroute: 'Other' };
  const cols: Record<string, string> = { 'Awaiting approval': 'var(--yellow)', 'Re-evaluate': 'var(--h-re)', 'Needs evidence': 'var(--h-ev)', 'Awaiting inspection': 'var(--h-insp)', Approved: 'var(--h-money)', 'Handed off': 'var(--ok)', Other: 'var(--muted)' };
  const st: Record<string, number> = {};
  cs.forEach((c) => { const k = names[call<string>('ccStage', c)]; st[k] = (st[k] || 0) + 1; });
  return { title: 'Decisions by stage', sub: 'Every returned asset in your view', ring: { segs: Object.entries(st).map(([l, v]) => ({ v, l, c: cols[l] })), center: String(cs.length), sub: 'returned assets' } };
}

export interface Figure { k: string; ic: string; h: string; v: string; l: string; sub: string; delta?: Delta }
/** Key figures for a period of '30', '90' or '365' days (the demo's frFigures). */
export function figures(per: string): Figure[] {
  if (API) return cached<Figure[]>(withQuery(H + '/figures', { per }));
  const n = per === '30' ? 1 : per === '90' ? 3 : 12, MONTHS: string[] = g('MONTHS'), mi0 = MONTHS.length - n;
  const all: any[] = call('visRows'), rows = all.filter((x) => x.mi >= mi0), rc = rows.filter((x) => x.status === 'reconciled');
  const sc = call<any>('ccScope'), open = sc.all.filter((c: any) => c._st === 'approval' || c._st === 'reeval');
  const prev = all.filter((x) => x.mi >= mi0 - n && x.mi < mi0 && x.status === 'reconciled');
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0), kf = (v: number) => call<string>('kfmt', v);
  const d = (a: number, b: number) => parseDelta(call<string>('frDelta', a, b, true));
  return [
    { k: 'assets', ic: 'box', h: 'insp', v: call<string>('fmtN', sc.all.length), l: 'Assets in scope', sub: 'returned assets now' },
    { k: 'potential', ic: 'dollar', h: 'money', v: kf(sum(open.map((c: any) => call<number>('ccNet', c)))), l: 'Potential recovery', sub: open.length + ' decisions open' },
    { k: 'risk', ic: 'alert', h: 'alert', v: kf(sum(sc.all.map((c: any) => c._var))), l: 'Value at risk', sub: 'next 30 days if no action' },
    { k: 'recovery', ic: 'trend', h: 'int', v: kf(sum(rc.map((x) => x.actual))), l: 'Net recovery', sub: rc.length + ' reconciled', delta: d(sum(rc.map((x) => x.actual)), sum(prev.map((x) => x.actual))) },
    { k: 'avoided', ic: 'layers', h: 'dec', v: kf(sum(rc.map((x) => x.avoided))), l: 'New purchases avoided', sub: 'confirmed avoided spend', delta: d(sum(rc.map((x) => x.avoided)), sum(prev.map((x) => x.avoided))) },
    { k: 'variance', ic: 'scale', h: 're', v: kf(sum(rc.map((x) => x.actual - x.p50))), l: 'Predicted against actual', sub: 'actual minus P50' },
  ];
}

// ---------- Home: watchlist, attention card, quick actions, modules, ask ----------
export interface Watch { id: string; text: string; fired?: boolean }
export const watches = (): Watch[] => ((API ? ui().watches : g<any>('AF').ui.watches) || []).filter((x: Watch) => !x.fired);
export function unwatch(id: string): void {
  if (API) return setUi({ watches: ((ui().watches || []) as Watch[]).filter((x) => x.id !== id) });
  const AF = g<any>('AF');
  AF.ui.watches = (AF.ui.watches || []).filter((x: any) => x.id !== id);
  call('afSave');
  bump();
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
  const PAGES = API ? ref<Record<string, unknown>>('PAGES') : g<Record<string, unknown>>('PAGES');
  const isRoute = (q: string[]) => /\//.test(q[0]) || !!PAGES[q[0]];
  const all: string[][] = API
    ? (FR_QA[role()] || FR_QA.Planner).filter((q) => !isRoute(q) || canPage(q[0].split('/')[0], q[0].split('/')[1] || undefined))
    : call<string[][]>('frQaAll');
  return all.map((q) => (isRoute(q) ? { go: q[0], label: q[1], icon: q[2] } : { act: q[0], label: q[1], icon: q[2] }));
}

export interface Module { id: string; label: string; sub: string; icon: string; hue: string; go: string }
const toModule = (x: any): Module => ({
  id: x.id, label: translate(x.label), sub: translate(x.sub), icon: x.icon,
  hue: (API ? ref<Record<string, string>>('FR_MODH') : g<Record<string, string>>('FR_MODH'))[x.id],
  go: API || x.leaf ? x.id : call<string>('navHref', x, '').slice(2),
});
type ModCfg = { order?: string[]; hide?: string[] };
/** The module cards in the account's order, without hidden ones (frMods). */
export function modules(): Module[] {
  if (!API) return call<any[]>('frMods').map(toModule);
  const cfg = frPref<ModCfg>('mods') || {}, ord = cfg.order || [], hid = cfg.hide || [];
  return allModules()
    .sort((a, b) => (ord.indexOf(a.id) + 1 || 99) - (ord.indexOf(b.id) + 1 || 99))
    .filter((m) => !hid.includes(m.id));
}
/** Every module the account may see, for Customize (with the API: the menu's groups, which are already filtered). */
export const allModules = (): Module[] =>
  API
    ? navigation().filter((x) => x.id !== 'home').map(toModule)
    : g<any[]>('NAV').filter((x) => x.id !== 'home' && call<boolean>('frVisible', x)).map(toModule);

export const askModes = (): [string, string, string, string][] => (API ? ref('FR_MODES') : g('FR_MODES'));
export const askStarters = (): string[] => {
  const st = API ? ref<Record<string, string[]>>('AF_STARTERS') : g<Record<string, string[]>>('AF_STARTERS');
  return st[role()] || st.Planner;
};
export function askExamples(): string[] {
  const cp = API ? canPage : g<(p: string, s?: string) => boolean>('canPage');
  const l = (API ? ref<any[]>('AF_INTENTS') : g<any[]>('AF_INTENTS'))
    .filter((I) => I.title && I.area !== 'presenter' && (I.area !== 'integration' || cp('integration')) && (I.area !== 'case' || cp('product', 'case')))
    .map((I) => I.title as string);
  return [...new Set(l)].slice(0, 40);
}
export const canManageWorkflows = (): boolean => (API ? canDo('manageWorkflows') : call('can', 'manageWorkflows'));
/** Refusal shown when a role cannot change workflows (NOWF). */
export const noWorkflowsMessage = (): string => (API ? ref('NOWF') : g('NOWF'));
/** $12k / −$1.20M (the demo's kfmt). */
export const kfmt = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  return a >= 1e6 ? s + '$' + (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? s + '$' + Math.round(a / 1e3) + 'k' : s + '$' + Math.round(a);
};

// ---------- Reports ----------
export interface Report { id: string; t: string; ic: string; h: string; d: string }
type Cell = string | number;
const FR_REP = () => g<any[]>('FR_REP');
export const reports = (): Report[] =>
  API ? cached<Report[]>(H + '/reports') : FR_REP().filter((r) => r.ok()).map(({ id, t, ic, h, d }) => ({ id, t, ic, h, d }));
/** A report served by its own page instead of rows here (with the API, the audit extract lives in the audit area). */
export const reportLink = (id: string): string | null => (API && id === 'audit' ? 'audit/log' : null);
/** Rows (header first) of a report for a tenant ('All' or one) and period ('30' | '90' | '365'). */
export function reportRows(id: string, tenant: string, period: string): Cell[][] {
  if (API) return reportLink(id) ? [[]] : cached<Cell[][]>(withQuery(H + '/reports/' + encodeURIComponent(id), { tenant, period }));
  const r = FR_REP().find((x) => x.id === id);
  if (!r) return [[]];
  const s = S(), t0 = s.frRepT, p0 = s.frRepP;
  s.frRepT = tenant;
  s.frRepP = period;
  try {
    return r.rows();
  } finally {
    s.frRepT = t0;
    s.frRepP = p0;
  }
}
/** The demo's frCsv. */
export const toCsv = (rows: Cell[][]): string =>
  rows.map((r) => r.map((v) => { const s = String(v == null ? '' : v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(',')).join('\n');
/** Run-board log lines (engine only: with the API, exports and views are not journalled yet). */
export const logReportExported = (title: string) => { if (!API) rbLog('report.exported', title + ' · CSV · ' + who()); bump(); };
export const logReportViewed = (title: string) => { if (!API) rbLog('report.viewed', title + ' · ' + who()); bump(); };
export const asOfLabel = (): string => {
  if (!API) return call('rgAsOf');
  return view().rg.tz === 'UTC' ? fmtDY(ref<string>('AS_OF')) : rgTime(asOfNow());
};

// ---------- Data Checks ----------
export interface Check { name: string; ok: boolean; detail: string }
export interface CheckNotRun { name: string; reason: string }
interface ChecksAnswer { checks: (Check & { data?: string; af?: boolean })[]; not_run: (CheckNotRun & { af?: boolean })[]; passed: number; total: number }
export const checks = (): Check[] =>
  API ? cached<ChecksAnswer>('/api/checks').checks.map(({ name, ok, detail }) => ({ name, ok, detail })) : call('runInvariants');
/** The demo's checks the backend cannot run (they test the demo page itself), each with why. Engine: none. */
export const checksNotRun = (): CheckNotRun[] => (API ? cached<ChecksAnswer>('/api/checks').not_run.map(({ name, reason }) => ({ name, reason })) : []);
/** The demo's frCheckOwner. */
export const checkOwner = (name: string): string =>
  /source|feed|mapping|integration|workflow|event/i.test(name) ? 'Developer' : /money|net|cost|recover|value|\$|baseline|avoid/i.test(name) ? 'Finance'
    : /approv|decision|route|gate/i.test(name) ? 'Decision Services' : 'Platform';
export const checksRunAt = (): Date => (API ? local.checksAt ?? asOfNow() : S().frChkAt || call('asOfNow'));
export function runChecks(): { ok: number; total: number } {
  if (API) {
    local.checksAt = asOfNow();
    const r = checks(), ok = r.filter((x) => x.ok).length;
    invalidate(); // the page shows the fresh answer when it arrives
    return { ok, total: r.length };
  }
  S().frChkAt = call('asOfNow');
  const r = checks(), ok = r.filter((x) => x.ok).length;
  rbLog('data.checks.run', ok + ' of ' + r.length + ' pass · ' + who());
  bump();
  return { ok, total: r.length };
}

// ---------- Settings ----------
export const roleDescription = (): string => (API ? session()?.description ?? '' : call<any>('pol')?.desc ?? '');
export const region = (): { lang: string; tz: string; cur: string } => (API ? view().rg : S().rg);
export const regionOptions = () => {
  const r = <T>(n: string): T => (API ? ref<T>(n) : g<T>(n));
  return {
    lang: r<[string, string][]>('RG_LANG'),
    tz: r<[string, string][]>('RG_TZ'),
    cur: Object.entries(r<Record<string, [string, number, string, string]>>('RG_CUR')).map(([k, v]) => [k, v[0] + ' ' + v[3]] as [string, string]),
  };
};
export function setRegion(k: 'lang' | 'tz' | 'cur', v: string): void {
  if (API) return setView({ rg: { ...view().rg, [k]: v } });
  S().rg[k] = v;
  call('rgSave');
  bump();
}
export const notifTypes = (): [string, string][] => (API ? ref('FR_NOTIF') : g('FR_NOTIF'));
interface AutoType { k: string; t: string; def: string; max: string }
/** Agent autonomy per action type for a role: [type, level label]. */
export function autonomy(r: string): [string, string][] {
  const types = API ? ref<AutoType[]>('AF_AUTO_TYPES') : g<AutoType[]>('AF_AUTO_TYPES'), levels = API ? ref<string[][]>('AF_LEVELS') : g<string[][]>('AF_LEVELS');
  const label = (lv: string) => (levels.find((l) => l[0] === lv) || [])[1] || '';
  if (!API) return types.map((t) => [t.t, label(call('afAutoLevel', r, t.k))]);
  // Admin's settings are read where the account may see them (Access › Agent autonomy); otherwise each type's default
  const matrix = canPage('access', 'autonomy') ? cached<{ autonomy?: { matrix: Record<string, Record<string, string>> } }>('/api/screens/access').autonomy?.matrix : undefined;
  const rank = ref<Record<string, number>>('AF_LV_RANK');
  return types.map((t) => {
    const v = matrix?.[r]?.[t.k] ?? t.def;
    return [t.t, label(rank[v] > rank[t.max] ? t.max : v)];
  });
}
/** The presenter flag (the demo's presenterOn): ?presenter=1 or this device's setting. */
export const presenterOn = (): boolean => {
  if (!API) return call('presenterOn');
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
export const livePaused = (): boolean => (API ? local.paused : !!S().frPause);
export function setLivePaused(off: boolean): void {
  if (API) local.paused = off;
  else S().frPause = off;
  bump();
}
