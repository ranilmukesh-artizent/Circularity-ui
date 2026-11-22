// Golden data for the product, case and orchestration screens (B14): what the demo computes for those pages, for every
// account, through the same engine functions the facade files (src/api/product.ts, case.ts, orchestration.ts) call.
//
//   node frontend/scripts/golden/product_case.mjs
//
// Writes fixtures/golden/screens/product.json, case.json and orchestration.json. Values that do not depend on the
// account are written once per case (the script checks that they are the same for every account that may see the
// case); what depends on the account is written per account. A refusal is {refused: <error code>}.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { freshDemo, goldenDir, writeGolden } from '../golden-sandbox.mjs';

// Each screen runs on a fresh copy of the demo: some page functions fill fields on first draw (predictBlock writes
// c.predictions), and the backend serves the starting state.
let g, setAcct, ACCT, S, CASES, CBI, canPage, tenantOK, locOK;
function fresh() {
  g = freshDemo();
  [setAcct, ACCT, S, CASES, CBI] = ['setAcct', 'ACCT', 'S', 'CASES', 'CASE_BY_ID'].map((n) => g(n));
  [canPage, tenantOK, locOK] = ['canPage', 'tenantOK', 'locOK'].map((n) => g(n));
}
fresh();
const ACCOUNTS = JSON.parse(readFileSync(join(goldenDir, 'policy.json'), 'utf8')).accounts.map((a) => a.id);
const READ_IDS = JSON.parse(readFileSync(join(goldenDir, 'reads.json'), 'utf8')).case_ids;
const f = (n) => g(n);
const TENANT_FILTERS = ['All', 'Customer A', 'Customer B', 'Customer C'];
const J = (x) => (x === undefined ? null : JSON.parse(JSON.stringify(x))); // no shared objects ($ref) in the output
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const AS_OF = g('AS_OF');

// The case set: every hero case, RT-1062, RT-1044 and generated cases from each stage and readiness (reads.json).
const IDS = READ_IDS;

/** Store a value that should not depend on the account: the first account's, checked against every other one. */
function once(store, key, v, who) {
  if (!(key in store)) store[key] = { v: J(v), who };
  else if (!same(store[key].v, J(v))) throw new Error(`${key} differs between ${store[key].who} and ${who}`);
}
const flat = (store) => Object.fromEntries(Object.entries(store).map(([k, x]) => [k, x.v]));

// ---------------------------------------------------------------- shared shapes
const rr = (r) => (r ? { id: r.id, plan: r.plan, net: r.net } : null);
const ROW_KEYS = ['id', 'assetId', 'product', 'cls', 'owner', 'received', 'location', 'condition', 'assessment', 'stage', 'qty', 'grade', 'age',
  'mfr', 'engLife', 'hero', 'spec', 'evidence', 'blocked'];
/** One case as the lists show it (Returned assets, the asset page's fleet, related and compare). */
function row(c) {
  const o = {};
  for (const k of ROW_KEYS) if (c[k] !== undefined) o[k] = c[k];
  Object.assign(o, {
    recommendation: rr(c.recommendation), chosen: rr(c.chosen), model: f('asModel')(c), serial: f('asSerial')(c), stage_key: f('ccStage')(c),
    health: f('assetHealth')(c).score, signals: f('sigOf')(c),
  });
  return o;
}
function refusal(page, sec, c) {
  if (!canPage(page, sec)) return { refused: 'out_of_scope' };
  if (c && (!tenantOK(c.owner) || !locOK(c))) return { refused: 'tenant_boundary' };
  return null;
}

