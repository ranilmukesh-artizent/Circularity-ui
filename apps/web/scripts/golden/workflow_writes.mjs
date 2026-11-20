// B15 golden data for the Workflow Studio's actions: workflow.save, publish, setStatus, create, duplicate, delete, run
// and the read workflow.validate.
//
//   node apps/web/scripts/golden/workflow_writes.mjs   -> fixtures/golden/workflow_writes.json
//
// Each scenario runs in a fresh copy of the demo. As in fabric.mjs (the B14 studio data), wfInit() runs first, before
// anything else draws a random number, so every copy starts from the workflows screens/workflows.json recorded, and
// every workflow's graph is built (what opening it does). A call is [account, action, input] (input may be a function
// of the demo and the results so far) and its result is recorded; ['flush'] finishes the runs started so far (the
// demo finishes a run on a timer: the sandbox's setTimeout is replaced by a queue, and the run timers in it are
// called; the source syncs a manual ingest run starts are not). After the calls, the Workflow Studio data the B14
// endpoints serve is observed with the demo's own functions: the workflows (S.wf.list), the recent runs (S.wf.runs),
// the attention list (frWfAttn) and, for the workflows the scenario names, what GET /api/screens/workflows/{id}
// returns (frWfHistory, frFailedRows, frRunCounts, wfRunFromLast, wfBuild, wfStat), or null for one that is gone.
import { freshDemo, writeGolden } from '../golden-sandbox.mjs';

const copy = (x) => JSON.parse(JSON.stringify(x));
const graph = (h, id) => copy(h('WFW')(id).graph);
const moved = (g) => { g.nodes[1].x += 8; return g; };
const srcWf = (h, src) => h('S').wf.list.find((w) => w.src === src && w.cat === 'Ingest').id;
const ACCOUNTS = freshDemo()('ACCOUNTS').map((a) => a.id);

