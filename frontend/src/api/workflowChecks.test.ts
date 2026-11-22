// Workflow Studio usability (plan 6 follow-up, G2): the canvas' checks merged with the server's for the draft, and the
// saved version a published workflow can publish.
//
// Sources made in the Connection Fabric (plan 6 follow-up): a workflow on a catalogue source gets no false "deleted",
// "maps to undefined" or wrong-channel checks in the browser (the demo's SH, MAP_TARGET and DELIVER know only the
// demo's sources; the list's `live` overlay gives the rest, as the server's checks read them), and a write connector's
// Target operation is checked against its target's writes, as the server does.
import { describe, expect, it } from 'vitest';
import type { BlockSpec, Check, Source, WfGraph } from './workflows';
import { cfgChecks, fieldErrors, info, liveSources, mergeChecks, republishVer, validate, type Lookups } from './workflowGraph';

const g: WfGraph = {
  nodes: [
    { id: 'r', k: 'conn', ref: 'crm', x: 0, y: 0 },
    { id: 'late', k: 'xf', ref: 'x_late', x: 200, y: 0, cfg: { keys: ['opportunity_id'] } },
  ],
  edges: [{ id: 'e1', a: 'r', b: 'late', locked: false }],
};
const BAD = 'Order late events: Key fields opportunity_id is not a field the records carry.';