// ---------------------------------------------------------------- the facade's own computations (product.ts)
function assetEcon(c) {
  const r = c.recommendation, K = g('CLASSES')[c.cls], q = c.qty, asHex = f('asHex');
  const sum = (a) => a.reduce((x, y) => x + y, 0);
  const CC_EST = g('CC_EST');
  const pos = r ? sum(r.terms.filter((t) => t.amt > 0).map((t) => t.amt)) : Math.round(CC_EST[c.cls] * q);
  const neg = r ? sum(r.terms.filter((t) => t.amt < 0).map((t) => t.amt)) : 0;
  const net = r ? r.net : Math.round(pos * 0.8);
  const rg = r ? Math.round(((r.p90 - r.p10) / 2 / Math.max(1, Math.abs(net))) * 100) : null;
  const age = Math.max(1, c.age);
  const mt = Math.round(K.pnew * q * 0.018 * age * (0.8 + (asHex(c, 'mt') % 50) / 100));
  const pr = Math.round(mt * (0.4 + (asHex(c, 'pr') % 40) / 100));
  const sv = Math.round((mt + pr) * (0.9 + (asHex(c, 'sv') % 30) / 100));
  const avg = Math.round(sv / age);
  const rs = g('ROWS').filter((x) => x.cls === c.cls && x.route === 'resale' && x.status === 'reconciled' && x.actual > 0);
  const by = Array(12).fill(0);
  rs.forEach((x) => { by[x.mi]++; });
  const med = f('med');
  const unit = (a) => med(a.map((x) => x.actual / x.q));
  const last3 = rs.filter((x) => x.mi >= 9), prev3 = rs.filter((x) => x.mi >= 6 && x.mi < 9);
  const trend = prev3.length && last3.length ? (unit(last3) / unit(prev3) - 1) * 100 : 0;
  const price = rs.length ? Math.round(unit(rs) * q) : 0;
  const bars = by.slice(6), mx = Math.max(1, ...bars);
  const dem = (bars[3] + bars[4] + bars[5]) / Math.max(1, bars[0] + bars[1] + bars[2]);
  const demand = dem >= 1.1 ? ['Strong', 'ok'] : dem >= 0.9 ? ['Steady', 'warn'] : ['Softening', 'bad'];
  const months = g('MONTHS').slice(6);
  return { pos, neg, net, rg, age, mt, pr, sv, avg, bars, mx, months, demand, trend, price }; // r: the case's recommendation
}
function assetEligibility(c) {
  const d = c.demand || {}, spec = c.spec || {};
  const yr = new Date(c.received).getUTCFullYear() - Math.max(0, Math.round(c.age)) + Math.min(6, Math.round(g('CLASSES')[c.cls].tau / 2));
  const warrOk = yr >= new Date(AS_OF).getUTCFullYear();
  const sil = /SIL/.test(spec['Safety rating'] || ''), lith = ['drill', 'batch', 'it'].includes(c.cls), erase = c.cls === 'it' && spec['Data erasure'] === 'Pending';
  const asLease = f('asLease');
  return [
    ['Ownership', c.owner, 'Eligible for all treatments', 'ok'],
    ['Contract terms', d.lease ? 'Lease ' + asLease(c) + ' ended, no restriction on reuse' : 'No contract restriction on file', d.lease ? 'Verified' : 'Not on file', d.lease ? 'ok' : 'line'],
    ['Warranty', warrOk ? 'Active until ' + yr : 'Expired (' + yr + ')', warrOk ? 'Active' : '—', warrOk ? 'ok' : 'line'],
    ['Safety and regulatory', sil ? 'Safety-rated unit (' + spec['Safety rating'] + ')' : 'No open safety alerts', sil ? 'Review' : 'Compliant', sil ? 'warn' : 'ok'],
    ['Environmental', erase ? 'Data erasure certificate pending' : lith ? 'Lithium battery handling required' : 'No special handling', erase || lith ? 'Follow guidelines' : 'Compliant', erase || lith ? 'warn' : 'ok'],
  ]; // route: c.recommendation || c.routes[0]
}
function closedLastYear(c) {
  const m = f('asModel')(c), cut = f('addDays')(AS_OF, -365);
  return g('ROWS').filter((r) => String(r.equip).replace(/s$/, '') === m && r.tenant === c.owner && new Date(r.date) >= cut).length;
}
function expectedStage(e) {
  const st = g('AF_STAGES'), day = +String(e.date).split(' ')[0], n = day - 2 > new Date(AS_OF).getUTCDate() ? 1 : 2;
  return 'Stage ' + n + ' · ' + st[n - 1].t;
}

