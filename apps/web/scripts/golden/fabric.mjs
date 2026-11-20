// B14 golden data for the Connection Fabric, MCP & Tools, Access and Workflow Studio screens.
//
//   node apps/web/scripts/golden/fabric.mjs
//     -> fixtures/golden/screens/integration.json, screens/mcp.json, screens/access.json, screens/workflows.json
//
// What the demo's own functions return (the ones behind apps/web/src/api/integration.ts, mcp.ts, access.ts and
// workflows.ts), from a fresh copy of the demo. Values that do not depend on who is signed in are written once; what
// does (page access, which requests the account may decide, which cases behind a call or an event it may open) is
// written per account, for the 11 accounts in policy.json.
//
// The Workflow Studio's list (S.wf) is seeded with Math.random on first use, so wfInit() runs first, before anything
// else draws a random number: the file is the same on every run.
import { freshDemo, writeGolden } from '../golden-sandbox.mjs';

const g = freshDemo();
g('wfInit')();
g('hhInit')();

const S = g('S'), SOURCES = g('SOURCES'), setAcct = g('setAcct'), ACCT = g('ACCT'), canPage = g('canPage'), canRoute = g('canRoute');
const accounts = g('ACCOUNTS').map((a) => a.id);
const SECS = g('RB_SECS');
const pageAccess = () => Object.fromEntries(['integration', 'mcp', 'access'].map((p) => [p, canPage(p) ? (SECS[p] ?? []).filter((s) => canPage(p, s)) : null]));
const caseOpenable = (id) => !!g('CASE_BY_ID')[id] && canRoute({ page: 'product', a: id, b: null }) === true;

// ---------------------------------------------------------------- workflows (S.wf), with each graph built
const W = S.wf.list;
const wfDetail = {};
for (const w of W) {
  g('wfGraphOf')(w); // builds w.graph from its template and keeps the saved snapshot (what opening it does)
  wfDetail[w.id] = {
    history: g('frWfHistory')(w),
    failed_rows: g('frFailedRows')(w),
    run_counts: g('frRunCounts')(w),
    run_from_last: g('wfRunFromLast')(w),
    template: g('wfBuild')(w.tpl),
    stat: g('wfStat')(w),
  };
}

// ---------------------------------------------------------------- integration
const per = (f) => Object.fromEntries(SOURCES.map((s) => [s.id, f(s)]));
const integration = {
  sources: SOURCES,
  derived: per((s) => ({
    needs_attention: g('frNeedsAttn')(s), failing: g('frSrcFailing')(s), cred_days: g('frCredDays')(s), success: g('frSuccess')(s),
    series30: g('frSeries')(s, 30), failed7: g('frFailedRecs')(s, 7), failed30: g('frFailedRecs')(s, 30), sla: g('frSla')(s), latency: g('frLat')(s),
    sync_history: g('frSyncHist')(s), tables: g('frTblN')(s.id), fields: g('frFldN')(s.id), models: g('frSrcModels')(s),
    workflows: g('wfUsing')(s.id), channels: g('srcCh')(s), category: g('frCatOf')(s),
  })),
  integrations: g('frIntegrations')().map(({ src, c, ...x }) => ({ ...x, src: src ? src.id : null, catalog: c ? c.id : null })),
  recommendations: g('frRecs')().map(({ s, c, ...x }) => ({ ...x, source: s ? s.id : null, catalog: c ? c.id : null })),
  connected: g('frConnected')().map((s) => s.id),
  available: g('frAvail')(),
  catalog: g('CATALOG'),
  exceptions: g('smExceptions')(),
  totals: g('hhTotals')(),
  hourly: S.hh,
  activity: S.smLog,
  table_models: Object.fromEntries(Object.keys(g('TBL_MODELS')).map((k) => [k, g('tgModel')(k)])),
  canon: g('CANON'),
  canon_examples: g('CANON_EX'),
  mappings: g('MAPPINGS'),
  events: g('EVENTS'),
  conflicts: g('CONFLICTS'),
  // reference the endpoints need beside sources.json and canonical.json
  map_target: g('MAP_TARGET'), canon_pfx: g('CANON_PFX'), fr_catof: g('FR_CATOF'), fr_cats: g('FR_CATS'), fr_xtypes: g('FR_XTYPES'),
};

