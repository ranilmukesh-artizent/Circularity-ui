import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  apiInvoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { id: 1 }, key: null, action: 'x' })),
}));
vi.mock('./client', () => ({ apiInvoke: m.apiInvoke, cachedAction: vi.fn(), cached: vi.fn(), http: vi.fn(), peek: vi.fn() }));

import { importDemand, importHistory, replayBatches, replayReport, replayRuns, runReplay } from './replay';

const last = () => (m.apiInvoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>]).slice(0, 2);

beforeEach(() => m.apiInvoke.mockClear());

describe('the replay facade (plan 9, P9-7.1, X-06)', () => {
  it('x-06: importHistory sends {pack, org_unit_id, csv}', async () => {
    await importHistory('tool_fleet', 'Customer A', 'item_id\nA\n');
    expect(last()).toEqual(['replay.import', { pack: 'tool_fleet', org_unit_id: 'Customer A', csv: 'item_id\nA\n' }]);
  });
  it('x-06: importHistory appends with batch_id when given', async () => {
    await importHistory('device', 'Customer A', 'x', 4);
    expect(last()[1]).toMatchObject({ batch_id: 4 });
  });
  it('x-06: importDemand sends {batch_id, csv}', async () => {
    await importDemand(4, 'demand_id\nD1\n');
    expect(last()).toEqual(['replay.importDemand', { batch_id: 4, csv: 'demand_id\nD1\n' }]);
  });
  it('x-06: replayBatches asks for the pack and org unit', async () => {
    await replayBatches('device', 'Customer B');
    expect(last()).toEqual(['replay.batches', { pack: 'device', org_unit_id: 'Customer B' }]);
  });
  it('x-06: runReplay sends {batch_id, flow_id} and flow_ver only when given', async () => {
    await runReplay(3, 7);
    expect(last()).toEqual(['replay.run', { batch_id: 3, flow_id: 7 }]);
    await runReplay(3, 7, 'draft');
    expect(last()).toEqual(['replay.run', { batch_id: 3, flow_id: 7, flow_ver: 'draft' }]);
  });
  it('x-06: replayReport and replayRuns ask by run and by flow', async () => {
    await replayReport(9);
    expect(last()).toEqual(['replay.report', { run_id: 9 }]);
    await replayRuns(7);
    expect(last()).toEqual(['replay.runs', { flow_id: 7 }]);
  });
});
