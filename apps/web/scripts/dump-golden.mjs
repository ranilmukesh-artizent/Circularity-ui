// B1 (docs/BACKEND_STEPS.md): dump what the static demo computes, as golden JSON for the Python backend's parity tests.
//
//   node apps/web/scripts/dump-golden.mjs            -> fixtures/golden/*.json at the repository root
//
// The demo's script runs headless in a sandbox with inert DOM shims, the clock pinned to its as-of time
// (7 Oct 2026 09:00 UTC) and Math.random seeded, so two runs give identical files.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const out = join(root, 'fixtures/golden');
const html = readFileSync(process.env.LEGACY_HTML ?? join(root, 'index.html'), 'utf8');
let src = /<script>([\s\S]*)<\/script>\s*<\/body>/.exec(html)[1];
src = src.replace(/^afBoot\(\);S\.acct=sessionLoad\(\);.*$/m, '').replace(/^setInterval\(\(\)=>\{try\{smTick\(\)\}.*$/m, '');

// ---------- sandbox ----------
const T0 = Date.parse('2026-10-07T09:00:00Z');
class FixedDate extends Date {
  constructor(...a) { if (a.length === 0) super(T0); else super(...a); }
  static now() { return T0; }
}
const prelude = `
class El{constructor(){this.classList={add(){},remove(){},toggle(){return false},contains(){return false}};this.dataset={};this.style={setProperty(){}};this.children=[];this.parentNode=null;this.innerHTML='';this.textContent='';this.value=''}
 querySelector(){return null}querySelectorAll(){return[]}closest(){return null}matches(){return false}addEventListener(){}removeEventListener(){}appendChild(c){return c}remove(){}setAttribute(){}getAttribute(){return null}removeAttribute(){}contains(){return false}focus(){}blur(){}scrollIntoView(){}getBoundingClientRect(){return{top:0,left:0,width:0,height:0,right:0,bottom:0}}insertAdjacentHTML(){}}
var document={documentElement:new El(),body:new El(),head:new El(),activeElement:null,title:'',querySelector(){return null},querySelectorAll(){return[]},getElementById(){return null},createElement(){return new El()},addEventListener(){},removeEventListener(){},hidden:false,visibilityState:'visible'};
var __store={};var localStorage={getItem:k=>k in __store?__store[k]:null,setItem:(k,v)=>{__store[k]=String(v)},removeItem:k=>{delete __store[k]}};var sessionStorage=localStorage;
var location={search:'',hash:'',href:'http://localhost/',pathname:'/',reload(){}};
var history={replaceState(){},pushState(){},back(){}};var navigator={userAgent:'node',clipboard:{writeText:async()=>{}},language:'en-GB'};
var window=globalThis;var addEventListener=()=>{};var removeEventListener=()=>{};var scrollTo=()=>{};var scrollY=0;var innerWidth=1280;var innerHeight=800;
var matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});var getComputedStyle=()=>({getPropertyValue:()=>''});
var requestAnimationFrame=f=>0;var cancelAnimationFrame=()=>{};var ResizeObserver=class{observe(){}disconnect(){}};var IntersectionObserver=ResizeObserver;var MutationObserver=ResizeObserver;
var CSS={escape:s=>s};var alert=()=>{};var confirm=()=>true;
(function(){let s=20261007;Math.random=function(){s=(s+0x6D2B79F5)|0;let t=Math.imul(s^(s>>>15),1|s);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296}})();
`;
// a fresh copy of the demo in its own sandbox; returns a lookup of its globals
function freshDemo() {
  const ctx = vm.createContext({
    console, Date: FixedDate, Intl, TextEncoder, crypto: globalThis.crypto, performance: { now: () => 0 },
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  });
  vm.runInContext(prelude + src + '\n;globalThis.__get=function(n){return eval(n)};', ctx, { timeout: 60000 });
  return (n) => ctx.__get(n);
}
const g = freshDemo();

// ---------- plain JSON: drop functions, break cycles, dates as ISO, numbers rounded to 1e-6 ----------
function plain(v, seen = new WeakMap(), path = '$') {
  if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
  if (typeof v === 'number') return Number.isFinite(v) ? Math.round(v * 1e6) / 1e6 : String(v);
  if (typeof v === 'function' || typeof v === 'undefined' || typeof v === 'symbol') return undefined;
  if (v instanceof Date) return isNaN(v) ? null : v.toISOString();
  if (v instanceof Set) return plain([...v], seen, path);
  if (v instanceof Map) return plain(Object.fromEntries(v), seen, path);
  if (seen.has(v)) return { $ref: seen.get(v) };
  seen.set(v, path);
  if (Array.isArray(v)) return v.map((x, i) => plain(x, seen, `${path}[${i}]`) ?? null);
  const o = {};
  for (const k of Object.keys(v).sort()) {
    const x = plain(v[k], seen, `${path}.${k}`);
    if (x !== undefined) o[k] = x;
  }
  return o;
}
const files = {};
const put = (name, data) => { files[name] = plain(data); };

// ---------- the world ----------
put('world.json', {
  as_of: g('AS_OF'), months: g('MONTHS'), tenants: g('TENANTS'), sites: g('SITES'), facilities: g('FACILITIES'),
  routes: g('ROUTES'), route_mix: g('ROUTE_MIX'), models: g('MODELS'), gates: g('GATES'), classes: g('CLASSES'), grade_factor: g('GRADE_F'),
});
put('cases.json', g('CASES'));
put('decisions.json', g('ROWS'));
put('sources.json', { types: g('SRC_TYPES'), sources: g('SOURCES') });
put('canonical.json', { models: g('CANON'), mappings: g('MAPPINGS') });
put('events.json', { events: g('EVENTS'), conflicts: g('CONFLICTS') });
put('tools.json', { tools: g('TOOLS'), agents: g('AGENTS'), hard_rules: g('HARD_RULES'), client_servers: g('CLIENT_SERVERS') });
put('policy.json', {
  role_policy: g('ROLE_POLICY'), accounts: g('ACCOUNTS'), perm_acts: g('PERM_ACTS'), perm_alias: g('PERM_ALIAS'), sections: g('RB_SECS'),
  signin_ids: g('SIGNIN_IDS'), signin_domain: g('SIGNIN_DOMAIN'),
});
put('actions_catalog.json', Object.values(g('ACTIONS')).map(({ id, title, desc, risk, perm, scope, input, verb, dupText, idem }) => ({ id, title, desc, risk, perm, scope, input, verb: verb ?? null, dup_text: dupText ?? null, idempotent: !!idem })));

// ---------- per-account answers: access, scope and headline figures ----------
const setAcct = g('setAcct'), ACCT = g('ACCT'), invoke = g('invoke'), S = g('S');
const read = (id, input = {}) => { const r = invoke(id, input); return r.ok ? r.output : { error: r.error }; };
const perms = Object.keys(g('PERM_ACTS')).concat('approve.mcp', 'approve.tenantAccess');
const pages = Object.keys(g('PAGES'));
const accounts = {};
for (const a of g('ACCOUNTS')) {
  setAcct(ACCT(a.id));
  const cases = read('cases.list', { limit: 1000 });
  accounts[a.id] = {
    can: Object.fromEntries(perms.map((p) => [p, g('can')(p)])),
    pages: Object.fromEntries(pages.map((p) => [p, (g('RB_SECS')[p] ?? []).filter((s) => g('canPage')(p, s)).concat(g('canPage')(p) ? [''] : [])])),
    allowed_tenants: g('allowedTenants')(),
    home: g('homeOf')(S.acct),
    visible_case_ids: g('myCases')().map((c) => c.id).sort(),
    cases_total: cases.total, cases_value_total: cases.value_total,
    counts: g('frCounts')(),
    kpis: typeof g('frKpis') === 'function' ? g('frKpis')(a.role) : null,
    inbox: read('inbox.get'),
  };
}
setAcct(ACCT('admin')); // the agent-layer checks (intents, safety tests) need a signed-in account, as in the demo
const invariants = g('runInvariants')();
setAcct(null);
put('figures.json', { invariants, accounts });

// ---------- a scripted RT-1048 journey: every invoke() call and its result ----------
const steps = [];
const AF_SYS = g('AF_SYS');
function call(acct, id, input, opts) {
  if (acct) setAcct(ACCT(acct));
  const r = invoke(id, input, opts);
  const c = g('CASE_BY_ID')[input.case_id];
  steps.push({ as: acct ?? 'system', action: id, input, result: r, case_after: c && { stage: c.stage, approval: c.approval, exec: c.exec, outcome: c.outcome } });
  return r;
}
const ID = 'RT-1048';
call('planner-a', 'case.get', { case_id: ID });
call('planner-b', 'case.get', { case_id: ID }); // tenant boundary
call('planner-a', 'decision.submit', { case_id: ID });
call('planner-a', 'decision.submit', { case_id: ID }); // duplicate
setAcct(ACCT('approver'));
const c = g('CASE_BY_ID')[ID], rec = c.recommendation;
const rationale = c.packet ? c.packet.rationale : g('afDraftRationale')(c);
call('approver', 'decision.approve', { case_id: ID, route: rec.plan, rationale: 'short', reviewed: true, spend: g('defaultSpend')(c, rec), terms: '' }); // validation
call('approver', 'decision.approve', {
  case_id: ID, route: rec.plan, rationale, reviewed: true, spend: g('defaultSpend')(c, rec),
  terms: `Transfer to ${rec.target || 'receiving site'} by ${c.timing || 'Day 10'}; cancel planned purchase PO-${48000 + parseInt(ID.slice(3))}`,
});
for (let i = 0; i < 12; i++) {
  const r = call(null, 'adapter.acknowledge', { case_id: ID }, { via: 'system', actor: AF_SYS });
  if (!r.ok) break;
}
call('finance', 'outcome.confirm', { case_id: ID });
call('finance', 'outcome.confirm', { case_id: ID }); // duplicate
setAcct(null);
put('actions.json', { case_id: ID, steps });

// ---------- the decision engine's read answers: what-if scenarios and pool optimisation (B10) ----------
// After the journey, so nothing above moves; both actions are read-only and draw no random numbers.
const SCENARIOS = [
  { purchase: 0.8 }, { purchase: 1.25 }, { cost: 1.3 }, { cost: 0.7 }, { service: 1.5 }, { market: 0.7 }, { market: 1.2 },
  { demandOff: true }, { purchase: 0.9, cost: 1.2, market: 1.1 }, { purchase: 0.6, service: 2, demandOff: true },
];
setAcct(ACCT('admin'));
const whatIf = {}, pools = {};
for (const cs of g('CASES')) {
  if (!cs.routes.length) continue;
  whatIf[cs.id] = SCENARIOS.map((s) => ({ input: s, output: read('case.whatIf', { case_id: cs.id, ...s }) }));
  if (cs.pool) pools[cs.id] = read('pool.optimize', { case_id: cs.id });
}
setAcct(null);
put('engine.json', { scenarios: SCENARIOS, what_if: whatIf, pools });

// ---------- read actions as each account, from a fresh copy of the demo (B11) ----------
// A fresh copy, so the reads see the demo's starting state and nothing above moves.
{
  const h = freshDemo();
  const inv = h('invoke'), setA = h('setAcct'), acct = h('ACCT');
  const rd = (id, input) => { const r = inv(id, input); return r.ok ? { ok: true, output: r.output } : { ok: false, error: r.error }; };
  const all = h('CASES');
  // every hand-modelled case, and generated cases from each stage and readiness (the first two of each)
  const pickIds = new Set(all.filter((c) => c.hero || ['RT-1062', 'RT-1044'].includes(c.id)).map((c) => c.id));
  const seen = {};
  for (const c of all) {
    const k = c.readiness + '|' + c.stage + '|' + (c.blocked ? 'b' : '');
    if (!c.hero && (seen[k] = (seen[k] || 0) + 1) <= 2) pickIds.add(c.id);
  }
  const caseIds = [...pickIds].sort();
  const CASE_READS = ['case.get', 'case.evidence', 'case.routes', 'case.trace', 'demand.find', 'asset.compare'];
  const CASE_AS = ['admin', 'planner-a', 'planner-b', 'wm-1', 'executive'];
  const LIST_INPUTS = [
    {}, { sort: 'priority' }, { sort: 'value', limit: 10 }, { sort: 'received', limit: 5 }, { stage: 'awaiting_approval' },
    { location: 'Warehouse 1' }, { missing: true }, { owner: 'Customer B' }, { cls: 'motor' }, { q: 'RT-1048' },
    { route: 'redeploy' }, { submitted: true }, { received_within_days: 3 }, { assessment: 'Pending' }, { product: 'Industrial motor' },
  ];
  const OTHER_READS = [
    ...LIST_INPUTS.map((i) => ['cases.list', i]),
    ['inbox.get', {}], ['receiving.plan', {}],
    ['access.lookup', { perm: 'approve' }], ['access.lookup', { perm: 'approve', amount: 20000 }], ['access.lookup', { perm: 'confirm' }],
    ['access.lookup', { perm: 'assess' }],
    ...Object.keys(h('AF_KPI')).map((k) => ['kpi.explain', { kpi: k }]),
  ];
  const reads = { case_ids: caseIds, case_reads: {}, other_reads: {} };
  for (const a of h('ACCOUNTS')) {
    setA(acct(a.id));
    if (CASE_AS.includes(a.id)) {
      reads.case_reads[a.id] = {};
      for (const id of caseIds) reads.case_reads[a.id][id] = Object.fromEntries(CASE_READS.map((x) => [x, rd(x, { case_id: id })]));
    }
    reads.other_reads[a.id] = OTHER_READS.map(([x, i]) => ({ action: x, input: i, result: rd(x, i) }));
  }
  setA(null);
  put('reads.json', reads);
}

// ---------- write actions: scripted scenarios, each in a fresh copy of the demo (B12) ----------
// A call is [account, action, input] (input may be a function of the demo and the results so far); after the calls,
// `observe` reads ([account, action, input]) show what changed through the read actions B11 matched.
{
  const RATIONALE = 'Redeploy to Site 3 as recommended; evidence snapshot reviewed.';
  const approve = (id, route, extra = {}) => ({ case_id: id, ...(route ? { route } : {}), rationale: RATIONALE, reviewed: true, ...extra });
  const look = (id, as = ['admin']) => as.flatMap((a) => [[a, 'case.get', { case_id: id }], [a, 'case.trace', { case_id: id }], [a, 'case.routes', { case_id: id }]]);
  const inbox = (...as) => as.map((a) => [a, 'inbox.get', {}]);
  const idpUser = (h, pred) => h('S').idp.users.find(pred);
  const lastReq = (h) => h('S').reqs[0].id;
  const SCENARIOS = {
    submit_and_approve: {
      calls: [['planner-a', 'decision.submit', { case_id: 'RT-1048' }], ['planner-a', 'decision.submit', { case_id: 'RT-1048' }],
        ['approver', 'decision.approve', { case_id: 'RT-1048', rationale: 'too short', reviewed: true }],
        ['approver', 'decision.approve', { case_id: 'RT-1048', rationale: RATIONALE, reviewed: false }],
        ['approver', 'decision.approve', approve('RT-1048', 'Sell + buy for Site 3')],
        ['approver', 'decision.approve', approve('RT-1048', null, { spend: 12000, terms: 'Transfer to Site 3 by Day 10' })],
        ['approver', 'decision.approve', approve('RT-1048')]],
      observe: [...look('RT-1048', ['admin', 'approver']), ...inbox('approver', 'planner-a', 'admin'), ['admin', 'cases.list', { submitted: true }]],
    },
    override: {
      calls: [['planner-a', 'decision.submit', { case_id: 'RT-1048' }], ['approver', 'decision.override', approve('RT-1048', 'Sell parts externally')],
        ['approver', 'decision.override', approve('RT-1048', 'No such route')], ['approver', 'decision.override', approve('RT-1048', 'Sell + buy for Site 3')]],
      observe: [...look('RT-1048'), ...inbox('approver', 'planner-a')],
    },
    decline_and_reevaluate: {
      calls: [['planner-a', 'decision.submit', { case_id: 'RT-1049' }], ['approver', 'decision.decline', { case_id: 'RT-1049', reason: 'short' }],
        ['approver', 'decision.decline', { case_id: 'RT-1049', reason: 'Refurbish first: grade A listings are open.' }],
        ['planner-a', 'decision.submit', { case_id: 'RT-1049' }], ['planner-a', 'case.reevaluate', { case_id: 'RT-1049' }],
        ['planner-a', 'decision.submit', { case_id: 'RT-1049' }], ['approver', 'decision.approve', approve('RT-1049')]],
      observe: [...look('RT-1049'), ...inbox('approver', 'planner-a')],
    },
    approve_without_submit_and_by_planner: {
      calls: [['planner-a', 'decision.approve', approve('RT-1048')], ['admin', 'decision.approve', approve('RT-1049')],
        ['approver', 'decision.approve', approve('RT-1050')], ['planner-b', 'decision.submit', { case_id: 'RT-1048' }]],
      observe: [...look('RT-1049'), ...inbox('admin')],
    },
    evidence: {
      calls: [['executive', 'evidence.request', { case_id: 'RT-1051' }], ['planner-a', 'evidence.request', { case_id: 'RT-1051' }],
        ['planner-a', 'evidence.request', { case_id: 'RT-1051' }], ['engineer', 'evidence.recordResult', { case_id: 'RT-1051' }],
        ['wm-1', 'evidence.request', { case_id: 'RT-1050' }], ['wm-2', 'evidence.request', { case_id: 'RT-1050' }],
        ['engineer', 'evidence.recordResult', { case_id: 'RT-1050' }], ['planner-b', 'decision.submit', { case_id: 'RT-1050' }]],
      observe: [...look('RT-1051'), ...look('RT-1050'), ...inbox('engineer', 'planner-a', 'planner-b', 'wm-2')],
    },
    prepare: {
      calls: [['planner-a', 'decision.prepare', { case_id: 'RT-1049' }], ['planner-a', 'decision.prepare', { case_id: 'RT-1051' }],
        ['approver', 'decision.prepare', { case_id: 'RT-1048' }]],
      observe: [...look('RT-1049'), ...inbox('planner-a')],
    },
    scenarios: {
      calls: [['planner-a', 'scenario.save', { case_id: 'RT-1048', name: 'Cheaper new motor', scen: { purchase: 0.8, cost: 1, service: 1, market: 1, demandOff: false } }],
        ['planner-a', 'scenario.save', { case_id: 'RT-1048', name: 'Demand cancelled', scen: { purchase: 1, cost: 1, service: 1, market: 1, demandOff: true }, top: 'Sell + buy for Site 3' }],
        ['planner-a', 'scenario.delete', (h, res) => ({ case_id: 'RT-1048', id: res[0].output && res[0].output.id })],
        ['planner-a', 'scenario.delete', { case_id: 'RT-1048', id: 'SCN-NONE' }], ['executive', 'scenario.save', { case_id: 'RT-1048', name: 'x', scen: {} }]],
      observe: [...look('RT-1048', ['planner-a'])],
    },
    notifications: {
      calls: [['executive', 'notify.send', { ex_id: 'risk:RT-1048', title: 'Value at risk: RT-1048', msg: 'Approve RT-1048 before Day 10.', sev: 'High', to: 'approver', ids: ['RT-1048'] }],
        ['approver', 'notify.acknowledge', { id: 'NTF-101' }], ['approver', 'notify.acknowledge', { id: 'NTF-101' }],
        ['planner-a', 'notify.acknowledge', { id: 'NTF-999' }], ['planner-a', 'comment.add', { key: 'RT-1048', text: 'Site 3 confirmed the need date.' }],
        ['approver', 'comment.add', { key: 'RT-1048', text: 'Checked the Site 3 contract terms.' }],
        ['finance', 'comment.add', { key: 'RT-1048', text: 'Purchase baseline checked against PO 49048.' }], ['finance', 'comment.add', { key: 'RT-1048', text: '' }],
        ['planner-a', 'escalation.send', { case_id: 'RT-1048', to: 'approver', msg: 'Needed at Site 3 in 10 days.', blocker: 'Approval pending' }]],
      observe: [...inbox('approver', 'executive', 'planner-a'), ['admin', 'case.trace', { case_id: 'RT-1048' }]],
    },
    tenant_access: {
      calls: [['planner-b', 'access.requestTenant', { tenant: 'Customer A', reason: 'Pooled motor demand at Site 3 needs RT-1048.' }],
        ['planner-b', 'access.requestTenant', { tenant: 'Customer C', reason: 'Shared battery pool with Customer C.' }],
        ['planner-b', 'access.requestTenant', { tenant: 'Customer C', reason: 'again' }], ['admin', 'access.decideRequest', (h) => ({ id: lastReq(h), decision: 'decline', note: 'Use the pool view' })],
        ['planner-b', 'case.get', { case_id: 'RT-1048' }], ['planner-b', 'access.decideRequest', { id: 'REQ-304', decision: 'approve' }],
        ['approver', 'access.decideRequest', { id: 'REQ-304', decision: 'approve', note: 'For the motor pool' }],
        ['planner-b', 'case.get', { case_id: 'RT-1048' }], ['admin', 'access.decideRequest', { id: 'REQ-304', decision: 'decline', note: 'Not needed' }],
        ['admin', 'access.decideRequest', { id: 'REQ-303', decision: 'approve' }]],
      observe: [...inbox('approver', 'planner-b', 'admin'), ['planner-b', 'cases.list', { owner: 'Customer A', limit: 3 }]],
    },
    mcp_proposals: {
      calls: [['developer', 'mcp.propose', { name: 'Fleet telemetry', owner: 'Operations', purpose: 'Read run hours for remaining life.', data: 'Run hours, alarms', access: 'read', tools: ['get_run_hours'] }],
        ['planner-a', 'mcp.propose', { name: 'x', owner: 'y', purpose: 'z', data: 'd', access: 'read', tools: [] }],
        ['approver', 'access.decideRequest', (h) => ({ id: lastReq(h), decision: 'approve' })], ['admin', 'access.decideRequest', { id: 'REQ-301', decision: 'decline', note: 'Duplicate' }]],
      observe: [...inbox('approver', 'developer', 'admin')],
    },
    delegation: {
      calls: [['approver', 'access.setDelegation', { k: 'decisions', on: false }], ['admin', 'access.setDelegation', { k: 'decisions', on: false }],
        ['planner-a', 'decision.submit', { case_id: 'RT-1048' }], ['approver', 'decision.approve', approve('RT-1048')],
        ['admin', 'access.setDelegation', { k: 'tenantAccess', on: false }], ['approver', 'access.decideRequest', { id: 'REQ-304', decision: 'approve' }],
        ['admin', 'access.setDelegation', { k: 'decisions', on: true }]],
      observe: [['admin', 'access.lookup', { perm: 'approve' }], ...inbox('approver', 'admin')],
    },
    identity: {
      calls: [['planner-a', 'access.syncDirectory', {}], ['admin', 'access.syncDirectory', {}], ['admin', 'access.setRoleSource', { src: 'groups' }],
        ['admin', 'access.mapIdentity', { acct: 'admin', field: 'role', value: 'Planner' }], ['admin', 'access.mapIdentity', { acct: 'planner-c', field: 'role', value: 'Wizard' }],
        ['admin', 'access.mapIdentity', { acct: 'wm-2', field: 'site', value: 'Warehouse 1' }],
        ['admin', 'access.setOutOfOffice', (h) => ({ to: idpUser(h, (u) => h('idpRoleOf')(u) === 'Planner').id, from: '2026-10-08', until: '2026-10-15' })],
        ['admin', 'access.setOutOfOffice', (h) => ({ to: idpUser(h, (u) => h('idpRoleOf')(u) === 'Approver').id, from: '2026-10-15', until: '2026-10-08' })],
        ['admin', 'access.setOutOfOffice', (h) => ({ to: idpUser(h, (u) => h('idpRoleOf')(u) === 'Approver').id, from: '2026-10-08', until: '2026-10-15' })],
        ['admin', 'access.clearOutOfOffice', { index: 0 }], ['admin', 'access.clearOutOfOffice', { index: 5 }],
        ['admin', 'access.removeUser', (h) => ({ id: h('S').idp.users[h('S').idp.users.length - 1].id })], ['admin', 'access.removeUser', { id: 'nobody' }]],
      observe: [['admin', 'access.lookup', { perm: 'assess' }], ['wm-2', 'cases.list', { limit: 3 }], ...inbox('admin')],
    },
  };
  const writes = {};
  for (const [name, sc] of Object.entries(SCENARIOS)) {
    const h = freshDemo();
    const inv = h('invoke'), setA = h('setAcct'), acct = h('ACCT');
    const results = [], calls = [];
    for (const [as, id, input] of sc.calls) {
      const inp = typeof input === 'function' ? input(h, results) : input;
      setA(acct(as));
      const r = inv(id, inp);
      calls.push({ as, action: id, input: inp });
      results.push(r);
    }
    const observed = sc.observe.map(([as, id, input]) => { setA(acct(as)); return { as, action: id, input, result: inv(id, input) }; });
    setA(null);
    writes[name] = { calls: calls.map((c, k) => ({ ...c, result: results[k] })), observed };
  }
  put('writes.json', writes);
}

// ---------- write ----------
mkdirSync(out, { recursive: true });
for (const [name, data] of Object.entries(files)) writeFileSync(join(out, name), JSON.stringify(data, null, 1) + '\n');
const inv = files['figures.json'].invariants;
console.log(`[golden] wrote ${Object.keys(files).length} files to ${out}`);
console.log(`[golden] cases ${files['cases.json'].length}, decisions ${files['decisions.json'].length}, accounts ${Object.keys(accounts).length}, journey steps ${steps.length}`);
console.log('[golden] invariants:', JSON.stringify(inv).slice(0, 300));
