import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: {}, key: null, action: 'x' })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { draftChangeSet, readDescription } from './compose';

const last = () => m.invoke.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];

beforeEach(() => m.invoke.mockClear());

describe('the compose facade (plan 9, P9-2.7, X-02)', () => {
  it('x-02: readDescription invokes config.read with the text and the org', async () => {
    await readDescription('We lease cordless tools.', 'Customer A');
    expect(last()).toEqual(['config.read', { text: 'We lease cordless tools.', org_unit_id: 'Customer A' }]);
  });

  it('x-02: draftChangeSet invokes config.draft, with the answer only when there is one', async () => {
    await draftChangeSet('We lease cordless tools.', 'Customer A', 'skip');
    expect(last()).toEqual(['config.draft', { text: 'We lease cordless tools.', org_unit_id: 'Customer A', answer: 'skip' }]);
    await draftChangeSet('We lease cordless tools.', 'Customer A');
    expect(last()[1]).not.toHaveProperty('answer');
  });
});
