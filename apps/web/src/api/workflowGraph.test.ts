import { describe, expect, it } from 'vitest';
import type { BlockSpec, FieldSpec, RunState, Source, StepKind, TestRun, WfGraph, WfNode, Workflow } from './workflows';
import {
  ageShort, analyze, canLink, cfgErrors, compactCfg, evalStep, frAgo, hashId, info, nodeCfg, order, pathXY, runCounts, runTimes, specKey, srcCh, srcLabel, srcOr, trigText,
  validate, wfStat, type Fixed, type Lookups,
} from './workflowGraph';

// ---------------------------------------------------------------- hand-built lookups (shapes as ref() serves them)
const src = (id: string, name: string, status: Source['status'], mode: string, more: Partial<Source> = {}): Source => ({
  id, name, vendor: name + ' Systems', status, mode, auth: 'OAuth 2.0', read: ['GET /records'], write: [], cat: 'internal', fresh: '4 min',
  owner: 'Ops', type: id, ...more,
});
const xf = (id: string, label: string, more: Record<string, unknown> = {}) => ({ id, label, sub: label + ' sub', desc: '', ...more });
const fx = (label: string, more: Partial<Fixed> = {}): Fixed => ({ label, sub: label + ' sub', desc: '', in: true, out: true, ...more });
// the Connection Fabric's steps (FR_XF); as in the real reference data, XF carries them too
const FR = [
  xf('x_sched', 'Scheduler', { start: true, group: 'orch' }),
  xf('x_err', 'Error handler', { sink: true, group: 'branch' }),
  xf('x_audit', 'Write to audit log', { sink: true, group: 'branch' }),
  xf('x_pub', 'Publish to event stream', { sink: true, group: 'branch' }),
];
const L: Lookups = {
  sources: [
    src('crm', 'CRM', 'live', 'API extractor · API + events', { write: ['POST /task'] }),
    src('erp', 'ERP', 'live', 'SFTP drop · CSV'),
    src('old', 'Old ledger', 'stale', 'API extractor', { fresh: '3 days' }),
    src('off', 'Offline', 'unavailable', '—'),
    src('man', 'Spreadsheet', 'manual', 'Manual upload'),
  ],
  mappings: { crm: [['Opportunity.Amount', 'value']], erp: [['MATNR', 'sku']], old: [['a', 'b']], man: [['a', 'b']] },
  XF: [
    xf('x_gw', 'API gateway', { group: 'ingest', ingest: 'api' }),
    xf('x_evt', 'Event ingestion', { group: 'ingest', ingest: 'event' }),
    xf('x_val', 'Validation & enrichment', { group: 'ingest' }),
    xf('x_unzip', 'Download and unzip', { group: 'file', fileIn: true }),
    xf('x_cb', 'Fetch import log', { group: 'file' }),
    xf('x_notify', 'Notify with log links', { group: 'file' }),
    xf('x_utc', 'Timestamps to UTC'),
    xf('x_env', 'Instruction envelope'),
    ...FR,
  ],
  FR_XF: FR,
  FXD: {
    c_dem: fx('Demand opportunity', { canon: true, model: 'Demand opportunity' }),
    c_asset: fx('Asset & component', { canon: true, model: 'Asset & component' }),
    c_dec: fx('Decision', { canon: true, model: 'Decision', start: true }),
    c_out: fx('Outcome', { canon: true, model: 'Outcome' }),
    appr: fx('Human approval'),
    gates: fx('Six eligibility gates'),
    evid: fx('Case evidence', { in: false }),
    snap: fx('Evidence snapshot', { out: false }),
  },
  ACT_TYPES: [
    { id: 'a_api', ch: 'api', label: 'Outbound API call', sub: 'REST / SOAP request', desc: '' },
    { id: 'a_file', ch: 'file', label: 'File generation', sub: 'Flat file', desc: '' },
  ],
  TOOLS: [
    { id: 'send_instruction', rw: 'write', approval: 'Approver', desc: '' },
    { id: 'find_demand', rw: 'read', approval: 'none', desc: '' },
  ],
  MAP_TARGET: { crm: 'Demand opportunity', erp: 'Demand opportunity', old: 'Asset & component', off: 'Asset & component', man: 'Asset & component' },
  SH: { crm: 'CRM', erp: 'ERP', old: 'Old ledger', off: 'Offline', man: 'Spreadsheet', gone: 'Retired WMS' },
  DELIVER: { crm: ['api'] },
  CH_ARR: { api: 'API calls', event: 'events', file: 'files' },
  CH_DEL: { api: 'REST API calls', event: 'events', file: 'files', proc: 'process orchestration' },
};

type N = [id: string, k: StepKind, ref: string];
function G(nodes: N[], edges: [string, string][] = []): WfGraph {
  return {
    nodes: nodes.map(([id, k, ref], i) => ({ id, k, ref, x: i * 200, y: 0 })),
    edges: edges.map(([a, b], i) => ({ id: 'e' + i, a, b, locked: false })),
  };
}
const checks = (g: WfGraph, kind: 'pipe' | 'dec' = 'pipe') => validate(L, g, kind).map((c) => [c.sev, c.id, c.msg]);
const checksOn = (g: WfGraph, id: string, kind: 'pipe' | 'dec' = 'pipe') => checks(g, kind).filter((c) => c[1] === id);