// ---------------------------------------------------------------- MCP & Tools
const TOOLS = g('TOOLS'), AGENTS = g('AGENTS'), TENANTS = g('TENANTS');
const ACTIONS = g('ACTIONS'), RL = g('RISK_LABEL'), order = ['read', 'draft', 'act', 'commit'];
const mcp = {
  tools: TOOLS,
  agents: AGENTS,
  hard_rules: g('HARD_RULES'),
  client_servers: g('CLIENT_SERVERS'),
  calls: g('CALLS'),
  matrix: Object.fromEntries(TENANTS.map((t) => [t, AGENTS.map((a) => ({ agent: a.id, cells: TOOLS.map((x) => ({ tool: x.id, ...g('permCell')(a, x, t) })) }))])),
  registry_tools: Object.values(ACTIONS).filter((A) => A.risk !== 'system').sort((a, b) => order.indexOf(a.risk) - order.indexOf(b.risk))
    .map((A) => ({ id: A.id, exposedAs: A.risk === 'commit' ? A.id + '.prepare' : A.id, risk: A.risk, riskLabel: RL[A.risk], perm: A.perm || 'any signed-in role', desc: A.desc })),
};

// ---------------------------------------------------------------- Access
const AF = g('AF'), RP = g('ROLE_POLICY'), roles = Object.keys(RP);
const access = {
  requests: S.reqs,
  delegations: g('DELEG').map(([k, label, desc]) => ({ k, label, desc, on: !!S.deleg[k] })),
  account_rows: g('ACCOUNTS').map((a) => {
    const P = RP[a.role], h = g('homeFor')(a.role);
    return { account: a, policy: P, tenants: P.tenantScoped ? [a.tenant].concat(S.grants[a.id] || []).join(', ') : 'All', landsOn: g('HOME_LABEL')[h] || h };
  }),
  home_label: g('HOME_LABEL'),
  idp: S.idp,
  idp_roles: g('IDP_ROLES'),
  idp_user_roles: Object.fromEntries(S.idp.users.map((u) => [u.id, g('idpRoleOf')(u)])),
  levels: g('AF_LEVELS').map(([k, label, desc]) => ({ k, label, desc })),
  auto_types: g('AF_AUTO_TYPES'),
  autonomy: Object.fromEntries(roles.map((r) => [r, Object.fromEntries(g('AF_AUTO_TYPES').map((t) => [t.k, g('afAutoLevel')(r, t.k)]))])),
  limits: Object.fromEntries(roles.map((r) => { const v = AF.cfg.limits[r]; return [r, v === Infinity || v == null ? null : v]; })),
  self_approve: !!AF.cfg.self,
  run_limits: { ...AF.cfg.max },
  agents: AGENTS.map((a) => ({ id: a.id, name: a.name, scopes: a.scopes.slice(), limit: a.limit, stopped: !!AF.cfg.off[a.id], prepared: AF.journal.filter((x) => x.prep === a.id).length })),
  hard_rules: g('HARD_RULES'),
  metrics: g('afMetrics')(),
};

// ---------------------------------------------------------------- per account
const perAccount = {};
for (const id of accounts) {
  setAcct(ACCT(id));
  perAccount[id] = {
    pages: pageAccess(),
    can_decide: Object.fromEntries(S.reqs.map((r) => [r.id, g('canDecide')(r)])),
    inbox_requests: g('inboxReqs')().map((r) => r.id),
    calls_openable: g('CALLS').map((c) => caseOpenable(c.caseId)),
    events_openable: g('EVENTS').map((e) => !!(e.caseId && g('CASE_BY_ID')[e.caseId] && g('rbPath')('product/' + e.caseId))),
  };
}
setAcct(null);

const workflows = { starting: W, runs: S.wf.runs, attention: g('frWfAttn')(), detail: wfDetail };

console.log('wrote', writeGolden('screens/integration.json', { ...integration, accounts: perAccount }));
console.log('wrote', writeGolden('screens/mcp.json', { ...mcp, accounts: perAccount }));
console.log('wrote', writeGolden('screens/access.json', { ...access, accounts: perAccount }));
console.log('wrote', writeGolden('screens/workflows.json', { ...workflows, accounts: Object.fromEntries(accounts.map((a) => [a, { pages: perAccount[a].pages }])) }));
