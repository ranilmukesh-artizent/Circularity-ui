/**
 * MVP-0.3: dump the PO Modeler prototype (docs/reference/po-modeler/recover-app-prototype.html) into
 * fixtures/golden/po/*.json, the reference the decision-platform tasks compare against (plan 08, Domain spec D1-D11).
 *
 *   cd frontend; node scripts/dump-po-golden.mjs
 *
 * Opens the prototype from its file:// URL in the installed Chrome (no download). The Recover app sits in
 * <template id="app-recover"> and runs in one closure when its "Open Recover" button mounts it, so the script adds one
 * line before the app's final render() that hands out a lookup of the closure's names, then presses that button;
 * nothing else in the prototype changes and its own seeds (rng(26110), rng(4242)) stay.
 * Date.now is pinned to 1767225600000 (the proposal node ids); the prototype never calls Math.random.
 * Output is sorted JSON, numbers rounded to 1e-6, so two runs give byte-identical files. Never hand-edit the output.
 */
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const proto = join(root, 'docs/reference/po-modeler/recover-app-prototype.html');
const outDir = join(root, 'fixtures/golden/po');
const NOW = 1767225600000;

const SENTENCES = [
  'Never recycle construction lasers',
  'Prefer tool pool for grade A or B from Repair center',
  'Only harvest parts for breakers under 30% life',
  'Lower the fit-for-use threshold to 60',
  'Skip approval for grade A',
  'Lots over 45 days on hand: Auction only',
  'Never list grade D on Buy Now',
  'Samsung under 24 months prefer offers',
];
const DEVICE_SIM_RULE = 'Lots over 45 days on hand: Auction only';

/** Runs in the page: adds the closure lookup (window.__po) to the Recover app's script, still in its template. */
function expose() {
  const script = document.getElementById('app-recover').content.querySelector('script');
  const tail = /\nrender\(\);\n\}\)\(\);\s*$/;
  if (!tail.test(script.textContent)) throw new Error('the Recover script no longer ends with "render();\\n})();"');
  script.textContent = script.textContent.replace(tail, '\nwindow.__po = (n) => eval(n);\nrender();\n})();\n');
}

