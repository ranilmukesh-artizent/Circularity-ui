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
const ctx = vm.createContext({
  console, Date: FixedDate, Intl, TextEncoder, crypto: globalThis.crypto, performance: { now: () => 0 },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
});
vm.runInContext(prelude + src + '\n;globalThis.__get=function(n){return eval(n)};', ctx, { timeout: 60000 });
const g = (n) => ctx.__get(n);

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

// ---------- write ----------
mkdirSync(out, { recursive: true });
for (const [name, data] of Object.entries(files)) writeFileSync(join(out, name), JSON.stringify(data, null, 1) + '\n');
const inv = files['figures.json'].invariants;
console.log(`[golden] wrote ${Object.keys(files).length} files to ${out}`);
console.log(`[golden] cases ${files['cases.json'].length}, decisions ${files['decisions.json'].length}, accounts ${Object.keys(accounts).length}, journey steps ${steps.length}`);
console.log('[golden] invariants:', JSON.stringify(inv).slice(0, 300));