// ---------------------------------------------------------------- product
function assetBundle(c) {
  const h = f('assetHealth')(c), r = c.chosen || c.recommendation, rec = c.recommendation;
  return {
    case: J(c), title: f('asTitle')(c), serial: f('asSerial')(c), rev: f('asRev')(c), receipt: f('asReceipt')(c), rma: f('asRMA')(c), sc: f('asSC')(c),
    lease_ref: f('asLease')(c), model: f('asModel')(c),
    health: h, facts: f('assetFacts')(c), events: f('asEvents')(c), return_history: f('asReturnHistory')(c), parts: f('asParts')(c, h),
    part_prices: f('asPartPrices')(c, h), catalogue: f('asCatalogue')(c), prep_cost: f('asPrepCost')(c),
    prep_parts: r ? f('exPrepParts')(c, r) || null : null, learn_version: f('learnVer')(c, 'prep-cost-time'),
    rul: f('caseRul')(c) || null, demand: f('caseDemand')(c) || null, diag: f('caseDiag')(c) || null, recert: r ? f('recert')(c, r) || null : null,
    confidence: r ? f('tiConf')(c, r) : null, value_order: f('valueOrder')(c) || null, value_state: f('asValState')(c), baseline: f('asBaseline')(c),
    econ: assetEcon(c), eligibility: assetEligibility(c), lease_trail: f('afLease')(c), provenance: c.evidence.map((e) => f('provFor')(c, e)),
    snapshot_time: f('snapTime')(c), closed_last_year: closedLastYear(c),
    term_methods: rec ? rec.terms.map((t) => f('exTrace')(c, rec, t).method) : [],
  };
}
/** The journey strip and guide on Returned assets (step 0) and Asset intelligence (step 1). The run is always past
 * stage 4, so both steps are always 'done' and only what each established is shown (jgWait is never reached). */
function journey(c) {
  const p = f('jgProg')(c);
  if (p <= 1) throw new Error(c.id + ' at stage ' + p);
  return { visible: true, progress: p, established: [f('jgEst')(c, 0), f('jgEst')(c, 1)] };
}

const product = { rows: {}, expected_rows: [], accounts: {}, asset: {} };
const assetOnce = {};
for (const c of CASES) product.rows[c.id] = J(row(c));
product.expected_rows = J(g('EXPECTED').map((e) => ({ ...e, run_stage: expectedStage(e) })));
for (const a of ACCOUNTS) {
  setAcct(ACCT(a));
  const out = { returned: {}, expected: {}, my_ids: f('myCases')().map((c) => c.id) };
  for (const t of TENANT_FILTERS) {
    S.tenant = t;
    out.returned[t] = f('visCases')().map((c) => c.id);
    out.expected[t] = f('expVis')().map((e) => e.id);
  }
  S.tenant = 'All';
  const ok = f('whOK');
  out.expected_count = g('EXPECTED').filter((e) => tenantOK(e.owner) && ok(e)).length;
  out.notes = J(S.notes.filter((n) => n.to === S.acct.id && n.status === 'open'));
  out.source = J(f('SRC')('lease') ?? { vendor: 'Contract Management', freshMin: 0 });
  out.journey = {};
  out.asset = {};
  out.default_asset = f('rbLastAsset')();
  for (const id of IDS) {
    const c = CBI[id];
    out.journey[id] = f('dpVisible')(id) ? journey(c) : { visible: false };
    const no = refusal('product', 'asset', c);
    if (no) { out.asset[id] = no; continue; }
    once(assetOnce, id, assetBundle(c), a);
    const my = f('myCases')(), m = f('asModel')(c);
    const cnt = (l, fn) => l.reduce((o, x) => { const k = fn(x); o[k] = (o[k] || 0) + 1; return o; }, {});
    out.asset[id] = {
      fleet: my.filter((x) => x.cls === c.cls).map((x) => x.id),
      related: f('assetRelated')(c).map((x) => x.id),
      units: f('skuUnits')(c).map((x) => x.id),
      models: cnt(my, f('asModel')),
      customers: cnt(my.filter((x) => f('asModel')(x) === m), (x) => x.owner),
      journey: !!f('dpVisible')(id),
    };
  }
  out.pools = ['RT-1048', 'RT-1052'].filter((id) => tenantOK(CBI[id].owner));
  product.accounts[a] = out;
}
product.asset = flat(assetOnce);
product.pools = J(g('POOLS'));
setAcct(null);

