// B14 golden data for analytics, audit, reference data, the menu and the data checks (docs/backend-steps.md, B14).
//
//   node frontend/scripts/golden/analytics_audit.mjs
//
// Writes, from a fresh copy of the demo (its starting state), for every account:
//   fixtures/golden/screens/reference.json  the static lists every page reads (MONTHS, ROUTES, CLASSES, NAV, PAGES ...)
//   fixtures/golden/screens/analytics.json  analyticsRows(f) as row ids, metrics(rows), modelStats, analytics.models
//   fixtures/golden/screens/audit.json      auditEntries() (in full once, as ids per account), auditGaps(), comments
//   fixtures/golden/screens/nav.json        navigation() and navBadges() as frontend/src/api/nav.ts builds them, frCounts
//   fixtures/golden/screens/checks.json     runInvariants() (the Data Checks page) per account
// Each value is what the facade functions in frontend/src/api/{analytics,audit,nav,home}.ts return, computed by the same
// engine functions with the same arguments.
import { freshDemo, writeGolden } from '../golden-sandbox.mjs';

const g = freshDemo();
const setAcct = g('setAcct'), ACCT = g('ACCT'), S = g('S'), invoke = g('invoke');
const ACCOUNTS = g('ACCOUNTS').map((a) => a.id);
const as = (id, fn, tenant = 'All') => {
  setAcct(ACCT(id));
  S.tenant = tenant;
  try { return fn(); } finally { S.tenant = 'All'; }
};

// ---------------------------------------------------------------- reference: static lists (no account, no state)
const STATIC = [
  // analytics, journey steps
  'MONTHS', 'ROUTES', 'MODELS', 'CLASSES', 'CLS_ICON', 'EQUIP', 'COMPS', 'JSTEPS', 'JSTEPS_AF', 'GATES',
  // world
  'TENANTS', 'SITES', 'FACILITIES', 'AS_OF',
  // access and session
  'ROLE_POLICY', 'RB_AV', 'HOME_LABEL', 'IDP_ROLES', 'DELEG', 'AF_LEVELS', 'AF_LV_RANK', 'AF_AUTO_TYPES', 'HARD_RULES',
  'PERM_ALIAS', 'RB_SECS',
  // case and product
  'AF_STAGES', 'ST_PH', 'AF_BADGE_TIP', 'DIAG', 'EX_FX', 'EX_MC', 'JG', 'JG_NEXT', 'RATE_CARD', 'RG_CONT', 'CC_EST',
  // command center
  'CAP_LBL', 'CC_CAP', 'CC_DESC', 'CC_DUE', 'CC_REASONS', 'CC_STAGES', 'CC_LAYOUT', 'REQ_KIND', 'STEP_TPL', 'FEAT',
  // home, menu, region
  'NAV', 'PAGES', 'NOWF', 'FR_AK', 'FR_MODES', 'FR_MODH', 'FR_NOTIF', 'FR_REP', 'FR_ST', 'FR_TG', 'AF_STARTERS', 'AF_INTENTS',
  'RG_CUR', 'RG_LANG', 'RG_TZ', 'I18N',
  // integration
  'AUTH_OPTS', 'CANON', 'CANON_EX', 'CANON_PFX', 'CATALOG', 'CONN_METHODS', 'FR_AUTH', 'FR_CATS', 'FR_DEC', 'FR_INT_KIDS',
  'FR_INT_SUB', 'FR_SAMPLE', 'FR_XTYPES', 'SAMPLE_CSV', 'SRC_CATS', 'SRC_CAT_NOTE', 'SRC_TYPES', 'TBL_AVAIL', 'TBL_MODELS',
  // mcp and orchestration
  'TOOLS', 'RISK_LABEL', 'AF_EVALS', 'AF_STAGE_AGENT', 'HANDOFF_MODEL', 'LR_MODELS', 'RUN_ST',
  // workflows
  'ACT_TYPES', 'CH_ARR', 'CH_DEL', 'CH_ING', 'DELIVER', 'FR_CATOF', 'FR_SRCG', 'FR_XF', 'FXD', 'MAP_TARGET', 'SH', 'WF_STC',
  'WF_STL', 'XF',
];
const reference = Object.fromEntries(STATIC.map((n) => [n, g(n)]));
reference.JMAP = Array.from({ length: 13 }, (_, n) => g('jmap')(n)); // the demo's jmap(n) for n = 0..12 (n itself beyond)
writeGolden('screens/reference.json', reference);

// ---------------------------------------------------------------- analytics
const FILTERS = [
  {},
  { tenant: 'Customer A' },
  { tenant: 'Customer B' },
  { cls: 'motor' },
  { cls: 'it' },
  { route: 'redeploy' },
  { route: 'exit' },
  { from: 3, to: 8 },
  { from: 11, to: 11 },
  { model: 'v1.0' },
  { model: 'v1.3' },
  { tenant: 'Customer C', cls: 'pump', route: 'resale', from: 2, to: 10, model: 'v1.2' },
].map((f) => ({ tenant: '', cls: '', route: '', from: 0, to: 11, model: '', ...f }));
const TOP_TENANTS = ['All', 'Customer A', 'Customer B'];

