// B14 golden data for Home and the Command Center: what the facade functions in apps/web/src/api/home.ts and
// apps/web/src/api/command.ts return, for every account, computed by the demo's own functions with the same arguments.
//
//   node apps/web/scripts/golden/home_command.mjs   -> fixtures/golden/screens/home.json, screens/command.json
//
// The facade's own mapping (parsing the demo's HTML fragments, projecting the Command Center's case objects) is
// repeated here as plain JavaScript, so the files hold exactly what each page receives.
import { freshDemo, writeGolden } from '../golden-sandbox.mjs';

const g = freshDemo();
const S = g('S');
const call = (name, ...a) => g(name)(...a);
const sum = (a) => a.reduce((x, y) => x + (y || 0), 0);
const setAcct = g('setAcct'), ACCT = g('ACCT');
const ACCOUNTS = g('ACCOUNTS').map((a) => a.id);
// a deep copy, so shared objects (a request, a notification) are written in full wherever they appear, not as $ref
const tree = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === 'number' && !Number.isFinite(v) ? String(v) : v)));

// ---------------------------------------------------------------- the facade's small parsers (no DOM here)
const unesc = (s) => String(s ?? '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const text = (html) => (html ? unesc(String(html).replace(/<[^>]*>/g, '')) : '');
function parseDelta(html) {
  if (!html) return undefined;
  const m = /class="frd ?([^"]*)"[^>]*data-tip="([^"]*)"[^>]*>([^<]*)</.exec(html);
  return m ? { cls: m[1].trim(), tip: text(m[2]), text: text(m[3]) } : undefined;
}
function parseStatus(html) {
  if (!html) return undefined;
  const m = /class="frst ([^"]*)"><i><\/i>([^<]*)</.exec(html);
  return m ? { tone: m[1], label: text(m[2]) } : undefined;
}