// ---------------------------------------------------------------- case
const STAGE_DATA = (c, n) => {
  const d = f('stData')(c, n);
  return { res: d.res, facts: d.facts.map((x) => ({ l: x.l, v: x.v, k: x.p.k, sys: x.p.sys })), docs: d.docs, mean: d.mean, when: d.when ?? null, who: d.who };
};
function activeClock(c) {
  const a = c.exec && c.exec.steps.find((y) => y.state === 'active');
  return a ? f('exClock')(c, a, f('asOfNow')()) : null;
}
function analysis(c) {
  const r = c.chosen || c.recommendation, el = c.routes.filter((x) => !x.excluded).sort((a, b) => b.net - a.net);
  const rows = f('afBaseRows')(c), tb = f('tieBreak')(c, rows);
  return {
    provenance: c.evidence.map((e) => f('provFor')(c, e)), snapshot_time: f('snapTime')(c),
    routes: c.routes.map((x) => ({ id: x.id, plan: x.plan, conf: f('tiConf')(c, x), terms: x.excluded ? null : x.terms.map((t) => f('exTrace')(c, x, t)) })),
    ranking: rows.map((x) => ({ route: x.r.id, plan: x.r.plan, gross: x.gross, cost: x.cost, net: x.net, days: x.days, prob: x.prob, life: x.life, co2: x.co2 })),
    tie: tb && tb.near ? { gap: tb.gap, pct: tb.pct, text: f('tieText')(tb), preferred: tb.preferred.r.plan, decided_by: tb.decidedBy, values: tb.values } : null,
    flips: f('flips')(c),
    rul: f('caseRul')(c) || null, demand: f('caseDemand')(c) || null, recert: r ? f('recert')(c, r) || null : null,
    pool: c.poolResult || g('POOLS')[c.id] || null,
    plan: r ? f('exPlan')(c, r, f('asOfNow')()) : [], move: r ? f('exMove')(c, r) || null : null, what_if: r ? f('exWhatIf')(c, r) : [],
    prep_parts: r ? f('exPrepParts')(c, r) || null : null,
    lease: f('afLease')(c),
    rationale: f('afDraftRationale')(c),
    spend: Object.fromEntries(el.map((x) => [x.id, f('defaultSpend')(c, x)])),
    instruction: r ? f('instrPayload')(c) : null,
    journal: f('afCaseJournal')(c.id),
    events: g('EVENTS').filter((x) => x.caseId === c.id),
    evidence_pack: f('afEvidencePack')(c.id),
  };
}
fresh();
const CASE0 = Object.fromEntries(IDS.map((id) => [id, J(CBI[id])])); // the case records before any page draws
// stData's facts carry a provenance badge (HTML, stProv(kind, system)); record the kind and system instead.
g('stProv=function(k,sys){return {k:k,sys:sys}}');
const caseOut = { cases: {}, accounts: {} };
const anOnce = {}, stOnce = {};
for (const a of ACCOUNTS) {
  setAcct(ACCT(a));
  const out = {};
  for (const id of IDS) {
    const c = CBI[id], no = refusal('product', 'case', c);
    if (no) { out[id] = no; continue; }
    const run = f('afRun')(c);
    out[id] = J({
      run, tags: run.stages.map((s) => f('stState')(c, s.n, run)), landing: f('stLand')(c), next: f('afNextStep')(c), clock: activeClock(c),
      approval: { role: S.deleg.decisions ? 'Approver' : 'Admin', limit: f('afLimitFor')(S.acct) },
    });
    once(anOnce, id, analysis(c), a);
    once(stOnce, id, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => STAGE_DATA(c, n)), a);
  }
  caseOut.accounts[a] = out;
}
for (const [id, x] of Object.entries(flat(anOnce))) caseOut.cases[id] = { analysis: x, stages: flat(stOnce)[id], case: CASE0[id] };
setAcct(null);