// a clean ingest pipeline: connector → ingestion → validation → mapping → canonical model, with its branches
const GOOD: N[] = [['r', 'conn', 'crm'], ['ig', 'xf', 'x_gw'], ['v', 'xf', 'x_val'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem'], ['err', 'xf', 'x_err'], ['pub', 'xf', 'x_pub']];
const GOOD_E: [string, string][] = [['r', 'ig'], ['ig', 'v'], ['v', 'm'], ['m', 'dem'], ['v', 'err'], ['dem', 'pub']];

// ---------------------------------------------------------------- validate
describe('validate: a well-formed pipeline', () => {
  it('has no errors, warnings or notes', () => {
    expect(checks(G(GOOD, GOOD_E))).toEqual([]);
  });
});

describe('validate: nothing starts or feeds a step', () => {
  it('warns that an unfed canonical model has an evidence gap (pipelines only)', () => {
    const g = G([['dem', 'fixed', 'c_dem']]);
    expect(checks(g)).toEqual([['warn', 'dem', 'Nothing feeds Demand opportunity. AI services will report an evidence gap.']]);
    expect(checks(g, 'dec')).toEqual([]);
  });
  it('does not ask for an input on Decision or Outcome', () => {
    expect(checks(G([['d', 'fixed', 'c_dec'], ['o', 'fixed', 'c_out']]))).toEqual([]);
  });
  it('warns about a read connector wired to nothing', () => {
    expect(checks(G([['r', 'conn', 'crm']]))).toEqual([['warn', 'r', 'CRM is not wired into the workflow.']]);
  });
  it('warns about a connector that never reaches a canonical model', () => {
    expect(checks(G([['r', 'conn', 'crm'], ['u', 'xf', 'x_utc']], [['r', 'u']]))).toEqual([
      ['warn', 'r', 'CRM does not reach a canonical model.'],
      ['warn', 'u', 'Timestamps to UTC is not wired between a source and a target.'],
    ]);
  });
});

describe('validate: unconnected steps', () => {
  it('warns about a transform with no input or no output', () => {
    expect(checks(G([['u', 'xf', 'x_utc']]))).toEqual([['warn', 'u', 'Timestamps to UTC is not wired between a source and a target.']]);
    expect(checksOn(G([['r', 'conn', 'crm'], ['u', 'xf', 'x_utc']], [['r', 'u']]), 'u')).toHaveLength(1);
  });
  it('lets the notification end a workflow, but wants Fetch import log before it', () => {
    const g = G([['u', 'xf', 'x_utc'], ['n', 'xf', 'x_notify']], [['u', 'n']]);
    expect(checksOn(g, 'n')).toEqual([['error', 'n', 'The notification carries log links, so it follows Fetch import log.']]);
  });
  it('warns about a field mapping that is not fed, and one that leads nowhere', () => {
    expect(checksOn(G([['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['m', 'dem']]), 'm')).toEqual([
      ['warn', 'm', 'CRM fields is not fed by a connector.'],
    ]);
    expect(checksOn(G([['r', 'conn', 'crm'], ['m', 'map', 'crm']], [['r', 'm']]), 'm')).toEqual([
      ['warn', 'm', 'CRM fields does not lead to a canonical model.'],
    ]);
  });
});

describe('validate: connectors and field mappings', () => {
  it('stops raw vendor values entering a canonical model without a mapping', () => {
    const g = G([['r', 'conn', 'crm'], ['ig', 'xf', 'x_gw'], ['v', 'xf', 'x_val'], ['dem', 'fixed', 'c_dem']], [['r', 'ig'], ['ig', 'v'], ['v', 'dem']]);
    expect(checks(g)).toEqual([
      ['error', 'r', 'CRM reaches Demand opportunity without a field mapping. Raw vendor values would enter the canonical model.'],
    ]);
  });
  it('warns when a mapped path skips ingestion or validation', () => {
    const both = G([['r', 'conn', 'crm'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['r', 'm'], ['m', 'dem']]);
    expect(checks(both)).toEqual([
      ['warn', 'r', 'CRM reaches the models without an ingestion channel or validation and enrichment. Access, ordering and bad rows are then not handled in one place.'],
    ]);
    const noVal = G([['r', 'conn', 'crm'], ['ig', 'xf', 'x_gw'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['r', 'ig'], ['ig', 'm'], ['m', 'dem']]);
    expect(checks(noVal)).toEqual([
      ['warn', 'r', 'CRM reaches the models without validation and enrichment. Access, ordering and bad rows are then not handled in one place.'],
    ]);
  });
  it('rejects an ingestion channel the source does not deliver on', () => {
    const g = G([['r', 'conn', 'erp'], ['ig', 'xf', 'x_gw'], ['v', 'xf', 'x_val'], ['m', 'map', 'erp'], ['dem', 'fixed', 'c_dem']], [['r', 'ig'], ['ig', 'v'], ['v', 'm'], ['m', 'dem']]);
    expect(checks(g)).toEqual([['error', 'ig', 'API gateway receives ERP, which does not arrive as API calls.']]);
  });
  it('wants a file for file steps', () => {
    const g = G([['r', 'conn', 'crm'], ['z', 'xf', 'x_unzip'], ['u', 'xf', 'x_utc']], [['r', 'z'], ['z', 'u']]);
    expect(checksOn(g, 'z')).toEqual([['error', 'z', 'Download and unzip needs a file to work on, but CRM does not deliver files.']]);
    const ok = G([['r', 'conn', 'erp'], ['z', 'xf', 'x_unzip'], ['u', 'xf', 'x_utc']], [['r', 'z'], ['z', 'u']]);
    expect(checksOn(ok, 'z')).toEqual([]);
  });
  it('checks what feeds a mapping and where it leads', () => {
    expect(checksOn(G([['r', 'conn', 'erp'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['r', 'm'], ['m', 'dem']]), 'm')).toEqual([
      ['error', 'm', 'CRM fields is fed by ERP. Field names would not line up.'],
    ]);
    expect(checksOn(G([['u', 'xf', 'x_utc'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['u', 'm'], ['m', 'dem']]), 'm')).toEqual([
      ['error', 'm', 'CRM fields has no connector upstream, so there is nothing to map.'],
    ]);
    expect(checksOn(G([['r', 'conn', 'crm'], ['m', 'map', 'crm'], ['a', 'fixed', 'c_asset']], [['r', 'm'], ['m', 'a']]), 'm')).toEqual([
      ['error', 'm', 'CRM fields maps to Demand opportunity, but it is wired to Asset & component.'],
    ]);
    expect(checksOn(G([['r', 'conn', 'off'], ['m', 'map', 'off'], ['a', 'fixed', 'c_asset']], [['r', 'm'], ['m', 'a']]), 'm')).toEqual([
      ['error', 'm', 'No field mapping is defined for Offline yet.'],
    ]);
  });
  it('reports a deleted source once and checks nothing else on that step', () => {
    expect(checks(G([['g', 'conn', 'gone']]))).toEqual([['error', 'g', 'Retired WMS was deleted from the Source map. Reconnect it or remove this step.']]);
    expect(checks(G([['g', 'map', 'nowhere']]))).toEqual([['error', 'g', 'This source was deleted from the Source map. Reconnect it or remove this step.']]);
  });
  it('reports source health, errors first, then warnings, then notes', () => {
    const g = G([['s', 'conn', 'man'], ['o', 'conn', 'old'], ['f', 'conn', 'off']]);
    const c = checks(g);
    expect(c.map((x) => x[0])).toEqual(['error', 'warn', 'warn', 'warn', 'warn', 'info']);
    expect(c).toContainEqual(['error', 'f', 'Offline has no connected feed. Circularity will not infer data, so this evidence would be missing.']);
    expect(c).toContainEqual(['warn', 'o', 'Old ledger is 3 days old. Predictions fall back to the last fresh data and say so.']);
    expect(c).toContainEqual(['info', 's', 'Spreadsheet is a manual import. It supports evaluation, not live automation.']);
  });
});

describe('validate: error handler and publish rules', () => {
  it('wants Validation & enrichment before the Error handler', () => {
    const g = G([['r', 'conn', 'crm'], ['ig', 'xf', 'x_gw'], ['err', 'xf', 'x_err']], [['r', 'ig'], ['ig', 'err']]);
    expect(checksOn(g, 'err')).toEqual([
      ['error', 'err', 'Error handler receives the records that fail validation, so it follows Validation & enrichment.'],
    ]);
  });
  it('wants a canonical model before Publish to event stream', () => {
    const g = G(GOOD, [...GOOD_E.filter(([a, b]) => !(a === 'dem' && b === 'pub')), ['v', 'pub']]);
    expect(checksOn(g, 'pub')).toEqual([
      ['error', 'pub', 'Publish to event stream announces a model update, so it follows a canonical model.'],
    ]);
  });
  it('only warns about an unfed publish step (no publish error without an input)', () => {
    expect(checks(G([['pub', 'xf', 'x_pub']]))).toEqual([['warn', 'pub', 'Publish to event stream is not wired between a source and a target.']]);
  });
});

describe('validate: Connection Fabric overrides', () => {
  it('a start step needs no input', () => {
    expect(checksOn(G([['s', 'xf', 'x_sched'], ['u', 'xf', 'x_utc']], [['s', 'u']]), 's')).toEqual([]);
  });
  it('a start step that is fed is warned about', () => {
    const g = G([['u', 'xf', 'x_utc'], ['s', 'xf', 'x_sched'], ['u2', 'xf', 'x_utc']], [['u', 's'], ['s', 'u2']]);
    expect(checksOn(g, 's')).toEqual([['warn', 's', 'Scheduler starts a workflow, so nothing should feed it.']]);
  });
  it('a sink step needs no output', () => {
    const g = G([...GOOD, ['aud', 'xf', 'x_audit']], [...GOOD_E, ['m', 'aud']]);
    expect(checks(g)).toEqual([]);
  });
  it('unwired start and sink steps are still reported', () => {
    expect(checks(G([['s', 'xf', 'x_sched']]))).toEqual([['warn', 's', 'Scheduler is not wired between a source and a target.']]);
    expect(checks(G([['a', 'xf', 'x_audit']]))).toEqual([['warn', 'a', 'Write to audit log is not wired between a source and a target.']]);
  });
  it('a start step with no output is still reported', () => {
    expect(checks(G([['u', 'xf', 'x_utc'], ['s', 'xf', 'x_sched']], [['u', 's']]))).toContainEqual(
      ['warn', 's', 'Scheduler is not wired between a source and a target.'],
    );
  });
});

describe('validate: delivery and approval', () => {
  const OUT: N[] = [['gates', 'fixed', 'gates'], ['appr', 'fixed', 'appr'], ['env', 'xf', 'x_env'], ['act', 'act', 'a_api'], ['w', 'wconn', 'crm']];
  const OUT_E: [string, string][] = [['gates', 'appr'], ['appr', 'env'], ['env', 'act'], ['act', 'w']];
  it('accepts approval → envelope → delivery → write connector', () => {
    expect(checks(G(OUT, OUT_E), 'dec')).toEqual([]);
  });
  it('rejects a path that bypasses Human approval', () => {
    const c = checks(G(OUT, [...OUT_E, ['gates', 'act']]), 'dec');
    expect(c).toEqual([
      ['error', 'act', 'Outbound API call bypasses Human approval. Anything that commits stock, spend or price always stops at a person.'],
      ['error', 'w', 'Writes to CRM bypass Human approval. Anything that commits stock, spend or price always stops at a person.'],
    ]);
  });
  it('wants an Instruction envelope before delivery', () => {
    const g = G(OUT.filter((n) => n[0] !== 'env'), [['gates', 'appr'], ['appr', 'act'], ['act', 'w']]);
    expect(checks(g, 'dec')).toEqual([
      ['error', 'act', 'Outbound API call needs an Instruction envelope upstream, so the receiving system can trace and de-duplicate it.'],
      ['error', 'w', 'Writes to CRM need an Instruction envelope. Without the decision ID and approval reference, the receiving system cannot trace or de-duplicate it.'],
    ]);
  });
  it('checks the receiving system accepts the delivery method', () => {
    const g = G(OUT.map((n) => (n[0] === 'act' ? (['act', 'act', 'a_file'] as N) : n)), OUT_E);
    expect(checks(g, 'dec')).toEqual([['error', 'act', 'CRM does not accept files. It accepts REST API calls.']]);
  });
  it('warns about unwired delivery steps and write connectors', () => {
    expect(checks(G([['act', 'act', 'a_api']]), 'dec')).toEqual([['warn', 'act', 'Outbound API call is not wired to receive an instruction.']]);
    expect(checksOn(G(OUT.slice(0, 4), OUT_E.slice(0, 3)), 'act', 'dec')).toEqual([
      ['warn', 'act', 'Outbound API call does not lead to a system that receives it.'],
    ]);
    expect(checks(G([['w', 'wconn', 'off']]), 'dec')).toEqual([
      ['error', 'w', 'Offline has no connected system to write to.'],
      ['warn', 'w', 'Offline is not wired to receive an instruction.'],
    ]);
    expect(checksOn(G([['w', 'wconn', 'old']]), 'w', 'dec')[0]).toEqual(['warn', 'w', 'Old ledger has an expired token. Instructions would queue until it is refreshed.']);
  });
});

describe('validate: decision workflows and agent tools', () => {
  it('warns when the approved decision is not carried out', () => {
    expect(checks(G([['c_dec', 'fixed', 'c_dec']]), 'dec')).toEqual([
      ['warn', 'c_dec', 'The approved decision is not carried out. Add send_instruction after the Decision record.'],
    ]);
  });
  it('wants send_instruction after approval and the Decision record', () => {
    const early = G([['c_dec', 'fixed', 'c_dec'], ['send', 'tool', 'send_instruction']], [['c_dec', 'send']]);
    expect(checks(early, 'dec')).toEqual([
      ['error', 'send', 'send_instruction has to come after Human approval. Instructions go out only after a person approves and the Decision record carries the approval reference.'],
    ]);
    const ok = G([['appr', 'fixed', 'appr'], ['c_dec', 'fixed', 'c_dec'], ['send', 'tool', 'send_instruction']], [['appr', 'c_dec'], ['c_dec', 'send']]);
    expect(checks(ok, 'dec')).toEqual([]);
  });
  it('orders find_demand between Case evidence and the gates', () => {
    expect(checks(G([['fd', 'tool', 'find_demand']]), 'dec')).toEqual([['warn', 'fd', 'find_demand is not wired in.']]);
    const why = 'Demand fit is gate 4, so demand has to be found before the gates run.';
    expect(checks(G([['evid', 'fixed', 'evid'], ['fd', 'tool', 'find_demand']], [['evid', 'fd']]), 'dec')).toEqual([
      ['error', 'fd', 'find_demand has to come before Six eligibility gates. ' + why],
    ]);
    expect(checks(G([['fd', 'tool', 'find_demand'], ['gates', 'fixed', 'gates']], [['fd', 'gates']]), 'dec')).toEqual([
      ['error', 'fd', 'find_demand has to come after Case evidence. ' + why],
    ]);
    const ok = G([['evid', 'fixed', 'evid'], ['fd', 'tool', 'find_demand'], ['gates', 'fixed', 'gates']], [['evid', 'fd'], ['fd', 'gates']]);
    expect(checks(ok, 'dec')).toEqual([]);
  });
});

// ---------------------------------------------------------------- run order, analysis and link checks
describe('order and analyze', () => {
  it('runs steps in dependency order, breadth first in edge order', () => {
    const g = G([['d', 'xf', 'x_utc'], ['c', 'xf', 'x_utc'], ['b', 'xf', 'x_utc'], ['a', 'conn', 'crm']], [['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd']]);
    expect(order(g)).toEqual(['a', 'b', 'c', 'd']);
  });
  it('leaves out steps caught in a loop', () => {
    expect(order(G([['x', 'xf', 'x_utc'], ['y', 'xf', 'x_utc'], ['z', 'xf', 'x_utc']], [['x', 'y'], ['y', 'x']]))).toEqual(['z']);
  });
  it('ignores connections to steps that no longer exist', () => {
    const g = G([['a', 'conn', 'crm'], ['b', 'xf', 'x_utc']], [['a', 'ghost'], ['a', 'b']]);
    const A = analyze(g);
    expect(A.succ.a).toEqual(['b']);
    expect(order(g)).toEqual(['a', 'b']);
  });
  it('finds ancestors and descendants', () => {
    const A = analyze(G([['a', 'conn', 'crm'], ['b', 'xf', 'x_utc'], ['c', 'xf', 'x_utc']], [['a', 'b'], ['b', 'c']]));
    expect([...A.anc('c')].sort()).toEqual(['a', 'b']);
    expect([...A.desc('a')].sort()).toEqual(['b', 'c']);
    expect(A.desc('c').size).toBe(0);
  });
});

describe('canLink', () => {
  const g = G([['r', 'conn', 'crm'], ['u', 'xf', 'x_utc'], ['u2', 'xf', 'x_utc'], ['snap', 'fixed', 'snap'], ['appr', 'fixed', 'appr'], ['gates', 'fixed', 'gates']], [['r', 'u'], ['u', 'u2']]);
  it('allows a new forward connection', () => {
    expect(canLink(L, g, 'r', 'u2')).toBeNull();
  });
  it('explains every refusal', () => {
    expect(canLink(L, g, 'r', 'nope')).toBe('That step no longer exists.');
    expect(canLink(L, g, 'u', 'u')).toBe('A step cannot connect to itself.');
    expect(canLink(L, g, 'snap', 'u')).toBe('Evidence snapshot has no output.');
    expect(canLink(L, g, 'u', 'r')).toBe('CRM takes no input. Read connectors are where data starts.');
    expect(canLink(L, g, 'appr', 'gates')).toBe('Fixed steps are wired by Circularity and cannot be re-wired.');
    expect(canLink(L, g, 'r', 'u')).toBe('Those two steps are already connected.');
    expect(canLink(L, g, 'u2', 'u')).toBe('That would create a loop.');
  });
});

// ---------------------------------------------------------------- the test run
const run = (states: Record<string, RunState>, approved = true): TestRun => ({
  status: 'running', states, dur: {}, order: [], i: 0, approved, t0: 0, id: 'RUN-1', trig: 'Manual',
});

describe('evalStep', () => {
  const g = G([['r', 'conn', 'crm'], ['u', 'xf', 'x_utc'], ['appr', 'fixed', 'appr']], [['r', 'u'], ['u', 'appr']]);
  const A = analyze(g), n = (id: string) => A.by[id];
  it('follows the states upstream', () => {
    expect(evalStep(L, run({ r: 'failed' }), A, n('u'))).toBe('upstream_failed');
    expect(evalStep(L, run({ r: 'upstream_failed' }), A, n('u'))).toBe('upstream_failed');
    expect(evalStep(L, run({ r: 'held' }), A, n('u'))).toBe('waiting');
    expect(evalStep(L, run({ r: 'skipped' }), A, n('u'))).toBe('skipped');
    expect(evalStep(L, run({ r: 'success' }), A, n('u'))).toBe('success');
  });
  it('holds at Human approval until approved', () => {
    expect(evalStep(L, run({ u: 'success' }, false), A, n('appr'))).toBe('held');
    expect(evalStep(L, run({ u: 'success' }, true), A, n('appr'))).toBe('success');
  });
  it('fails a step marked to fail', () => {
    expect(evalStep(L, run({ r: 'success' }), A, { ...n('u'), fail: true })).toBe('failed');
  });
  it('reads connectors from their source health', () => {
    const one = (k: StepKind, ref: string) => { const h = G([['x', k, ref]]); return evalStep(L, run({}), analyze(h), h.nodes[0]); };
    expect(one('conn', 'crm')).toBe('success');
    expect(one('conn', 'off')).toBe('failed');
    expect(one('conn', 'old')).toBe('warning');
    expect(one('wconn', 'crm')).toBe('skipped'); // a write connector needs an instruction
    expect(one('fixed', 'c_dec')).toBe('success'); // a start step needs no input
    expect(one('fixed', 'evid')).toBe('success'); // takes no input
    expect(one('fixed', 'gates')).toBe('skipped');
  });
});

describe('runTimes', () => {
  const r: TestRun = {
    ...run({ a: 'success', b: 'skipped', c: 'failed', d: 'queued' }), order: ['a', 'b', 'c', 'd'], dur: { a: 1.5, b: 9, c: '2', d: 4 }, t0: 1000,
  };
  it('lays steps end to end, with a 120 ms gap after each that ran', () => {
    expect(runTimes(r, 99)).toEqual({
      a: { s: 1000, e: 2500, d: 1.5, ex: true },
      b: { s: 2620, e: 2620, d: 0, ex: false },
      c: { s: 2620, e: 4620, d: 2, ex: true },
      d: { s: 4740, e: 4740, d: 0, ex: false },
    });
  });
  it('is deterministic and starts at now only without a start time', () => {
    expect(runTimes(r, 99)).toEqual(runTimes(r, 12345));
    expect(runTimes({ ...r, t0: 0 }, 5000).a).toEqual({ s: 5000, e: 6500, d: 1.5, ex: true });
  });
});

describe('runCounts', () => {
  const w = { id: 'WF-T', last: { ts: 0, state: 'success', dur: 1, rows: 1000, note: '' } } as unknown as Workflow;
  const g = G([['r', 'conn', 'crm'], ['v', 'xf', 'x_val'], ['err', 'xf', 'x_err'], ['m', 'map', 'crm'], ['dem', 'fixed', 'c_dem']], [['r', 'v'], ['v', 'err'], ['v', 'm'], ['m', 'dem']]);
  const all = (s: RunState) => Object.fromEntries(g.nodes.map((n) => [n.id, s]));
  it('validation rejects a fixed share into the error handler', () => {
    // 1000 rows × (0.004 + hashId('WF-Trej') % 9 / 1000) = 12
    expect(runCounts(w, g, all('success'))).toEqual({
      r: { in: 1000, out: 1000, rej: 0 }, v: { in: 1000, out: 988, rej: 12 }, err: { in: 12, out: 12, rej: 0 },
      m: { in: 988, out: 988, rej: 0 }, dem: { in: 988, out: 988, rej: 0 },
    });
  });
  it('is the same every time', () => {
    expect(runCounts(w, g, all('success'))).toEqual(runCounts(w, g, all('success')));
  });
  it('passes nothing on from failed, upstream-failed or skipped steps', () => {
    const c = runCounts(w, g, { r: 'success', v: 'failed', err: 'upstream_failed', m: 'upstream_failed', dem: 'skipped' });
    expect(c.v).toEqual({ in: 1000, out: 0, rej: 0 });
    expect(c.err).toEqual({ in: 0, out: 0, rej: 0 });
    expect(c.m).toEqual({ in: 0, out: 0, rej: 0 });
  });
  it('counts nothing for a workflow that never ran', () => {
    const c = runCounts({ ...w, last: null }, g, all('success'));
    expect(Object.values(c).every((x) => x.in === 0 && x.out === 0 && x.rej === 0)).toBe(true);
  });
});

// ---------------------------------------------------------------- small helpers
describe('hashId', () => {
  it('is 32-bit FNV-1a as 8 upper-case hex digits', () => {
    expect(hashId('')).toBe('811C9DC5');
    expect(hashId('a')).toBe('E40C292C');
    expect(hashId('WF-Trej')).toBe('F772AF12');
    expect(hashId('WF-101')).toMatch(/^[0-9A-F]{8}$/);
    expect(hashId('WF-101')).not.toBe(hashId('WF-102'));
  });
});

describe('trigText', () => {
  it('describes each trigger, defaulting to Manual', () => {
    expect(trigText({ t: 'schedule', min: 30 })).toBe('Every 30 min');
    expect(trigText({ t: 'event' })).toBe('On event');
    expect(trigText({ t: 'approval' })).toBe('On approval');
    expect(trigText({ t: 'manual' })).toBe('Manual');
    expect(trigText({ t: 'case' })).toBe('On case request');
    expect(trigText({ t: 'file' })).toBe('On file arrival');
    expect(trigText({ t: 'whatever' })).toBe('Manual');
  });
});

describe('ageShort and frAgo', () => {
  it('ageShort', () => {
    expect(ageShort(-5000)).toBe('0 s');
    expect(ageShort(59_999)).toBe('59 s');
    expect(ageShort(61_000)).toBe('1 min 1 s');
    expect(ageShort(3_600_000)).toBe('1 h 0 min');
    expect(ageShort(172_799_000)).toBe('47 h 59 min');
    expect(ageShort(172_800_000)).toBe('2 days');
  });
  it('frAgo', () => {
    expect(frAgo(1_500)).toBe('2 sec ago');
    expect(frAgo(120_000)).toBe('2 min ago');
    expect(frAgo(7_200_000)).toBe('2 h ago');
    expect(frAgo(3 * 86_400_000)).toBe('3 days ago');
  });
});

describe('wfStat', () => {
  const w = (status: Workflow['status'], state: RunState | null) => ({ status, last: state ? { state } : null }) as unknown as Workflow;
  it('a published workflow whose last run failed is failing', () => {
    expect(wfStat(w('published', 'failed'))).toBe('failing');
    expect(wfStat(w('published', 'success'))).toBe('published');
    expect(wfStat(w('published', null))).toBe('published');
    expect(wfStat(w('paused', 'failed'))).toBe('paused');
  });
});

describe('sources and step info', () => {
  it('srcOr stands in for a deleted source', () => {
    expect(srcOr(L, 'crm').name).toBe('CRM');
    expect(srcOr(L, 'gone')).toMatchObject({ id: 'gone', name: 'Retired WMS', deleted: true, status: 'unavailable' });
    expect(srcOr(L, 'nowhere').name).toBe('Deleted source');
  });
  it('srcLabel adds the vendor only when two sources share a name', () => {
    const twin = { ...L, sources: [...L.sources, src('crm2', 'CRM', 'live', 'API', { vendor: 'HubSpot' })] };
    expect(srcLabel(L, L.sources[0])).toBe('CRM');
    expect(srcLabel(twin, twin.sources[0])).toBe('CRM · CRM Systems');
    expect(srcLabel(twin, twin.sources[5])).toBe('CRM · HubSpot');
  });
  it('srcCh reads the channels from mode and auth', () => {
    expect(srcCh(L.sources[0])).toEqual(['api', 'event']);
    expect(srcCh(L.sources[1])).toEqual(['file']);
    expect(srcCh(src('x', 'X', 'live', 'Polling', { auth: 'Webhook signature' }))).toEqual(['api', 'event']);
  });
  it('info labels each kind of step', () => {
    const i = (k: StepKind, ref: string) => info(L, { id: 'n', k, ref, x: 0, y: 0 });
    expect(i('fixed', 'c_dem')).toMatchObject({ label: 'Demand opportunity', tag: 'Fixed · canonical model', in: true, out: true });
    expect(i('fixed', 'appr').tag).toBe('Fixed · platform');
    expect(i('conn', 'crm')).toMatchObject({ label: 'CRM', sub: 'CRM Systems · API extractor · API + events', tag: 'Connector · read', in: false });
    expect(i('wconn', 'crm')).toMatchObject({ sub: 'POST /task', tag: 'Connector · write', in: true });
    expect(i('wconn', 'erp').sub).toBe('No write operations');
    expect(i('conn', 'gone')).toMatchObject({ label: 'Deleted source', sub: 'Reconnect or remove this step' });
    expect(i('map', 'crm')).toMatchObject({ label: 'CRM fields', sub: '→ Demand opportunity · 1 mapped', tag: 'Field mapping' });
    expect(i('xf', 'x_gw').tag).toBe('Integration layer');
    expect(i('xf', 'x_unzip').tag).toBe('File exchange');
    expect(i('xf', 'x_utc').tag).toBe('Transform');
    expect(i('act', 'a_api')).toMatchObject({ label: 'Outbound API call', tag: 'Delivery method' });
    expect(i('tool', 'send_instruction')).toMatchObject({ label: 'send_instruction', sub: 'Write · Approver', tag: 'Agent tool' });
    expect(i('tool', 'find_demand').sub).toBe('Read · no approval needed');
  });
});

describe('pathXY', () => {
  it('draws a curve forward', () => {
    expect(pathXY(0, 0, 100, 40)).toBe('M0 0C50 0 50 40 100 40');
    expect(pathXY(0, 0, 20, 0)).toBe('M0 0C18 0 2 0 20 0'); // control offset at least 18
    expect(pathXY(0, 0, 400, 0)).toBe('M0 0C90 0 310 0 400 0'); // and at most 90
  });
  it('detours with rounded corners going backward', () => {
    const d = pathXY(300, 100, 100, 100);
    expect(d.startsWith('M300 100L')).toBe(true);
    expect(d.endsWith('L100 100')).toBe(true);
    expect(d.match(/Q/g)).toHaveLength(4);
  });
});

// ---------------------------------------------------------------- seeded workflows (golden data)
// Trimmed from fixtures/golden/screens/workflows.json (starting, detail.*.run_counts, detail.*.run_from_last.order),
// fixtures/golden/screens/reference.json and integration.json (descriptions blanked). The golden
// workflow.validate answers (fixtures/golden/workflow_writes.json, validate) show no errors and no warnings for both.
const GOLDEN = {
  workflows: [
    {
      id: 'WF-101', kind: 'pipe' as const, last: {dur:5,note:"",rows:69,state:"success",ts:1791363496000},
      graph: {
        nodes: [
          {id:"r",k:"conn",ref:"crm",x:24,y:170},
          {id:"ig0",k:"xf",ref:"x_gw",x:230,y:90},
          {id:"ig1",k:"xf",ref:"x_evt",x:230,y:250},
          {id:"v",k:"xf",ref:"x_val",x:436,y:170},
          {id:"t",k:"xf",ref:"x_utc",x:642,y:170},
          {id:"m",k:"map",ref:"crm",x:848,y:170},
          {id:"c_dem",k:"fixed",ref:"c_dem",x:1054,y:170},
          {id:"snap",k:"fixed",ref:"snap",x:1260,y:170},
          {id:"err",k:"xf",ref:"x_err",x:436,y:340},
          {id:"aud",k:"xf",ref:"x_audit",x:848,y:340},
          {id:"pub",k:"xf",ref:"x_pub",x:1054,y:20},
        ],
        edges: [
          {a:"r",b:"ig0",id:"e0",locked:false},
          {a:"r",b:"ig1",id:"e1",locked:false},
          {a:"ig0",b:"v",id:"e2",locked:false},
          {a:"ig1",b:"v",id:"e3",locked:false},
          {a:"v",b:"t",id:"e4",locked:false},
          {a:"t",b:"m",id:"e5",locked:false},
          {a:"m",b:"c_dem",id:"e6",locked:false},
          {a:"c_dem",b:"snap",id:"e7",locked:true},
          {a:"v",b:"err",id:"e8",locked:false},
          {a:"m",b:"aud",id:"e9",locked:false},
          {a:"c_dem",b:"pub",id:"e10",locked:false},
        ],
      },
      states: {aud:"success",c_dem:"success",err:"success",ig0:"success",ig1:"success",m:"success",pub:"success",r:"success",snap:"success",t:"success",v:"success"},
      runCounts: {aud:{in:68,out:68,rej:0},c_dem:{in:68,out:68,rej:0},err:{in:1,out:1,rej:0},ig0:{in:69,out:69,rej:0},ig1:{in:69,out:69,rej:0},m:{in:68,out:68,rej:0},pub:{in:68,out:68,rej:0},r:{in:69,out:69,rej:0},snap:{in:68,out:68,rej:0},t:{in:68,out:68,rej:0},v:{in:69,out:68,rej:1}},
      runOrder: ["r","ig0","ig1","v","t","err","m","c_dem","aud","snap","pub"],
    },
    {
      id: 'WF-105', kind: 'pipe' as const, last: {dur:5.7,note:"",rows:422,state:"success",ts:1791363160000},
      graph: {
        nodes: [
          {id:"r",k:"conn",ref:"proc",x:24,y:170},
          {id:"ig0",k:"xf",ref:"x_gw",x:230,y:170},
          {id:"v",k:"xf",ref:"x_val",x:436,y:170},
          {id:"t",k:"xf",ref:"x_fx",x:642,y:170},
          {id:"m",k:"map",ref:"proc",x:848,y:170},
          {id:"c_dem",k:"fixed",ref:"c_dem",x:1054,y:170},
          {id:"snap",k:"fixed",ref:"snap",x:1260,y:170},
          {id:"err",k:"xf",ref:"x_err",x:436,y:340},
          {id:"aud",k:"xf",ref:"x_audit",x:848,y:340},
          {id:"pub",k:"xf",ref:"x_pub",x:1054,y:20},
        ],
        edges: [
          {a:"r",b:"ig0",id:"e0",locked:false},
          {a:"ig0",b:"v",id:"e1",locked:false},
          {a:"v",b:"t",id:"e2",locked:false},
          {a:"t",b:"m",id:"e3",locked:false},
          {a:"m",b:"c_dem",id:"e4",locked:false},
          {a:"c_dem",b:"snap",id:"e5",locked:true},
          {a:"v",b:"err",id:"e6",locked:false},
          {a:"m",b:"aud",id:"e7",locked:false},
          {a:"c_dem",b:"pub",id:"e8",locked:false},
        ],
      },
      states: {aud:"success",c_dem:"success",err:"success",ig0:"success",m:"success",pub:"success",r:"success",snap:"success",t:"success",v:"success"},
      runCounts: {aud:{in:420,out:420,rej:0},c_dem:{in:420,out:420,rej:0},err:{in:2,out:2,rej:0},ig0:{in:422,out:422,rej:0},m:{in:420,out:420,rej:0},pub:{in:420,out:420,rej:0},r:{in:422,out:422,rej:0},snap:{in:420,out:420,rej:0},t:{in:420,out:420,rej:0},v:{in:422,out:420,rej:2}},
      runOrder: ["r","ig0","v","t","err","m","c_dem","aud","snap","pub"],
    },
  ],
  lookups: {
    sources: [
      {id:"crm",name:"CRM",vendor:"Salesforce Sales Cloud",short:"CRM",status:"live",mode:"API extractor · API + events",auth:"OAuth 2.0 JWT bearer",read:["GET /services/data/v59.0/query?q=Opportunity","GET /services/data/v59.0/sobjects/Account","GET /services/data/v59.0/sobjects/Contract"],write:["POST /services/data/v59.0/sobjects/Task"],cat:"internal",fresh:"4 min",owner:"Sales Operations",type:"crm"},
      {id:"proc",name:"Procurement",vendor:"SAP Ariba",short:"Procurement",status:"live",mode:"API extractor · Polling · 30 min",auth:"OAuth 2.0 client credentials",read:["GET /procurement-reporting-details/v2/prod/views/PurchaseOrders","GET /sourcing-event/v2/prod/events","GET /supplier-data/v4/prod/suppliers"],write:[],cat:"internal",fresh:"12 min",owner:"Procurement",type:"proc"},
    ],
    XF: [
      {desc:"",group:"ingest",id:"x_gw",ingest:"api",label:"API gateway",sub:"REST / SOAP, auth, throttling"},
      {desc:"",group:"ingest",id:"x_evt",ingest:"event",label:"Event ingestion",sub:"Event hub, ordering, replay"},
      {desc:"",group:"ingest",id:"x_val",label:"Validation & enrichment",sub:"Schema, completeness, reference data"},
      {desc:"",id:"x_fx",label:"Convert currency",sub:"Dated rate, USD base"},
      {desc:"",id:"x_utc",label:"Timestamps to UTC",sub:"Local time → UTC"},
      {desc:"",group:"branch",ic:"alert",id:"x_err",label:"Error handler",sink:true,sub:"Invalid records"},
      {desc:"",group:"branch",ic:"audit",id:"x_audit",label:"Write to audit log",sink:true,sub:"Run status and metrics"},
      {desc:"",group:"branch",ic:"stream",id:"x_pub",label:"Publish to event stream",sink:true,sub:"Model updated"},
    ],
    FR_XF: [
      {desc:"",group:"branch",ic:"alert",id:"x_err",label:"Error handler",sink:true,sub:"Invalid records"},
      {desc:"",group:"branch",ic:"audit",id:"x_audit",label:"Write to audit log",sink:true,sub:"Run status and metrics"},
      {desc:"",group:"branch",ic:"stream",id:"x_pub",label:"Publish to event stream",sink:true,sub:"Model updated"},
    ],
    FXD: {
      c_dem: {canon:true,desc:"",in:true,label:"Demand opportunity",model:"Demand opportunity",out:true,sub:"Model v1.8 · 10 fields"},
      snap: {desc:"",in:true,label:"Evidence snapshot",out:false,sub:"Frozen for each decision"},
    },
    SH: {crm:"CRM",proc:"Procurement"},
    MAP_TARGET: {crm:"Demand opportunity",proc:"Demand opportunity"},
    CH_ARR: {api:"API calls",event:"events",file:"files"},
  },
};

describe('seeded workflows WF-101 and WF-105 (golden data)', () => {
  const GL: Lookups = {
    ...L, ...GOLDEN.lookups, mappings: { crm: [['a', 'b']], proc: [['a', 'b']] },
  } as unknown as Lookups;
  for (const w of GOLDEN.workflows) {
    const g = w.graph as WfGraph;
    it(w.id + ' validates with no errors and no warnings, as the demo shows', () => {
      const c = validate(GL, g, w.kind);
      expect(c.filter((x) => x.sev === 'error')).toEqual([]);
      expect(c.filter((x) => x.sev === 'warn')).toEqual([]);
      expect(c).toEqual([]);
    });
    it(w.id + ' runs in the order of its last run', () => {
      expect(order(g)).toEqual(w.runOrder);
    });
    it(w.id + ' counts the records of its last run as the demo does', () => {
      expect(runCounts({ id: w.id, last: w.last } as unknown as Workflow, g, w.states as Record<string, RunState>)).toEqual(w.runCounts);
    });
  }
});

// ---------------------------------------------------------------- block settings (plan 6 C2: the server's rules)
const fs_ = (key: string, label: string, type: FieldSpec['type'], dflt: unknown, more: Partial<FieldSpec> = {}): FieldSpec => ({
  key, label, type, default: dflt, required: false, choices: null, help: '', min: null, max: null, source: null, ...more,
});
const BS: Record<string, BlockSpec> = {
  x_fx: { ref: 'x_fx', readonly: false, fields: [fs_('currency', 'Target currency', 'select', 'USD', { required: true, choices: ['USD', 'EUR', 'INR'] })] },
  x_val: { ref: 'x_val', readonly: false, fields: [fs_('required', 'Required fields', 'fields', []), fs_('rules', 'Rules', 'rules', [])] },
  x_gw: { ref: 'x_gw', readonly: false, fields: [fs_('timeout_s', 'Timeout (s)', 'number', 30, { min: 1, max: 600 })] },
  conn: { ref: 'conn', readonly: false, fields: [fs_('resources', 'Resources', 'multi', [], { source: 'resources' })] },
  fixed: { ref: 'fixed', readonly: true, fields: [] },
};
describe('block settings', () => {
  const n = (k: StepKind, ref: string, cfg?: Record<string, unknown>): WfNode => ({ id: 'n', k, ref, x: 0, y: 0, ...(cfg ? { cfg } : {}) });
  it('reads a node without settings as the defaults, and stores only what differs', () => {
    expect(specKey(n('xf', 'x_fx'))).toBe('x_fx');
    expect(specKey(n('conn', 'crm'))).toBe('conn');
    expect(nodeCfg(BS, n('xf', 'x_fx'))).toEqual({ currency: 'USD' });
    expect(compactCfg(BS, n('xf', 'x_fx', { currency: 'USD' }))).toEqual(n('xf', 'x_fx'));
    expect(compactCfg(BS, n('xf', 'x_fx', { currency: 'EUR' })).cfg).toEqual({ currency: 'EUR' });
  });
  it('names the block and the field, as the server does', () => {
    expect(cfgErrors(BS, n('xf', 'x_fx', { currency: 'XYZ' }), { label: 'Convert currency' })).toEqual(['Convert currency: Target currency XYZ is not one of USD, EUR, INR.']);
    expect(cfgErrors(BS, n('xf', 'x_val', { rules: [{ field: '', check: 'present' }] }), { label: 'V' })).toEqual(['V: Rules rule 1 has no field.']);
    expect(cfgErrors(BS, n('xf', 'x_val', { rules: [{ field: 'qty', check: 'range', arg: '>0' }] }), { label: 'V' })).toEqual([]);
    expect(cfgErrors(BS, n('xf', 'x_gw', { timeout_s: 0 }), { label: 'G' })).toEqual(['G: Timeout (s) must be at least 1.']);
    expect(cfgErrors(BS, n('xf', 'x_gw', { colour: 'red' }), { label: 'G' })).toEqual(['G: colour is not a setting of this block.']);
    expect(cfgErrors(BS, n('conn', 'crm', { resources: ['ghosts'] }), { label: 'CRM', resources: ['opps'] })).toEqual(['CRM: Resources ghosts is not a resource of this connection.']);
    expect(cfgErrors(BS, n('fixed', 'c_dem', { a: 1 }), { label: 'D' })).toEqual(['D: this step has no settings to change.']);
  });
  it('adds settings errors to the checks when the catalogue is known', () => {
    const g = G(GOOD, GOOD_E);
    g.nodes.find((x) => x.id === 'v')!.cfg = { rules: [{ field: '', check: 'present' }] };
    expect(checksOn(g, 'v')).toEqual([]); // no catalogue in L: not checked
    const c = validate({ ...L, blocks: BS }, g, 'pipe').filter((x) => x.id === 'v');
    expect(c).toEqual([{ sev: 'error', id: 'v', msg: 'Validation & enrichment: Rules rule 1 has no field.' }]);
  });
});