const SCENARIOS = {
  save: {
    calls: [
      ['developer', 'workflow.save', (h) => ({ id: 'WF-101', name: '  Ingest · CRM (v2) ', owner: 'Sales Ops', trig: { t: 'schedule', min: 20 }, graph: moved(graph(h, 'WF-101')), note: 'Moved the gateway' })],
      ['admin', 'workflow.save', { id: 'WF-101', name: '   ', graph: { nodes: [], edges: [] } }],
      ['admin', 'workflow.save', { id: 'WF-101', name: 'x' }],
      ['admin', 'workflow.save', { id: 'WF-999', name: 'x', graph: { nodes: [], edges: [] } }],
      ['planner-a', 'workflow.save', { id: 'WF-101', name: 'x', graph: { nodes: [], edges: [] } }],
      ['engineer', 'workflow.save', { id: 'WF-101', name: 'x', graph: { nodes: [], edges: [] } }],
      ['admin', 'workflow.save', (h) => ({ id: 'WF-101', name: 'Ingest · CRM', graph: graph(h, 'WF-101') })],
      ['admin', 'workflow.save', (h) => ({ id: 'WF-133', name: 'Standard six-gate decision', owner: '', trig: {}, graph: graph(h, 'WF-133'), note: '' })],
    ],
    detail: ['WF-101', 'WF-133'],
  },
  publish: {
    calls: [
      ['admin', 'workflow.publish', { id: 'WF-101' }],
      ['admin', 'workflow.publish', { id: 'WF-117' }],
      ['developer', 'workflow.duplicate', { id: 'WF-133' }],
      ['developer', 'workflow.publish', { id: 'WF-100' }],
      ['developer', 'workflow.setStatus', { id: 'WF-100', status: 'draft' }],
      ['developer', 'workflow.publish', (h) => ({ id: 'WF-100', graph: moved(graph(h, 'WF-100')) })],
      ['developer', 'workflow.setStatus', { id: 'WF-100', status: 'draft' }],
      ['developer', 'workflow.publish', (h) => ({ id: 'WF-100', graph: graph(h, 'WF-100') })],
      ['approver', 'workflow.publish', { id: 'WF-117' }],
      ['admin', 'workflow.publish', { id: 'WF-999' }],
      ['admin', 'workflow.create', { type: 'blank' }],
      ['admin', 'workflow.publish', { id: 'WF-136', graph: { nodes: [{ id: 'n1', k: 'conn', ref: 'iot', x: 24, y: 24 }], edges: [] } }],
      ['admin', 'workflow.publish', { id: 'WF-136' }],
    ],
    detail: ['WF-100', 'WF-117', 'WF-136'],
  },
  set_status: {
    calls: [
      ['developer', 'workflow.setStatus', { id: 'WF-101', status: 'paused' }],
      ['developer', 'workflow.setStatus', { id: 'WF-101', status: 'published' }],
      ['developer', 'workflow.setStatus', { id: 'WF-101', status: 'archived' }],
      ['developer', 'workflow.setStatus', { id: 'WF-101' }],
      ['admin', 'workflow.setStatus', { id: 'WF-117', status: 'published' }],
      ['admin', 'workflow.setStatus', { id: 'WF-117', status: 'paused' }],
      ['admin', 'workflow.setStatus', { id: 'WF-118', status: 'draft' }],
      ['finance', 'workflow.setStatus', { id: 'WF-118', status: 'published' }],
      ['admin', 'workflow.setStatus', { id: 'WF-999', status: 'paused' }],
    ],
    detail: ['WF-101', 'WF-117', 'WF-118'],
  },
  create: {
    calls: [
      ['admin', 'workflow.create', { type: 'ingest', src: 'erp' }],
      ['admin', 'workflow.create', { type: 'out', src: 'erp', ch: 'file', name: ' ERP interface file ' }],
      ['admin', 'workflow.create', { type: 'dec' }],
      ['admin', 'workflow.create', { type: 'blank', name: '' }],
      ['admin', 'workflow.create', { type: 'ingest', src: '' }],
      ['admin', 'workflow.create', { type: 'out', src: 'nope' }],
      ['admin', 'workflow.create', { src: 'erp' }],
      ['developer', 'workflow.create', { type: 'ingest', src: 'rcy', ch: '', name: '' }],
      ['developer', 'workflow.create', { type: 'out', src: 'crm', ch: '', name: '' }],
      ['developer', 'workflow.create', { type: 'ingest', src: 'iot' }],
      ['developer', 'workflow.create', { type: 'blank', name: 'Custom', desc: 'Hand-built pipeline', graph: { nodes: [{ id: 'a', k: 'conn', ref: 'erp', x: 24, y: 24 }], edges: [] } }],
      ['developer', 'workflow.create', { type: 'other' }],
      ['engineer', 'workflow.create', { type: 'dec' }],
      ['planner-a', 'workflow.create', { type: 'dec' }],
      ['admin', 'workflow.validate', { id: 'WF-136' }],
      ['admin', 'workflow.validate', { id: 'WF-137' }],
      ['admin', 'workflow.validate', { id: 'WF-142' }],
      ['admin', 'workflow.validate', { id: 'WF-141' }],
    ],
    detail: ['WF-136', 'WF-137', 'WF-138', 'WF-139', 'WF-140', 'WF-141', 'WF-142', 'WF-143'],
  },
  duplicate: {
    calls: [
      ['developer', 'workflow.duplicate', { id: 'WF-101' }],
      ['developer', 'workflow.duplicate', { id: 'WF-116', name: 'Depot copy' }],
      ['developer', 'workflow.duplicate', { id: 'WF-999' }],
      ['planner-b', 'workflow.duplicate', { id: 'WF-101' }],
      ['admin', 'workflow.create', { type: 'blank' }],
      ['admin', 'workflow.duplicate', { id: 'WF-137' }],
      ['admin', 'workflow.duplicate', { id: 'WF-100', name: '' }],
    ],
    detail: ['WF-100', 'WF-136', 'WF-137', 'WF-138', 'WF-139'],
  },
  delete: {
    calls: [
      ['admin', 'workflow.delete', { id: 'WF-120' }],
      ['admin', 'workflow.delete', { id: 'WF-120' }],
      ['developer', 'workflow.create', { type: 'ingest', src: 'erp' }],
      ['developer', 'workflow.delete', { id: 'WF-136' }],
      ['approver', 'workflow.delete', { id: 'WF-101' }],
      ['developer', 'workflow.duplicate', { id: 'WF-101' }],
      ['developer', 'workflow.create', { type: 'dec' }],
    ],
    detail: ['WF-120', 'WF-136', 'WF-100'],
  },
  validate: {
    calls: [
      ['planner-a', 'workflow.validate', { id: 'WF-101' }],
      ['admin', 'workflow.validate', { id: 'WF-999' }],
      ['admin', 'workflow.validate', {}],
      ...Array.from({ length: 35 }, (_, k) => ['admin', 'workflow.validate', { id: 'WF-' + (101 + k) }]),
    ],
    detail: [],
  },
  run_ingest: {
    calls: [
      ['developer', 'workflow.run', { id: 'WF-101' }],
      ['developer', 'workflow.run', { id: 'WF-101' }],
      ['flush'],
      ['admin', 'workflow.run', { id: 'WF-101' }],
      ['flush'],
    ],
    detail: ['WF-101'],
  },
  run_kinds: {
    calls: [
      ['admin', 'workflow.run', { id: 'WF-133' }],
      ['admin', 'workflow.run', { id: 'WF-122' }],
      ['admin', 'workflow.run', { id: 'WF-118' }],
      ['admin', 'workflow.run', (h) => ({ id: srcWf(h, 'rcy') })],
      ['admin', 'workflow.run', { id: 'WF-116' }],
      ['flush'],
    ],
    detail: ['WF-133', 'WF-122', 'WF-118', 'WF-116', 'WF-120'],
  },
  run_draft: {
    calls: [
      ['developer', 'workflow.run', { id: 'WF-117' }],
      ['developer', 'workflow.create', { type: 'dec' }],
      ['developer', 'workflow.run', { id: 'WF-136' }],
      ['flush'],
      ['developer', 'workflow.setStatus', { id: 'WF-117', status: 'paused' }],
      ['developer', 'workflow.run', { id: 'WF-117' }],
      ['flush'],
      ['developer', 'workflow.create', { type: 'blank' }],
      ['developer', 'workflow.run', { id: 'WF-137' }],
      ['flush'],
    ],
    detail: ['WF-117', 'WF-136', 'WF-137'],
  },
  run_failing_step: {
    calls: [
      ['developer', 'workflow.save', (h) => { const g = graph(h, 'WF-105'); g.nodes.find((n) => n.id === 'v').fail = true; return { id: 'WF-105', name: h('WFW')('WF-105').name, graph: g }; }],
      ['developer', 'workflow.run', { id: 'WF-105' }],
      ['flush'],
    ],
    detail: ['WF-105'],
  },
  run_validation_error: {
    calls: [
      ['developer', 'workflow.save', (h) => {
        const g = graph(h, 'WF-102'), c = g.nodes.find((n) => n.k === 'fixed' && n.ref.startsWith('c_'));
        g.nodes = g.nodes.filter((n) => n.id !== 'm');
        g.edges = g.edges.filter((e) => e.a !== 'm' && e.b !== 'm');
        g.edges.push({ id: 'e99', a: 'v', b: c.id, locked: false });
        return { id: 'WF-102', name: h('WFW')('WF-102').name, graph: g, note: 'Skip the mapping' };
      }],
      ['developer', 'workflow.validate', { id: 'WF-102' }],
      ['developer', 'workflow.run', { id: 'WF-102' }],
      ['flush'],
      ['developer', 'workflow.setStatus', { id: 'WF-102', status: 'published' }],
    ],
    detail: ['WF-102'],
  },
  run_deleted_before_it_finished: {
    calls: [
      ['admin', 'workflow.run', { id: 'WF-103' }],
      ['admin', 'workflow.delete', { id: 'WF-103' }],
      ['flush'],
    ],
    detail: ['WF-103'],
  },
  run_refused: {
    calls: [
      ['planner-a', 'workflow.run', { id: 'WF-101' }],
      ['executive', 'workflow.run', { id: 'WF-101' }],
      ['admin', 'workflow.run', { id: 'WF-999' }],
      ['admin', 'workflow.run', {}],
    ],
    detail: [],
  },
};
// every account: may it change a workflow's status, read the checks, run one?
for (const a of ACCOUNTS) {
  SCENARIOS['access_' + a] = {
    calls: [[a, 'workflow.setStatus', { id: 'WF-133', status: 'paused' }], [a, 'workflow.validate', { id: 'WF-117' }], [a, 'workflow.run', { id: 'WF-134' }], ['flush']],
    detail: ['WF-133', 'WF-134'],
  };
}

