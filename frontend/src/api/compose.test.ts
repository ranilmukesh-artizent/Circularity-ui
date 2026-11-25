import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async (): Promise<unknown> => ({ ok: true, output: {}, key: null, action: 'x' })),
  read: vi.fn((): unknown => ({ compositions: [{ id: 1 }] })),
}));
vi.mock('./actions', () => ({ invoke: m.invoke, read: m.read }));

import {
  answerQuestion, approveComposition, compositions, draftChangeSet, editChangeSet, markStep, readDescription, sendBack, startComposition,
  submitComposition, useComposition,
} from './compose';

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

describe('the composition facade (plan 9, P9-8.17)', () => {
  it('p9-8.17: each call invokes its compose action with the ids and fields', async () => {
    await startComposition('Customer A', 'We lease tools.', 'tool_fleet');
    expect(last()).toEqual(['compose.start', { org_unit_id: 'Customer A', text: 'We lease tools.', pack_key: 'tool_fleet' }]);
    await startComposition('Customer A', 'We lease tools.');
    expect(last()[1]).not.toHaveProperty('pack_key');
    await answerQuestion(7, 'skip');
    expect(last()).toEqual(['compose.answer', { id: 7, answer: 'skip' }]);
    await editChangeSet(7, [{ id: 'op-1', op: 'add_approver' }]);
    expect(last()).toEqual(['compose.editChangeSet', { id: 7, ops: [{ id: 'op-1', op: 'add_approver' }] }]);
    await markStep(7, 'mapping');
    expect(last()).toEqual(['compose.markStep', { id: 7, step: 'mapping' }]);
    await submitComposition(7);
    expect(last()).toEqual(['compose.submit', { id: 7 }]);
    await sendBack(7, 'agents', 'The threshold is too low here.', 'stage:condition');
    expect(last()).toEqual(['compose.sendBack', { id: 7, step: 'agents', reason: 'The threshold is too low here.', node_id: 'stage:condition' }]);
    await sendBack(7, 'agents', 'The threshold is too low here.');
    expect(last()[1]).not.toHaveProperty('node_id');
    await approveComposition(7);
    expect(last()).toEqual(['compose.approve', { id: 7 }]);
  });
});

describe('the composition list (plan 9, P9-8.17)', () => {
  it('compositions reads compose.list, scoped to the org unit when given', () => {
    expect(compositions('Customer A')).toEqual([{ id: 1 }]);
    expect(m.read).toHaveBeenLastCalledWith('compose.list', { org_unit_id: 'Customer A' });
    compositions();
    expect(m.read).toHaveBeenLastCalledWith('compose.list', {});
  });

  it('useComposition reads compose.get by id', () => {
    useComposition(3);
    expect(m.read).toHaveBeenLastCalledWith('compose.get', { id: 3 });
  });
});
