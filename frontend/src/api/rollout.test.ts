import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  apiInvoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { flow_id: 12 }, key: null, action: 'x' })),
}));
vi.mock('./client', () => ({ apiInvoke: m.apiInvoke, cachedAction: vi.fn(), cached: vi.fn(), http: vi.fn(), peek: vi.fn() }));

import { canaryLine, getRollout, goFull, pauseRollout, rollbackRollout, startCanary, widenRollout } from './rollout';

const last = () => (m.apiInvoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>]).slice(0, 2);

beforeEach(() => m.apiInvoke.mockClear());

describe('the rollout facade (plan 9, P9-7.3, X-06)', () => {
  it('x-06: startCanary(12, FR, 20) invokes rollout.startCanary {flow_id: 12, region: FR, share: 20}', async () => {
    await startCanary(12, 'FR', 20);
    expect(last()).toEqual(['rollout.startCanary', { flow_id: 12, region: 'FR', share: 20 }]);
  });
  it('x-06: startCanary sends region_key only when given', async () => {
    await startCanary(12, 'Customer A', 5, 'owner');
    expect(last()[1]).toMatchObject({ region_key: 'owner' });
  });
  it('x-06: widenRollout sends the share, the region or both', async () => {
    await widenRollout(12, 40);
    expect(last()).toEqual(['rollout.widen', { flow_id: 12, share: 40 }]);
    await widenRollout(12, undefined, 'DE');
    expect(last()).toEqual(['rollout.widen', { flow_id: 12, region: 'DE' }]);
  });
  it('x-06: goFull, pauseRollout, rollbackRollout and getRollout name their actions', async () => {
    await goFull(12);
    expect(last()).toEqual(['rollout.full', { flow_id: 12 }]);
    await pauseRollout(12, 'Looks worse for a week.');
    expect(last()).toEqual(['rollout.pause', { flow_id: 12, reason: 'Looks worse for a week.' }]);
    await rollbackRollout(12, 'Looks worse for a week.');
    expect(last()).toEqual(['rollout.rollback', { flow_id: 12, reason: 'Looks worse for a week.' }]);
    await getRollout(12);
    expect(last()).toEqual(['rollout.get', { flow_id: 12 }]);
  });
  it('x-06: canaryLine names each region and its share', () => {
    expect(canaryLine([{ region: 'FR', share: 20 }])).toBe('Canary: FR at 20 % of volume');
    expect(canaryLine([{ region: 'FR', share: 40 }, { region: 'DE', share: 10 }])).toBe('Canary: FR at 40 % of volume, DE at 10 % of volume');
    expect(canaryLine([])).toBe('');
  });
});