// ---------------------------------------------------------------- home.ts
const role = () => S.acct?.role ?? '';
const taskItems = () => call('aomeItems').map((i) => ({ ...i, group: call('frTaskGroup', i) }));
const kpis = (r) => call('frKpis', r).map((o) => ({ ...o, delta: parseDelta(o.d), d: undefined }));
function activity(win) {
  return call('frActivity', win).map((o) => {
    const b = /<span class="afb[^"]*"[^>]*>([^<]*)<\/span>/.exec(o.t || '');
    const links = [...String(o.x || '').matchAll(/data-act="([^"]*)" data-arg="([^"]*)">([^<]*)</g)].map((m) => ({ act: m[1], arg: text(m[2]), label: text(m[3]) }));
    return { ic: o.ic, h: o.h, title: text((o.t || '').replace(b?.[0] ?? '', '')).trim(), badge: b ? text(b[1]) : undefined, sub: text(o.s || ''), ago: o.ago, st: parseStatus(o.st), links };
  });
}
function middlePanel(r) {
  if (r === 'Developer' || r === 'Admin') {
    call('wfInit');
    const c = { published: 0, failing: 0, draft: 0, paused: 0 };
    const list = S.wf.list;
    list.forEach((w) => c[call('wfStat', w)]++);
    const srcN = new Set(list.filter((w) => w.src).map((w) => w.src)).size;
    return {
      id: 'frWfHealth', title: 'Workflow health', sub: 'Across ' + srcN + ' source systems', link: { go: 'integration/studio', label: 'View all →' },
      ring: {
        segs: [{ v: c.published, c: 'var(--ok)', l: 'Published' }, { v: c.failing, c: 'var(--bad)', l: 'Failing' }, { v: c.draft + c.paused, c: 'var(--muted)', l: 'Draft or paused' }],
        center: ((c.published / (list.length || 1)) * 100).toFixed(1) + '%', sub: 'Healthy', label: 'Workflow health',
      },
    };
  }
  const cs = call('visCases');
  if (r === 'Engineer') {
    const gr = {};
    cs.forEach((c) => { const k = c.grade ? 'Grade ' + c.grade : c.assessment === 'Pending' ? 'Not inspected' : c.condition; gr[k] = (gr[k] || 0) + 1; });
    const cols = ['var(--ok)', 'var(--h-money)', 'var(--h-dec)', 'var(--h-insp)', 'var(--muted)', 'var(--bad)'];
    return { title: 'Inspections by grade', sub: 'Every returned asset in your view', ring: { segs: Object.entries(gr).map(([l, v], i) => ({ v, l, c: cols[i % cols.length] })), center: String(cs.length), sub: 'assets' } };
  }
  if (r === 'Finance') {
    const rc = call('visRows').filter((x) => x.status === 'reconciled');
    const inb = rc.filter((x) => Math.abs(x.actual - x.p50) <= Math.abs(x.p50) * 0.1).length, ab = rc.filter((x) => x.actual - x.p50 > Math.abs(x.p50) * 0.1).length;
    return {
      title: 'Predicted vs actual', sub: rc.length + ' reconciled decisions', link: { go: 'analytics/predicted', label: 'Analytics →' },
      ring: { segs: [{ v: inb, c: 'var(--ok)', l: 'Within ±10%' }, { v: ab, c: 'var(--h-money)', l: 'Above prediction' }, { v: rc.length - inb - ab, c: 'var(--bad)', l: 'Below prediction' }], center: ((inb / (rc.length || 1)) * 100).toFixed(0) + '%', sub: 'within ±10%' },
    };
  }
  if (r === 'Warehouse Manager') {
    const u = call('ccUtil'), cols = ['var(--h-insp)', 'var(--h-money)', 'var(--h-dec)', 'var(--h-re)', 'var(--h-int)'];
    return { title: 'Receiving load', sub: 'Where assets are now', ring: { segs: Object.entries(u).map(([l, v], i) => ({ v, l, c: cols[i % 5] })), center: String(sum(Object.values(u))), sub: 'assets' } };
  }
  if (r === 'Executive') {
    const m = call('metrics', call('visRows')), mx = Math.max(m.base, m.act, 1);
    const bar = (l, v, c) => ({ l, v, c, w: Math.max(2, (Math.abs(v) / mx) * 100) });
    return { title: 'Recovery waterfall', sub: m.rc.length + ' reconciled decisions', link: { go: 'analytics/waterfall', label: 'Analytics →' }, bars: [bar('Baseline', m.base, 'var(--muted)'), bar('Circularity uplift', m.uplift, 'var(--yellow)'), bar('Net recovery', m.act, 'var(--ok)')] };
  }
  const names = { approval: 'Awaiting approval', reeval: 'Re-evaluate', need: 'Needs evidence', await_insp: 'Awaiting inspection', approved: 'Approved', exec: 'Handed off', noroute: 'Other' };
  const cols = { 'Awaiting approval': 'var(--yellow)', 'Re-evaluate': 'var(--h-re)', 'Needs evidence': 'var(--h-ev)', 'Awaiting inspection': 'var(--h-insp)', Approved: 'var(--h-money)', 'Handed off': 'var(--ok)', Other: 'var(--muted)' };
  const st = {};
  cs.forEach((c) => { const k = names[call('ccStage', c)]; st[k] = (st[k] || 0) + 1; });
  return { title: 'Decisions by stage', sub: 'Every returned asset in your view', ring: { segs: Object.entries(st).map(([l, v]) => ({ v, l, c: cols[l] })), center: String(cs.length), sub: 'returned assets' } };
}
function figures(per) {
  const n = per === '30' ? 1 : per === '90' ? 3 : 12, MONTHS = g('MONTHS'), mi0 = MONTHS.length - n;
  const all = call('visRows'), rows = all.filter((x) => x.mi >= mi0), rc = rows.filter((x) => x.status === 'reconciled');
  const sc = call('ccScope'), open = sc.all.filter((c) => c._st === 'approval' || c._st === 'reeval');
  const prev = all.filter((x) => x.mi >= mi0 - n && x.mi < mi0 && x.status === 'reconciled');
  const kf = (v) => call('kfmt', v), d = (a, b) => parseDelta(call('frDelta', a, b, true));
  return [
    { k: 'assets', ic: 'box', h: 'insp', v: call('fmtN', sc.all.length), l: 'Assets in scope', sub: 'returned assets now' },
    { k: 'potential', ic: 'dollar', h: 'money', v: kf(sum(open.map((c) => call('ccNet', c)))), l: 'Potential recovery', sub: open.length + ' decisions open' },
    { k: 'risk', ic: 'alert', h: 'alert', v: kf(sum(sc.all.map((c) => c._var))), l: 'Value at risk', sub: 'next 30 days if no action' },
    { k: 'recovery', ic: 'trend', h: 'int', v: kf(sum(rc.map((x) => x.actual))), l: 'Net recovery', sub: rc.length + ' reconciled', delta: d(sum(rc.map((x) => x.actual)), sum(prev.map((x) => x.actual))) },
    { k: 'avoided', ic: 'layers', h: 'dec', v: kf(sum(rc.map((x) => x.avoided))), l: 'New purchases avoided', sub: 'confirmed avoided spend', delta: d(sum(rc.map((x) => x.avoided)), sum(prev.map((x) => x.avoided))) },
    { k: 'variance', ic: 'scale', h: 're', v: kf(sum(rc.map((x) => x.actual - x.p50))), l: 'Predicted against actual', sub: 'actual minus P50' },
  ];
}
const FR_REP = () => g('FR_REP');
const reports = () => FR_REP().filter((r) => r.ok()).map(({ id, t, ic, h, d }) => ({ id, t, ic, h, d }));
function reportRows(id, tenant, period) {
  const r = FR_REP().find((x) => x.id === id);
  if (!r) return [[]];
  const t0 = S.frRepT, p0 = S.frRepP;
  S.frRepT = tenant; S.frRepP = period;
  try { return r.rows(); } finally { S.frRepT = t0; S.frRepP = p0; }
}