function observe(h, ids) {
  const S = h('S');
  for (const w of S.wf.list) h('wfGraphOf')(w);
  const detail = {};
  for (const id of ids) {
    const w = h('WFW')(id);
    detail[id] = w ? {
      history: h('frWfHistory')(w),
      failed_rows: h('frFailedRows')(w),
      run_counts: h('frRunCounts')(w),
      run_from_last: h('wfRunFromLast')(w),
      template: h('wfBuild')(w.tpl),
      stat: h('wfStat')(w),
    } : null;
  }
  return { workflows: S.wf.list, runs: S.wf.runs, attention: h('frWfAttn')(), detail };
}

const out = {};
for (const [name, sc] of Object.entries(SCENARIOS)) {
  const h = freshDemo();
  h('wfInit')();
  h('hhInit')();
  for (const w of h('S').wf.list) h('wfGraphOf')(w);
  // the demo finishes runs on a timer: queue the timers, and call the run timers on ['flush']
  h('globalThis.__T=[]');
  h('setTimeout=function(f,ms){__T.push({f:f,ms:ms});return __T.length}');
  h('toast=function(){}'); // a finished manual run says so in a toast, which needs the page
  const flush = () => {
    const T = h('__T').splice(0);
    T.filter((t) => String(t.f).includes('wfSimOutcome')).forEach((t) => t.f());
    h('__T').length = 0;
  };
  const inv = h('invoke'), setA = h('setAcct'), acct = h('ACCT');
  const results = [], calls = [];
  for (const [as, id, input] of sc.calls) {
    if (as === 'flush') { flush(); calls.push({ flush: true }); continue; }
    const inp = typeof input === 'function' ? input(h, results) : input;
    setA(acct(as));
    const r = inv(id, inp);
    calls.push({ as, action: id, input: copy(inp), result: copy(r) });
    results.push(r);
  }
  setA(null);
  out[name] = { calls, observed: observe(h, sc.detail) };
}
console.log('wrote', writeGolden('workflow_writes.json', out));