/** Runs in the page: evaluates every golden and returns them as { file: data }. */
function dump({ sentences, deviceSimRule }) {
  const g = window.__po;
  const [TPL, MD, P, PUB, PK, PATHS, FN, FE] = ['TPL', 'MD', 'P', 'PUB', 'PK', 'PATHS', 'FN', 'FE'].map(g);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const prototypeTplKeys = Object.keys(TPL);

  // The prototype has no TPL.device (only TPL.equip, line 2373), yet fValidate, fSim and buildProposal reach the
  // device template through TPL[key]. Register it from the prototype's own device pieces so those functions run.
  const deviceRule = g('tplDevice')().n.find((x) => x.t === 'rule');
  if (!TPL.device) {
    TPL.device = {
      guards: g('GUARDS_D'), paths: g('DCH'), pname: (k) => g('DCN')[k], text: g('ruleTextD'), guard: g('ruleGuardD'),
      compile: g('compileDevice'), pre: deviceRule.rid.split('-')[0],
    };
  }

  // templates.json. dims: the scope fields of the rule inspector (prototype lines 2510-2511), which are markup only.
  const NUM = null;
  const DIMS = {
    equip: [['cls', 'Model', Object.keys(g('CLSWORDS'))], ['grade', 'Grade', ['A', 'B', 'C', 'D']],
      ['ft', 'Return channel', g('FUNCS')], ['site', 'Site', g('SITES')], ['rulMax', 'Life under %', NUM],
      ['rulMin', 'Life at least %', NUM]],
    device: [['brand', 'Brand', ['Apple', 'Samsung', 'Google', 'Motorola']], ['grade', 'Grade', ['A', 'B', 'C', 'D']],
      ['band', 'Age band', ['0-24m', '25-48m', '49m+']], ['dohMin', 'Days on hand ≥', NUM], ['qtyMin', 'Lot units ≥', NUM]],
  };
  const pathInfo = {
    equip: (k) => ({ key: k, ...PATHS[k] }),
    device: (k) => ({ key: k, name: g('DCN')[k] }),
  };
  const templates = {
    prototype_tpl_keys: prototypeTplKeys,
    templates: ['equip', 'device'].map((key) => ({
      key,
      name: TPL[key].name ?? null,
      sub: TPL[key].sub ?? null,
      pre: TPL[key].pre,
      in_prototype_tpl: prototypeTplKeys.includes(key),
      paths: TPL[key].paths.map(pathInfo[key]),
      guards: TPL[key].guards.map(([id, text, owner]) => ({ id, text, owner })),
      dims: DIMS[key].map(([dkey, label, values]) => ({ key: dkey, label, values })),
      chips: TPL[key].chips ?? [],
    })),
    ACTORS: g('ACTORS').map(([id, name, role]) => ({ id, name, role })),
    CLSWORDS: g('CLSWORDS'),
    FUNCS: g('FUNCS'),
    SITES: g('SITES'),
  };

  const flows = { equip: g('tplEquip')(), device: g('tplDevice')() };

  const CASES = g('CASES');
  const open = g('openCases')();
  const equipCases = { cases: CASES, open_ids: open.map((c) => c.id) };

  const decide = g('decide');
  const live = g('liveRules')();
  const equipDecisions = {
    rules: live,
    decisions: open.map((c) => {
      const d = decide(c, P, live);
      return {
        id: c.id, best: { k: d.best.k, net: d.best.net }, rules: d.rules,
        paths: d.all.map((v) => ({ k: v.k, ok: v.ok, net: v.net, why: v.why })),
      };
    }),
  };

  const lots = g('dLots')();
  const deviceBase = g('compileDevice')(PUB.device);
  const deviceDecisions = {
    rules: deviceBase,
    decisions: lots.map((l) => ({
      id: l.id, best: g('dDecide')(l, deviceBase), channels: g('DCH').map((k) => g('dScore')(l, k)),
    })),
  };

  // The default flow and four edited ones, each built from the published equip flow.
  const base = () => Object.assign(clone(PUB.equip), { key: 'equip' });
  const withRule = (opts) => {
    const f = base();
    f.n.push(FN('r3', 'rule', 1004, 470, '', '', { rid: 'BR-03', owner: 'Fleet desk', ...opts }));
    f.e = f.e.filter((e) => e.id !== 'r2>dec').concat([FE('r2', 'r3'), FE('r3', 'dec')]);
    return f;
  };
  const edited = {
    r1_disconnected: (() => {
      const f = base();
      f.e = f.e.filter((e) => e.id !== 'gate>r1').concat([FE('gate', 'r2')]);
      return f;
    })(),
    harvest_removed: (() => {
      const f = base();
      f.n = f.n.filter((x) => x.id !== 'p-harvest');
      f.e = f.e.filter((e) => e.a !== 'p-harvest' && e.b !== 'p-harvest');
      return f;
    })(),
    release_grade_c: withRule({ action: 'prefer', path: 'release', scope: { grade: ['C'] } }),
    rule_without_path: withRule({ action: 'exclude', scope: {} }),
  };
  const allFlows = { default: base(), ...edited };
  const names = Object.keys(allFlows);
  const compiled = Object.fromEntries(names.map((k) => [k, g('compileEquip')(allFlows[k])]));
  const compileCases = { cases: names.map((k) => ({ name: k, flow: allFlows[k], rules: compiled[k] })) };
  const validateCases = { cases: names.map((k) => ({ name: k, checks: g('fValidate')(allFlows[k]) })) };

  const value = g('value');
  const ruleTextE = g('ruleTextE');
  const ruleSets = {
    ...compiled,
    exclude_every_path: PK.map((k, i) => {
      const r = { id: 'BR-9' + i, scope: {}, action: 'exclude', path: k };
      return { ...r, text: ruleTextE(r) };
    }),
  };
  const applyCases = {
    rule_sets: ruleSets,
    cases: open.slice(0, 6).flatMap((c) => Object.keys(ruleSets).map((set) => {
      const all = PK.map((k) => value(c, k, P));
      const result = g('applyRules')(c, all, ruleSets[set]);
      return { id: c.id, rule_set: set, result, paths: all.map((v) => ({ k: v.k, ok: v.ok, why: v.why })) };
    })),
  };

  const parseCases = {
    cases: sentences.map((text) => ({ text, equip: g('parseEquip')(text), device: g('parseDevice')(text) })),
  };

  const textGuard = g('textGuard');
  const guardFor = (tpl, text) => { MD.tpl = tpl; return textGuard(text); };
  const textguardCases = {
    cases: sentences.map((text) => ({ text, equip: guardFor('equip', text), device: guardFor('device', text) })),
  };
  MD.tpl = 'equip';

  const simSummary = (s) => {
    if (!s) return null;
    if (s.kind === 'equip') {
      return {
        kind: s.kind, n: s.n, dv: s.dv,
        flips: s.flips.map((x) => ({ id: x.c.id, from: x.b.best.k, to: x.s.best.k, from_net: x.b.best.net, to_net: x.s.best.net })),
      };
    }
    return {
      kind: s.kind, n: s.n, u: s.u, dv: s.dv, cash: s.cash, dd: s.dd, days: s.days, dl: s.dl,
      flips: s.flips.map((x) => ({ id: x.l.id, from: x.b.k, to: x.s.k })),
    };
  };
  const fSim = g('fSim');
  const buildProposal = g('buildProposal');
  MD.actor = 'pshah';
  MD.tpl = 'device';
  const deviceProp = buildProposal(deviceSimRule);
  MD.tpl = 'equip';
  const simCases = {
    equip: Object.keys(edited).map((k) => ({ name: k, sim: simSummary(fSim(edited[k], PUB.equip)) })),
    device: [{ text: deviceSimRule, rule: deviceProp.flow.n.find((x) => x.id === deviceProp.nid), sim: simSummary(fSim(deviceProp.flow, PUB.device)) }],
  };

  const proposal = (tpl, text) => {
    MD.tpl = tpl;
    const p = buildProposal(text);
    const node = p.flow && p.nid ? p.flow.n.find((x) => x.id === p.nid) : null;
    return {
      text, kind: p.kind, rid: p.rid ?? null, label: p.label ?? null, msg: p.msg ?? null, g: p.g ?? null,
      nid: p.nid ?? null, node, checks: p.v ?? null, sim: simSummary(p.sim),
    };
  };
  const proposals = {
    actor: MD.actor,
    now: Date.now(),
    equip: sentences.map((t) => proposal('equip', t)),
    device: sentences.map((t) => proposal('device', t)),
  };
  MD.tpl = 'equip';

  // Plain JSON: functions dropped, Sets as arrays, a cycle is an error.
  const plain = (v, stack = []) => {
    if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
    if (typeof v === 'number') return Number.isFinite(v) ? Math.round(v * 1e6) / 1e6 : String(v);
    if (typeof v === 'function' || v === undefined || typeof v === 'symbol') return undefined;
    if (stack.includes(v)) throw new Error('cycle in golden data');
    const next = stack.concat([v]);
    if (v instanceof Set || Array.isArray(v)) return [...v].map((x) => plain(x, next) ?? null);
    const o = {};
    for (const k of Object.keys(v)) { const x = plain(v[k], next); if (x !== undefined) o[k] = x; }
    return o;
  };
  return plain({
    templates, flows, equip_cases: equipCases, equip_decisions: equipDecisions, device_lots: { lots },
    device_decisions: deviceDecisions, compile_cases: compileCases, validate_cases: validateCases,
    apply_cases: applyCases, parse_cases: parseCases, textguard_cases: textguardCases, sim_cases: simCases, proposals,
  });
}

/** Keys sorted at every level. */
function sorted(v) {
  if (Array.isArray(v)) return v.map(sorted);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])]));
  return v;
}

const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript((now) => { Date.now = () => now; }, NOW);
  await page.goto(pathToFileURL(proto).href);
  await page.evaluate(expose);
  await page.locator('button.h-open[data-mod="recover"]').click();
  await page.waitForFunction(() => typeof window.__po === 'function');
  const files = await page.evaluate(dump, { sentences: SENTENCES, deviceSimRule: DEVICE_SIM_RULE });
  if (errors.length) throw new Error('page errors: ' + errors.join('; '));
  mkdirSync(outDir, { recursive: true });
  for (const [name, data] of Object.entries(files)) {
    const file = join(outDir, name + '.json');
    writeFileSync(file, JSON.stringify(sorted(data), null, 1) + '\n');
    console.log('wrote', file);
  }
  console.log('prototype sha256', createHash('sha256').update(readFileSync(proto)).digest('hex'));
} finally {
  await browser.close();
}