// ---------------------------------------------------------------- orchestration
const orRow = (c) => ({
  id: c.id, product: c.product, owner: c.owner, stage: c.stage, approval: c.approval ? { ref: c.approval.ref, by: c.approval.by } : null,
  submitted: c.submitted ? { by: c.submitted.by } : null, exec: c.exec ? { steps: c.exec.steps.map((s) => ({ label: s.label, state: s.state })) } : null,
  outcome: c.outcome ? { net: c.outcome.net } : null,
});
function runOf(c) {
  const m = f('lrModel')(c), tl = f('lrTimeline')(c, m);
  return {
    model: m, timeline: tl, sig: f('lrSig')(c),
    stage_models: m.st.map((s) => f('lrStageModels')(c, s.n, s.lines).map((k) => ({ key: k, version: f('lrModelVer')(c, k) }))),
  };
}
fresh();
const orc = { rows: {}, runs: {}, drills: {}, accounts: {} };
const runOnce = {};
for (const c of CASES) orc.rows[c.id] = J(orRow(c));
for (const a of ACCOUNTS) {
  setAcct(ACCT(a));
  const out = { cases: {}, run: {} };
  for (const t of TENANT_FILTERS) {
    S.tenant = t;
    out.cases[t] = { ids: f('orCases')().map((c) => c.id), default: f('orCase')()?.id ?? null };
  }
  S.tenant = 'All';
  for (const id of IDS) {
    const c = CBI[id], no = refusal('orchestration', 'run', c);
    if (no) { out.run[id] = no; continue; }
    once(runOnce, id, runOf(c), a);
    const nx = f('afNextStep')(c), d = f('afEscalation')(c, nx).data, to = f('ACCT')(d.to);
    out.run[id] = J({ next: nx, escalation: { ...d, toLabel: to ? to.label : d.to } });
  }
  orc.accounts[a] = out;
}
orc.runs = flat(runOnce);
for (const id of ['RT-1048', 'RT-1052', 'RT-1003']) {
  orc.drills[id] = {};
  setAcct(ACCT('admin'));
  for (let k = 0; k < 10; k++) {
    S.or.fail = String(k);
    const c = CBI[id], m = f('lrModel')(c);
    orc.drills[id][k] = J({ model: m, timeline: f('lrTimeline')(c, m), sig: f('lrSig')(c) });
  }
  S.or.fail = '';
}
setAcct(null);
orc.journal = {}; orc.events = {};
for (const id of IDS) {
  orc.journal[id] = J(f('afCaseJournal')(id));
  orc.events[id] = J(g('EVENTS').filter((x) => x.caseId === id));
}

for (const [name, data] of [['screens/product.json', product], ['screens/case.json', caseOut], ['screens/orchestration.json', orc]]) {
  const file = writeGolden(name, data);
  console.log('wrote', file, (readFileSync(file).length / 1e6).toFixed(2), 'MB');
}