function analyticsRows(f) {
  return g('visRows')().filter((r) => (!f.tenant || r.tenant === f.tenant) && (!f.cls || r.cls === f.cls) && (!f.route || r.route === f.route) &&
    r.mi >= f.from && r.mi <= f.to && (!f.model || r.model === f.model));
}
// metrics(rows).rc is rows.filter(r => r.status === 'reconciled'): recorded as its length (the rows are recorded already)
const metricsOf = (rows) => { const { rc, ...m } = g('metrics')(rows); return { ...m, rc_n: rc.length }; };
const analytics = {
  filters: FILTERS,
  model_stats: g('MODELS').map((m) => g('modelStats')(m.v)),
  telemetry_unavailable: (g('SRC')('iot') ?? { status: 'unavailable' }).status === 'unavailable',
  accounts: {},
};
for (const id of ACCOUNTS) {
  analytics.accounts[id] = {
    views: TOP_TENANTS.flatMap((top) => FILTERS.map((f, k) => as(id, () => {
      const rows = analyticsRows(f);
      return { filter: k, tenant_filter: top, row_ids: rows.map((r) => r.id), metrics: metricsOf(rows) };
    }, top))),
    models: as(id, () => { const r = invoke('analytics.models', {}); return r.ok ? { ok: true, output: r.output } : { ok: false, error: r.error }; }),
  };
}
writeGolden('screens/analytics.json', analytics);

// ---------------------------------------------------------------- audit
const entriesAll = as('admin', () => g('auditEntries')());
const byId = Object.fromEntries(entriesAll.map((x) => [x.id, x]));
// every gap's provenance record (status "unavailable" and the reason), for the data trace, as provenanceOf() gives it
const gapProvenance = as('admin', () => g('auditGaps')().map(({ c, e }) => g('provFor')(c, e)));
const audit = { entries: entriesAll, gap_provenance: gapProvenance, comments: S.cm, accounts: {} };
for (const id of ACCOUNTS) {
  audit.accounts[id] = {};
  for (const top of TOP_TENANTS) {
    const e = as(id, () => g('auditEntries')(), top);
    for (const x of e) if (!byId[x.id]) throw new Error('entry ' + x.id + ' not in the admin list');
    audit.accounts[id][top] = {
      entry_ids: e.map((x) => x.id),
      gaps: as(id, () => g('auditGaps')().map(({ c, e }) => [c.id, e.k]), top),
    };
  }
}
writeGolden('screens/audit.json', audit);

// ---------------------------------------------------------------- the menu (frontend/src/api/nav.ts, same code)
function navigation() {
  const NAV = g('NAV'), visible = g('frVisible'), kidsOf = g('navKids'), hrefOf = g('navHref');
  return NAV.filter(visible).map((x) => {
    const kids = x.leaf ? [] : kidsOf(x);
    const first = x.mode ? (kids.some((k) => k[0] === 'received') ? 'received' : kids[0]?.[0] ?? '') : '';
    return {
      id: x.id, label: x.label, sub: x.sub, icon: x.icon, section: x.sec ?? '', leaf: !!x.leaf,
      href: x.leaf ? '#/' + x.id : hrefOf(x, first),
      kids: kids.map(([id, label, sub, badge]) => ({ id, label, sub, href: hrefOf(x, id), badge })),
    };
  });
}
function navBadges() {
  const conf = g('CONFLICTS').filter((c) => c.status === 'open').length;
  const srcissue = g('SOURCES').filter((s) => s.status === 'stale' || s.status === 'unavailable').length;
  const wffail = S.wf ? S.wf.list.filter((w) => w.status === 'published' && w.last?.state === 'failed').length : 0;
  const inbox = S.acct ? g('inboxReqs')().length : 0;
  const awaiting = g('visCases')().filter((c) => c.stage === 'awaiting_approval').length;
  const canPage = g('canPage');
  return {
    awaiting, inbox: canPage('command', 'approvals') ? inbox : 0, integration: canPage('integration', 'conflicts') ? conf : 0,
    sections: { conf, srcissue, wffail, inbox },
  };
}
g('wfInit')(); // the workflows the demo seeds on first use (S.wf), so wffail counts them as the menu does
const nav = { accounts: {} };
for (const id of ACCOUNTS) {
  nav.accounts[id] = as(id, () => ({ navigation: navigation(), badges: navBadges(), tasks: g('frCounts')().tasks }));
}
S.ccMode = 'senior';
nav.admin_senior = as('admin', () => navigation());
S.ccMode = 'operational';
writeGolden('screens/nav.json', nav);

// ---------------------------------------------------------------- the data checks
const checks = { accounts: {} };
for (const id of ACCOUNTS) checks.accounts[id] = as(id, () => g('runInvariants')());
setAcct(null);
writeGolden('screens/checks.json', checks);
console.log('[golden] screens: reference, analytics, audit, nav, checks written');
