import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { askForInfo, explainException } from './mywork';

beforeEach(() => m.invoke.mockReset());

describe('askForInfo (P9-1.7, case.needInfo)', () => {
  it('asks a role a question about a case through the action pipeline', async () => {
    m.invoke.mockResolvedValue({ ok: true, output: { id: 7, case_id: 'RT-1048' }, key: null, action: 'case.needInfo' });
    const r = await askForInfo('RT-1048', 'Which site holds the spare?', 'Planner');
    expect(m.invoke).toHaveBeenCalledWith('case.needInfo', {
      case_id: 'RT-1048',
      question: 'Which site holds the spare?',
      to_role: 'Planner',
    });
    expect(r).toEqual({ ok: true, output: { id: 7, case_id: 'RT-1048' }, key: null, action: 'case.needInfo' });
  });
});

describe('explainException (P9-2.10, exception.explain)', () => {
  it('reads the assistant draft of an exception item through the action pipeline', async () => {
    const draft = { cause: 'c', recommended_action: 'a', owner_role: 'Planner', by_model: false, sources: [] };
    m.invoke.mockResolvedValue({ ok: true, output: draft, key: null, action: 'exception.explain' });
    const r = await explainException(7);
    expect(m.invoke).toHaveBeenCalledWith('exception.explain', { exception_id: 7 });
    expect(r.ok && r.output).toEqual(draft);
  });
});