describe('mergeChecks', () => {
  it('adds the server-only field error to the browser checks, errors first', () => {
    const browser: Check[] = [{ sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' }];
    const server: Check[] = [{ sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' }, { sev: 'error', id: 'late', msg: BAD }];
    expect(mergeChecks(browser, server, g)).toEqual([
      { sev: 'error', id: 'late', msg: BAD },
      { sev: 'warn', id: 'r', msg: 'CRM does not reach a canonical model.' },
    ]);
  });
  it('keeps one check per step and text, and the server wins on a duplicate', () => {
    const browser: Check[] = [{ sev: 'warn', id: 'r', msg: 'Same text.' }];
    const server: Check[] = [{ sev: 'error', id: 'r', msg: 'Same text.' }];
    expect(mergeChecks(browser, server, g)).toEqual([{ sev: 'error', id: 'r', msg: 'Same text.' }]);
  });
  it('drops a server check for a step no longer in the graph (an answer for an earlier edit)', () => {
    const server: Check[] = [{ sev: 'error', id: 'gone', msg: 'Old step.' }, { sev: 'error', id: 'e1', msg: 'A link check.' }];
    expect(mergeChecks([], server, g)).toEqual([{ sev: 'error', id: 'e1', msg: 'A link check.' }]);
  });
  it('is the browser checks alone without a server answer', () => {
    const browser: Check[] = [{ sev: 'info', id: 'r', msg: 'A note.' }];
    expect(mergeChecks(browser, null, g)).toBe(browser);
    expect(mergeChecks(browser, [], g)).toBe(browser);
  });
});

describe('republishVer', () => {
  it('offers the saved version when it is newer than the published one', () => {
    expect(republishVer({ status: 'published', ver: '0.3' }, '0.2')).toBe('0.3');
  });
  it('offers nothing when the published version is the saved one, or the workflow is not published', () => {
    expect(republishVer({ status: 'published', ver: '0.3' }, '0.3')).toBeNull();
    expect(republishVer({ status: 'paused', ver: '0.3' }, '0.2')).toBeNull();
    expect(republishVer({ status: 'draft', ver: '0.3' }, null)).toBeNull();
  });
});

// ---------------------------------------------------------------- a catalogue source in the browser's checks
const src = (id: string, name: string, more: Partial<Source> = {}): Source => ({
  id, name, vendor: name + ' Inc.', status: 'live', mode: 'API extractor', auth: 'API key', read: ['GET /rows'], write: [], cat: 'internal',
  fresh: '4 min', owner: 'Ops', type: id, ...more,
});
const xf = (id: string, label: string, more: Record<string, unknown> = {}) => ({ id, label, sub: '', desc: '', ...more });
const fx = (label: string, model: string) => ({ label, sub: '', desc: '', in: true, out: true, canon: true, model });
const base = (sources: Source[]): Lookups => ({
  sources,
  mappings: { crm: [['a', 'b']], postgres: [['id', 'asset.serial']], wh: [['x', 'y']] },
  XF: [xf('x_gw', 'API gateway', { group: 'ingest', ingest: 'api' }), xf('x_val', 'Validation & enrichment', { group: 'ingest' }), xf('x_env', 'Instruction envelope')],
  FR_XF: [],
  FXD: { c_asset: fx('Asset & component', 'Asset & component'), c_out: fx('Outcome', 'Outcome'), appr: { label: 'Human approval', sub: '', desc: '', in: true, out: true } },
  ACT_TYPES: [{ id: 'a_api', ch: 'api', label: 'Outbound API call', sub: '', desc: '' }],
  TOOLS: [],
  MAP_TARGET: { crm: 'Demand opportunity' },
  SH: { crm: 'CRM' },
  DELIVER: { crm: ['api'] },
  CH_ARR: { api: 'API calls', event: 'events', file: 'files' },
  CH_DEL: { api: 'REST API calls', file: 'files' },
});
// the integration screen's sources with the list's overlay: the catalogue source's target and delivery
const L = base(liveSources(
  [src('crm', 'Salesforce'), src('postgres', 'Database'), src('wh', 'Warehouse feed', { write: ['POST /moves'] })],
  {
    crm: { status: 'live', fresh: '4 min' },
    postgres: { status: 'live', fresh: '4 min', target: 'Asset & component', deliver: [] },
    wh: { status: 'live', fresh: '4 min', target: 'Outcome', deliver: ['api'] },
  },
));
const E = (a: string, b: string, i: number) => ({ id: 'e' + i, a, b, locked: false });
const ingest: WfGraph = {
  nodes: [
    { id: 'r', k: 'conn', ref: 'postgres', x: 0, y: 0 }, { id: 'ig', k: 'xf', ref: 'x_gw', x: 0, y: 0 }, { id: 'v', k: 'xf', ref: 'x_val', x: 0, y: 0 },
    { id: 'm', k: 'map', ref: 'postgres', x: 0, y: 0 }, { id: 'c', k: 'fixed', ref: 'c_asset', x: 0, y: 0 },
  ],
  edges: [E('r', 'ig', 0), E('ig', 'v', 1), E('v', 'm', 2), E('m', 'c', 3)],
};

describe('a workflow on a catalogue source', () => {
  it('names its mapping by the source and finds no problem with a clean ingest', () => {
    expect(info(L, ingest.nodes[3]).label).toBe('Database fields');
    expect(info(L, ingest.nodes[3]).sub).toBe('→ Asset & component · 1 mapped');
    expect(validate(L, ingest, 'pipe')).toEqual([]);
  });
  it('says the mapping is wired to the wrong model with the target the server reads', () => {
    const g = { ...ingest, nodes: ingest.nodes.map((n) => (n.id === 'c' ? { ...n, ref: 'c_out' } : n)) };
    expect(validate(L, g, 'pipe').map((c) => c.msg)).toContain('Database fields maps to Asset & component, but it is wired to Outcome.');
  });
  it('lets a writable catalogue source take API calls, and names it in a delivery error', () => {
    const out: WfGraph = {
      nodes: [
        { id: 'appr', k: 'fixed', ref: 'appr', x: 0, y: 0 }, { id: 'env', k: 'xf', ref: 'x_env', x: 0, y: 0 },
        { id: 'a', k: 'act', ref: 'a_api', x: 0, y: 0 }, { id: 'w', k: 'wconn', ref: 'wh', x: 0, y: 0 },
      ],
      edges: [E('appr', 'env', 0), E('env', 'a', 1), E('a', 'w', 2)],
    };
    expect(validate(L, out, 'pipe').filter((c) => c.id === 'a')).toEqual([]);
    const ro = { ...out, nodes: out.nodes.map((n) => (n.id === 'w' ? { ...n, ref: 'postgres' } : n)) };
    expect(validate(L, ro, 'pipe').filter((c) => c.id === 'a').map((c) => c.msg)).toEqual(['Database does not accept REST API calls. It accepts .']);
  });
});

// ---------------------------------------------------------------- G3b: Target operation
const OP: BlockSpec = {
  ref: 'wconn', readonly: false,
  fields: [{ key: 'operation', label: 'Target operation', type: 'text', default: '', required: false, choices: null, help: '', min: null, max: null, source: 'operations' }],
};
describe('a write connector\'s Target operation', () => {
  it('is checked against the target\'s writes, as the server does', () => {
    const f = OP.fields[0];
    expect(fieldErrors(f, 'teardown', { operations: ['repair', 'teardown'] })).toEqual([]);
    expect(fieldErrors(f, '', { operations: ['repair', 'teardown'] })).toEqual([]);
    expect(fieldErrors(f, 'scrap', { operations: ['repair', 'teardown'] })).toEqual(['Target operation scrap is not a write of this system (repair, teardown).']);
    expect(fieldErrors(f, 'scrap', { operations: [] })).toEqual(['Target operation scrap is not a write of this system (it takes none).']);
    expect(fieldErrors(f, 'scrap', {})).toEqual([]); // the targets' writes not known: the server's check covers it
  });
  it('reads the catalogue\'s operations in the canvas checks', () => {
    const g: WfGraph = { nodes: [{ id: 'w', k: 'wconn', ref: 'wh', x: 0, y: 0, cfg: { operation: 'scrap' } }], edges: [] };
    const LB = { ...L, blocks: { wconn: OP }, operations: { repair: ['repair', 'teardown'] } };
    expect(cfgChecks(LB, g).map((c) => c.msg)).toEqual(['Warehouse feed: Target operation scrap is not a write of this system (it takes none).']);
  });
});