// ---------------------------------------------------------------- command.ts
const SECTIONS = ['kpis', 'exceptions', 'aome', 'handed', 'approvals', 'outcomes', 'charts', 'actions', 'signals', 'value', 'health'];
const ccLayout = () => call('ccLayout');
const ccSection = (a) => call('ccSec', ccLayout(), { a });
const ccKeys = (L) => L.kpis.filter((x) => g('FEAT').uplift || x !== 'uplift');
const series = (f) => call('ccSeries', f, call('visRows'));
const delta = (s) => call('ccDelta', s);
const ccNet = (c) => (c.recommendation ? c.recommendation.net : 0);
const rbPath = (p) => call('rbPath', p);
const kfmt = (n) => call('kfmt', n);
function ccMetrics(rows) {
  const m = call('metrics', rows);
  return { act: m.act, base: m.base, uplift: m.uplift, avoided: m.avoided, days: m.days || null, rcCount: m.rc.length, p50: sum(m.rc.map((r) => r.p50)), co2e: sum(m.rc.map((r) => r.co2e)) };
}
function kpiTiles(keys, sc, rows) {
  const m = call('metrics', rows), acct = S.acct;
  const st = (x) => sc.all.filter((c) => c._st === x), ap = st('approval');
  const open = sc.all.filter((c) => c._st === 'approval' || c._st === 'reeval'), pot = sum(open.map(ccNet)), vr = sum(sc.all.map((c) => c._var));
  const sCnt = () => series(() => 1), sPred = () => series((r) => Math.max(0, r.p50)),
    sUp = () => series((r) => (r.status === 'reconciled' ? r.actual - r.baseline : 0)), sAct = () => series((r) => (r.status === 'reconciled' ? r.actual : 0));
  const cl = ap.filter((c) => c._left < 5).length, gaps = sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp').length, yp = sum(m.rc.map((r) => r.p50));
  const fmtN = g('fmtN');
  const pick = (arg) => ({ kind: 'pick', arg }), go = (to) => ({ kind: 'go', to }), sec = (x) => ({ kind: 'section', sec: x });
  const SCROLL = { ccVar: 'kpis', ccApprovals: 'approvals', ccAome: 'aome', ccHanded: 'handed', ccSignals: 'signals' };
  const k = (key, cls, icon, label, val, sub, d, sp, act, tip) => ({ key, cls, icon, label, val, sub, delta: d, spark: sp, act, tip });
  const riskPct = pot ? Math.round(vr / Math.max(1, pot + sum(sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp' || c._st === 'noroute').map((c) => c._val))) * 100) : 0;
  const D = {
    scope: () => k('scope', '', 'batch', 'Assets in scope', fmtN(sc.all.length), sum(sc.all.map((c) => c.qty)).toLocaleString() + ' units · vs prior month', delta(sCnt()), sCnt(), { kind: 'clear' }, 'Returned assets matching the filters. The change compares closed decisions this month with last month.'),
    awaiting: () => k('awaiting', 'y', 'check', 'Awaiting approval', fmtN(ap.length), kfmt(sum(ap.map(ccNet))) + ' predicted net · with an Approver', null, null, pick('stage:approval'), 'Decisions you prepared that now wait for an Approver. Select to filter the table.'),
    awaitVal: () => k('awaitVal', 'ok', 'check', 'Awaiting approval', kfmt(sum(ap.map(ccNet))), ap.length + ' decisions · predicted net', null, null, pick('stage:approval'), 'Predicted net recovery of decisions waiting for your approval. Select to filter the table.'),
    gaps: () => k('gaps', 'bad', 'audit', 'Evidence gaps', fmtN(gaps), 'assets cannot be routed yet', null, null, pick('stage:need'), 'Assets waiting for inspection or missing evidence. They cannot get a recommendation until it arrives.'),
    closing: () => k('closing', cl ? 'bad' : 'ok', 'flag', 'Closing within 5 days', fmtN(cl), 'decision windows · act first', null, null, pick('due:d5'), 'Decisions awaiting approval whose window closes in under 5 days.'),
    potential: () => k('potential', 'ok', 'analytics', 'Potential recovery value', kfmt(pot), open.length + ' decisions open · predicted net', delta(sPred()), sPred(), pick('stage:approval'), 'Predicted net recovery of decisions that still need a person: awaiting approval plus re-evaluation. Select to filter the table.'),
    risk: () => k('risk', 'bad', 'flag', 'Value at risk', kfmt(vr), riskPct + '% of open value if no action', null, null, sec(SCROLL.ccVar), 'Predicted recovery value on open returns that would be lost over the next 30 days if nobody acts: missing evidence, condition getting worse, delayed approval, falling market prices or capacity limits. Select to see the breakdown by reason.'),
    inbox: () => { const n = call('inboxReqs').length; return k('inbox', n ? 'y' : 'ok', 'access', 'Requests waiting', fmtN(n), 'tenant access and MCP proposals', null, null, sec('approvals'), 'Requests in the scopes you can decide. Select to open the Approvals inbox.'); },
    inspq: () => k('inspq', '', 'audit', 'Inspection queue', fmtN(st('await_insp').length), 'assets awaiting inspection', null, null, pick('stage:await_insp'), 'Returned assets with no inspection yet. Select to filter the table.'),
    gatefail: () => { const n = sc.all.filter((c) => c.blocked).length; return k('gatefail', n ? 'bad' : 'ok', 'flag', 'Failed gates', fmtN(n), 'exceptions waiting for evidence', null, null, pick('stage:need'), 'Cases where an eligibility gate failed or evidence is missing. No route is approvable until it passes.'); },
    graded: () => { const gr = sc.all.filter((c) => c.grade), ab = gr.filter((c) => c.grade === 'A' || c.grade === 'B').length; return k('graded', 'ok', 'check', 'Graded A or B', (gr.length ? Math.round(ab / gr.length * 100) : 0) + '%', ab + ' of ' + gr.length + ' graded assets', null, null, go('product/received'), 'Share of inspected assets in the top two condition grades.'); },
    parts: () => { const asParts = g('asParts'), ah = g('assetHealth'); const n = sc.all.filter((c) => asParts(c, ah(c)).some((p) => p.st === 'Backorder')).length; return k('parts', n ? 'bad' : 'ok', 'pump', 'Parts on backorder', fmtN(n), 'assets with a part on backorder', null, null, go('product/received'), 'Assets with at least one component on backorder.'); },
    net: () => k('net', 'ok', 'analytics', 'Net recovery', kfmt(m.act), m.rc.length + ' reconciled decisions · ' + S.cc.months + ' months', delta(sAct()), sAct(), go('analytics/waterfall'), 'Actual net recovery on reconciled decisions in the period. Same as Analytics when filters match.'),
    uplift: () => k('uplift', 'y', 'trend', 'Uplift vs baseline', '+' + kfmt(m.uplift), 'closed decisions · ' + (m.base ? '+' + ((m.act / m.base - 1) * 100).toFixed(0) + '%' : '—') + ' vs sell-or-scrap', delta(sUp()), sUp(), go('analytics'), 'Additional net recovery on reconciled decisions compared with the sell-or-scrap baseline. Same number as Analytics.'),
    yield: () => k('yield', '', 'check', 'Recovery yield', (yp ? Math.round(m.act / yp * 100) : 0) + '%', 'actual ÷ predicted on reconciled', null, null, go('analytics/predicted'), 'Actual net recovery divided by the predicted P50 on the same reconciled decisions.'),
    avoided: () => k('avoided', 'ok', 'export', 'Avoided spend', kfmt(m.avoided), 'ERP-confirmed purchases not made', null, null, go('analytics'), 'Purchases avoided by redeploying assets or using recovered parts, confirmed in ERP.'),
    co2m: () => k('co2m', 'ok', 'leaf', 'CO₂e avoided', (sum(m.rc.map((r) => r.co2e)) / 1000).toFixed(0) + ' t', 'estimated on reconciled decisions', null, null, go('analytics/sustain'), 'Estimated embodied carbon avoided on reconciled decisions. Measured values are on Analytics.'),
    ihealth: () => { const t = call('hhTotals'); return k('ihealth', t.pct >= 95 ? 'ok' : 'bad', 'integration', 'Integration health', t.pct.toFixed(1) + '%', 'successful syncs and events · 24 h', null, null, go('integration/map'), 'Share of syncs and events in the last 24 hours that succeeded.'); },
    srcattn: () => { const l = g('SOURCES').filter((x) => x.status === 'stale' || x.status === 'unavailable'); return k('srcattn', l.length ? 'bad' : 'ok', 'flag', 'Sources needing attention', fmtN(l.length), l.map((x) => x.name).join(', ') || 'all sources fresh', null, null, go('integration/map'), 'Sources that are stale or not connected.'); },
    wffail: () => { call('wfInit'); const wfStat = g('wfStat'); const n = S.wf.list.filter((w) => wfStat(w) === 'failing').length; return k('wffail', n ? 'bad' : 'ok', 'play', 'Failing workflows', fmtN(n), 'published, last run failed', null, null, go('integration/studio'), 'Published workflows whose last run failed.'); },
    conf: () => { const n = g('CONFLICTS').filter((c) => c.status === 'open').length; return k('conf', n ? 'bad' : 'ok', 'integration', 'Open conflicts', fmtN(n), 'systems that disagree', null, null, go('integration/conflicts'), 'Records where two systems disagree. Dependent routes stay held until resolved.'); },
    aome: () => { const n = call('aomeItems').length; return k('aome', n ? 'y' : 'ok', 'flag', 'Actions on me', fmtN(n), 'items whose next step is yours', null, null, sec('aome'), 'Everything waiting on you: notifications, requests, cases to submit, approve, inspect or confirm. Select to open Actions on me.'); },
    whcases: () => k('whcases', '', 'batch', 'Assets at ' + (acct.warehouse || 'your site'), fmtN(sc.all.length), sum(sc.all.map((c) => c.qty)).toLocaleString() + ' units · current location', null, null, go('product/received'), 'Returned assets whose current location is your warehouse.'),
    handed: () => { const n = sc.all.filter((c) => c.stage === 'approved' || c.stage === 'executing').length; return k('handed', '', 'integration', 'Handed off', fmtN(n), 'with enterprise systems · awaiting outcome', null, null, sec('handed'), 'Approved instructions sent to ERP, EAM or WMS that have not reported an outcome yet.'); },
    capwh: () => { const w = acct.warehouse || 'Warehouse 1', cap = g('CC_CAP')[w], p = (sc.util[w] || 0) / cap; return k('capwh', p >= 0.85 ? 'bad' : 'ok', 'flag', 'Capacity used', Math.round(p * 100) + '%', (sc.util[w] || 0) + ' of ' + cap + ' planned slots', null, null, sec('signals'), 'Utilisation of your warehouse against its configured planning capacity.'); },
    props: () => { const l = call('myReqs').filter((r) => r.kind === 'mcp'); return k('props', 'y', 'mcp', 'My MCP proposals', fmtN(l.filter((r) => r.status === 'pending').length) + ' pending', l.filter((r) => r.status === 'approved').length + ' approved · ' + l.filter((r) => r.status === 'declined').length + ' declined', null, null, go('mcp/proposals'), 'Servers you proposed and their review status.'); },
  };
  return keys.map((x) => D[x]());
}
const stageSlices = (sc) => g('CC_STAGES').map(([k, label, color]) => ({ k: 'stage:' + k, label, v: sc.all.filter((x) => x._st === k).length, color }));
const dueSlices = (sc) => g('CC_DUE').map(([k, label, color]) => ({ k: 'due:' + k, label, v: sc.act.filter((x) => x._due === k).length, color }));
function routeBars(sc) {
  return g('ROUTES').map((r) => {
    const a = sc.all.filter((c) => c.recommendation && c.recommendation.id === r.id);
    return { id: r.id, label: r.short, v: sum(a.map((c) => c.qty)), net: sum(a.map(ccNet)), color: r.color };
  }).filter((x) => x.v > 0);
}
const VAR_COL = { 'Delayed approval': 'var(--bad)', 'Condition deterioration': '#D9651E', 'Missing evidence': '#D4A800', 'Market price decline': 'var(--chart4)', 'Capacity constraints': 'var(--chart5)' };
const VAR_TIP = {
  'Delayed approval': 'Decisions whose window is closing. The offer or demand can lapse.',
  'Condition deterioration': 'Monthly value decay of the asset class while it waits.',
  'Missing evidence': 'Value of assets that cannot be routed yet. Estimated from similar closed decisions.',
  'Market price decline': 'Resale recommendations priced from stale market comparables.',
  'Capacity constraints': 'Repair-centre load is above 75%, so prep may slip.',
};
function varReasons(sc) {
  const reasons = g('CC_REASONS'), by = {};
  reasons.forEach((r) => (by[r] = 0));
  sc.all.forEach((c) => Object.keys(c._risk).forEach((k) => (by[k] += c._risk[k])));
  const tot = sum(Object.values(by)) || 1, mx = Math.max(1, ...Object.values(by));
  return reasons.map((r) => ({ reason: r, v: by[r], pct: Math.round(by[r] / tot * 100), w: by[r] / mx * 100, color: VAR_COL[r], tip: VAR_TIP[r] }));
}
function comboData(rows, months) {
  const rc = rows.filter((r) => r.status === 'reconciled'), out = [];
  for (let mi = 12 - months; mi < 12; mi++) {
    const p = sum(rc.filter((r) => r.mi === mi).map((r) => r.p50)), a = sum(rc.filter((r) => r.mi === mi).map((r) => r.actual));
    out.push({ mi, p, a, y: p ? a / p * 100 : 0 });
  }
  return out;
}
const ICON_KEYS = ['flag', 'audit', 'trend', 'refresh', 'pump', 'integration'];
function signals(sc) {
  const ICON = g('ICON');
  return call('ccSignals', sc).filter((x) => x.act.indexOf('go:') !== 0 || rbPath(x.act.slice(3))).map((x) => ({ ...x, ic: ICON_KEYS.find((k) => ICON[k] === x.ic) ?? 'flag' }));
}
function capacity(sc) {
  const CAP = g('CC_CAP'), LBL = g('CAP_LBL');
  return Object.keys(CAP).map((k) => {
    const u = sc.util[k] || 0, p = u / CAP[k];
    return { k, label: LBL[k] || k, u, cap: CAP[k], p, color: p >= 0.9 ? 'var(--bad)' : p >= 0.75 ? '#D4A800' : 'var(--ok)', msg: p >= 0.9 ? 'Over limit risk' : p >= 0.75 ? 'Tight' : 'Within limit' };
  });
}
function healthStrip() {
  const t = call('hhTotals'), st = { live: 0, stale: 0, manual: 0, unavailable: 0 };
  g('SOURCES').forEach((x) => st[x.status]++);
  return { pct: t.pct, live: st.live, stale: st.stale, manual: st.manual, unavailable: st.unavailable };
}
function insights(sc) {
  const o = [], cl = sc.all.filter((c) => c._st === 'approval' && c._left < 5).length, ap = sc.all.filter((c) => c._st === 'approval').length;
  if (ap) o.push(['stage:approval', ap + ' decisions await approval' + (cl ? ', ' + cl + ' close within 5 days' : '')]);
  const by = {};
  sc.all.forEach((c) => Object.keys(c._risk).forEach((k) => (by[k] = (by[k] || 0) + c._risk[k])));
  const tot = sum(Object.values(by)), top = Object.entries(by).sort((a, b) => b[1] - a[1])[0];
  if (top) o.push(['reason:' + top[0], kfmt(tot) + ' at risk, mostly ' + top[0].toLowerCase() + ' (' + Math.round(top[1] / tot * 100) + '%)']);
  if ((call('SRC', 'mkt') || {}).status === 'stale') o.push(['route:resale', 'Market feed is stale, so resale prices carry a warning']);
  const ne = sc.all.filter((c) => c._st === 'need' || c._st === 'await_insp').length;
  if (ne) o.push(['stage:need', ne + ' assets cannot be routed until evidence arrives']);
  return o.slice(0, 4);
}
function oppRows(sc) {
  const f = S.cc, q = String(f.q).trim().toLowerCase();
  let l = f.stage && ['exec', 'approved'].includes(f.stage) ? sc.all.slice().sort((a, b) => b._score - a._score) : sc.act;
  l = l.filter((c) => (!f.stage || c._st === f.stage) && (!f.due || c._due === f.due) && (!f.reason || c._risk[f.reason] > 0)
    && (!q || (c.id + ' ' + c.assetId + ' ' + c.product + ' ' + c.owner).toLowerCase().includes(q)));
  return l;
}
function oppRow(c, sc) {
  const rid = g('rid'), CAP = g('CC_CAP');
  const r = c.recommendation;
  const trigger = c._st === 'approval' ? 'Recommendation awaiting approval' : c._st === 'reeval' ? c.reevalReason || 'Conditions changed'
    : c._st === 'need' ? 'Evidence gap: ' + (c.blocked ? c.blocked.gateName : 'condition') : c._st === 'await_insp' ? 'Awaiting inspection'
      : c._st === 'noroute' ? 'No route passed the gates' : 'In motion';
  const action = r ? r.plan || rid(r.id).name : c.blocked ? c.blocked.action : 'Request inspection';
  const cons = c.blocked ? c.blocked.owner + ' input needed' : r && r.demandStatus === 'forecast' ? 'Forecast demand only'
    : c.location === 'Repair centre' && sc.util['Repair centre'] / CAP['Repair centre'] >= 0.75 ? 'Repair capacity' : 'None';
  const btn = c._st === 'approval' ? 'Review' : c._st === 'reeval' ? 'Re-evaluate' : c._st === 'exec' || c._st === 'approved' ? 'Track' : 'Investigate';
  const conf = r ? Math.max(30, Math.min(97, Math.round((1 - (r.p90 - r.p10) / (2 * Math.max(Math.abs(r.net), 1))) * 100))) : null;
  const dl = call('addDays', g('AS_OF'), c._left);
  return { trigger, action, cons, btn, conf, deadline: call('fmtD', dl), left: c._left };
}
// The Command Center's case, as the pages read it (the CcCase interface)
const ccRec = (r) => (r ? { id: r.id, net: r.net, p10: r.p10, p90: r.p90, plan: r.plan, demandStatus: r.demandStatus } : null);
const ccCase = (c) => ({
  id: c.id, assetId: c.assetId, product: c.product, qty: c.qty, owner: c.owner, location: c.location, cls: c.cls,
  stage: c.stage, assessment: c.assessment, grade: c.grade, timing: c.timing, reevalReason: c.reevalReason,
  recommendation: ccRec(c.recommendation), chosen: ccRec(c.chosen),
  blocked: c.blocked ? { action: c.blocked.action, gateName: c.blocked.gateName, owner: c.blocked.owner } : null,
  submitted: c.submitted ? { by: c.submitted.by } : null,
  _st: c._st, _left: c._left, _risk: c._risk, _var: c._var, _val: c._val, _due: c._due, _score: c._score, _pri: c._pri,
});
function exRows(sc) {
  const exNote = g('exNote'), am = g('asModel');
  return call('ccExRows', sc).map((x) => ({
    id: x.id, base: x.base, wh: x.wh, title: x.title, value: x.value, count: x.count, sev: x.sev, trend: x.trend, go: x.go,
    items: x.items.map((i) => ({ id: i.c.id, model: am(i.c), v: i.v })),
    note: exNote(x) ?? null,
    owner: call('exOwner', x),
  }));
}
const handedRows = () => call('handedRows').map((x) => ({ id: x.c.id, label: x.a.label, sys: x.a.sys, ref: x.last ? x.last.ack.ref : null, age: x.age, over: x.over }));
function awaitingApproval() {
  const ap = call('opScoped').filter((c) => c.stage === 'awaiting_approval');
  return { decider: S.deleg.decisions ? 'Approver' : 'Admin', rows: ap.map((c) => ({ id: c.id, location: c.location, plan: c.recommendation ? c.recommendation.plan : '—', submitted: !!c.submitted })) };
}
function outcomesToConfirm() {
  const v = call('visCases');
  return {
    rows: v.filter((c) => c.stage === 'closed' && !c.outcome).map((c) => { const r = c.chosen || c.recommendation; return { id: c.id, product: c.product, assetId: c.assetId, plan: r ? r.plan : '—', net: r ? r.net : null }; }),
    done: v.filter((c) => c.outcome).length,
  };
}
const toReq = (r) => ({ ...r, kindLabel: g('REQ_KIND')[r.kind], canDecide: call('canDecide', r) });
function inboxScope() {
  if (S.acct?.role !== 'Approver') return null;
  return g('DELEG').filter((d) => S.deleg[d[0]]).map(g('dlab'));
}
function approvalCards() {
  const am = g('asModel'), TPL = g('STEP_TPL');
  // the facade's steps are `s[0] + ' → ' + s[1]` over STEP_TPL entries, which are step kinds (strings) in the demo:
  // the endpoint returns the kinds, and so does this file
  return call('afApprovalQueue').map((x) => ({
    id: x.c.id, plan: x.c.recommendation.plan, net: x.net, model: am(x.c), owner: x.c.owner, timing: x.c.timing || '', submittedBy: x.c.submitted.by,
    risks: x.risks.map((r) => r.text), kinds: (TPL[x.c.recommendation.id] || []).slice(),
  }));
}
function healthDetail() {
  const t = call('hhTotals'), ex = call('smExceptions'), ackKind = g('ackKind');
  return {
    ok: t.ok, warn: t.warn, bad: t.bad, run: t.run, pct: t.pct,
    hours: S.hh.map((b) => ({ ok: b.ok, warn: b.warn, bad: b.bad })),
    exceptions: ex.slice(0, 6), exceptionCount: ex.length,
    events: g('EVENTS').slice(0, 6).map((e) => ({ id: e.id, ts: e.ts, dest: e.dest, type: e.type, ack: e.ack, kind: ackKind(e.ack) })),
  };
}
const opScopeInfo = () => ({ home: call('opHome'), scope: call('opScope'), locked: !!S.acct?.warehouse });

// ---------------------------------------------------------------- the Command Center's filters
const CC_CLEAR = { site: '', cls: '', route: '', stage: '', reason: '', due: '', view: '', q: '', months: 12 };
function withFilters(f, fn) {
  Object.assign(S.cc, CC_CLEAR, f);
  S.tenant = f.tenant || 'All';
  try { return fn(); } finally { Object.assign(S.cc, CC_CLEAR); S.tenant = 'All'; }
}
const SCOPES = [{}, { site: 'Warehouse 1' }, { site: 'Repair centre', cls: 'pump' }, { cls: 'motor' }, { route: 'redeploy' }, { route: 'resale', months: 6 }, { months: 3 }, { tenant: 'Customer A' }, { tenant: 'Customer B', site: 'Warehouse 2' }];
const TABLE = [{}, { site: 'Warehouse 1' }, { tenant: 'Customer A' }, { stage: 'approval' }, { stage: 'need' }, { stage: 'exec' }, { due: 'd5' }, { reason: 'Delayed approval' }, { q: 'rt-10' }, { stage: 'approval', q: 'motor', cls: 'motor' }];

// ---------------------------------------------------------------- per account
const home = {}, command = {};
for (const id of ACCOUNTS) {
  setAcct(ACCT(id));
  const r = role(), allowed = call('allowedTenants');
  const scopes = SCOPES.filter((f) => !f.tenant || allowed.includes(f.tenant));

  // Home and the utility pages
  const acts = Object.fromEntries(['live', 'today', 'week'].map((w) => [w, activity(w)]));
  const runs = S.wf ? S.wf.runs : null;
  if (S.wf) S.wf.runs = []; // the workflow runs are synthetic (random times and record counts): see test_screens_home
  const actsNoRuns = Object.fromEntries(['live', 'today', 'week'].map((w) => [w, activity(w)]));
  if (S.wf) S.wf.runs = runs;
  const reps = reports();
  const repRows = {};
  for (const rep of reps) {
    if (rep.id === 'audit') continue; // the audit extract is the audit area's fetch log (auditEntries), served there
    repRows[rep.id] = {};
    for (const t of ['All', ...allowed]) for (const p of t === 'All' ? ['30', '90', '365'] : ['90']) repRows[rep.id][t + '|' + p] = reportRows(rep.id, t, p);
  }
  home[id] = tree({
    briefing: call('afBriefing'),
    tasks: taskItems(),
    alerts: call('frAlerts'),
    kpis: kpis(r),
    activity: acts,
    activity_without_workflow_runs: actsNoRuns,
    middle: middlePanel(r),
    figures: Object.fromEntries(['30', '90', '365'].map((p) => [p, figures(p)])),
    reports: reps,
    report_rows: repRows,
  });

  // Command Center
  const modes = r === 'Admin' ? ['operational', 'senior'] : ['operational'];
  const layout = {};
  for (const mode of modes) {
    S.ccMode = mode;
    const L = ccLayout();
    layout[mode] = L ? { layout: L, keys: ccKeys(L), sections: SECTIONS.filter((k) => ccSection(k) === k) } : null;
  }
  const kp = {}, charts = {}, exceptions = {}, actions = {};
  for (const mode of modes) {
    S.ccMode = mode;
    const L = ccLayout();
    if (!L) continue;
    kp[mode] = scopes.map((f) => withFilters(f, () => {
      const sc = call('ccScope'), rows = call('ccRows');
      return {
        filters: f,
        tiles: kpiTiles(ccKeys(L), sc, rows),
        insights: insights(sc),
        metrics: ccMetrics(rows),
        health: healthStrip(),
        counts: { cases: call('visCases').length, rows: call('visRows').length, sources: g('SOURCES').length, workflows: S.wf?.list.length ?? 0 },
      };
    }));
  }
  S.ccMode = 'operational';
  charts.list = scopes.map((f) => withFilters(f, () => {
    const sc = call('ccScope'), rows = call('ccRows');
    return {
      filters: f, stages: stageSlices(sc), due: dueSlices(sc), routes: routeBars(sc), var: varReasons(sc),
      combo: comboData(rows, S.cc.months), signals: signals(sc), capacity: capacity(sc),
    };
  }));
  exceptions.list = scopes.map((f) => withFilters(f, () => {
    const sc = call('ccScope');
    const ap = sc.all.filter((c) => c._st === 'approval').sort((a, b) => ccNet(b) - ccNet(a)).map((c) => ({ id: c.id, plan: c.recommendation ? c.recommendation.plan : null, net: ccNet(c) }));
    return { filters: f, rows: exRows(sc), awaiting: ap };
  }));
  actions.list = TABLE.filter((f) => !f.tenant || allowed.includes(f.tenant)).map((f) => withFilters(f, () => {
    const sc = call('ccScope');
    return { filters: f, rows: oppRows(sc).map((c) => ({ case: ccCase(c), ...oppRow(c, sc) })) };
  }));
  const opScopes = {};
  for (const [k, v] of [['default', undefined], ['all', '']]) {
    if (v === undefined) delete S.opScope; else S.opScope = v;
    opScopes[k] = { scope: opScopeInfo(), aome: call('aomeItems'), handed: handedRows(), awaiting: awaitingApproval() };
  }
  delete S.opScope;
  // the tenant menu (S.tenant) narrows the queues too
  const inTenant = {};
  for (const t of ['Customer A', 'Customer C'].filter((x) => allowed.includes(x))) {
    S.tenant = t;
    inTenant[t] = {
      scope: opScopeInfo(), aome: call('aomeItems'), handed: handedRows(), awaiting: awaitingApproval(), outcomes: outcomesToConfirm(),
      decisions_awaiting: call('visCases').filter((c) => c.stage === 'awaiting_approval').length, cards: approvalCards(),
    };
    S.tenant = 'All';
  }
  // no decision is submitted at the start, so the approval cards are empty: the pre-approval check (afRisks) of every
  // visible case with a recommendation is recorded for Admin, to test it on its own
  const risks = r !== 'Admin' ? undefined : Object.fromEntries(call('visCases').filter((c) => c.recommendation).map((c) => {
    const rt = g('invoke')('case.routes', { case_id: c.id }).output, ev = g('invoke')('case.evidence', { case_id: c.id }).output;
    return [c.id, call('afRisks', c, rt, ev)];
  }));
  command[id] = tree({
    risks,
    in_tenant: inTenant,
    layout, kpis: kp, charts: charts.list, exceptions: exceptions.list, actions: actions.list, op_scopes: opScopes,
    outcomes: outcomesToConfirm(),
    inbox: {
      requests: call('inboxReqs').map(toReq), scope: inboxScope(),
      decisions_awaiting: call('visCases').filter((c) => c.stage === 'awaiting_approval').length,
      cards: approvalCards(), limit: call('afLimitFor', S.acct),
    },
    health: healthDetail(),
  });
}
setAcct(null);

console.log(writeGolden('screens/home.json', home));
console.log(writeGolden('screens/command.json', command));
