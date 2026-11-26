// The agent's suggested next step (runNextStep) is a click handler: it must not read the Suspense cache, which throws a
// Promise when the action catalogue has not loaded yet (MVP-12.4: the "Promise" page error on the case stage pages,
// after which the success toast never showed).
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(async () => ({ ok: true, output: { case_id: 'RT-1002' }, key: null, action: 'case.reevaluate' })),
  toast: vi.fn(),
  openAsk: vi.fn(),
}));
vi.mock('../../api/actions', () => ({
  invoke: m.invoke,
  // the real one suspends (throws a Promise) until /api/actions has loaded
  actionCatalog: () => {
    throw new Promise(() => {});
  },
  actionTitle: async (id: string) => (id === 'case.reevaluate' ? 'Re-evaluate a case' : undefined),
}));
vi.mock('../../api/case', () => ({
  caseById: () => ({ id: 'RT-1002', stage: 'reeval' }),
  nextStep: () => ({ kind: 'act', action: 'case.reevaluate', input: { case_id: 'RT-1002' }, n: 6, label: 'Re-evaluate' }),
  approverRole: () => 'Approver',
  checkAcknowledgement: vi.fn(),
  evidencePack: vi.fn(),
}));
vi.mock('../../components/toast', () => ({ toast: m.toast }));
vi.mock('../../utils/askBus', () => ({ askSoon: vi.fn(), openAsk: m.openAsk }));

import { caseActions, runNextStep } from './caseActions';
import type { CaseUi } from './CaseContext';

beforeEach(() => {
  m.invoke.mockClear();
  m.toast.mockClear();
  m.openAsk.mockClear();
});

describe('runNextStep', () => {
  it('runs the step and toasts its title without suspending', async () => {
    await expect(runNextStep('RT-1002', {} as CaseUi)).resolves.toBeUndefined();
    expect(m.invoke).toHaveBeenCalledWith('case.reevaluate', { case_id: 'RT-1002' });
    expect(m.toast).toHaveBeenCalledWith('Re-evaluate a case · RT-1002.', 3600);
  });
});

describe('the assistant launchers of the case pages', () => {
  it('"Ask about RT-1048" opens Ask with a question that names the case', () => {
    caseActions.askAboutCase('RT-1048');
    expect(m.openAsk).toHaveBeenCalledWith('Tell me about RT-1048: where it stands, why this route, and what it is waiting for.');
  });
  it('"Ask about this stage" names the case, the stage number and its title', () => {
    caseActions.askAboutStage('RT-1048', 6, 'Re-evaluate');
    expect(m.openAsk).toHaveBeenCalledWith('Tell me about stage 6 (Re-evaluate) of RT-1048: what it needs and who owns it.');
  });
  it('"Notify the owner" drafts a note to the stage owner', () => {
    caseActions.notifyOwner('Approver');
    expect(m.openAsk).toHaveBeenCalledWith('Draft a note to Approver asking them to act on the step this case is waiting for.');
  });
});
