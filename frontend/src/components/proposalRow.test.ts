import { describe, expect, it } from 'vitest';
import { canAccept, inContext, orderProposals, runHref } from './ProposalRow';

const p = (id: number, case_id: string | null, action = 'decision.approve') => ({ id, case_id, action });

describe('ProposalRow logic', () => {
  it('lists the case in context first, then the rest in server order', () => {
    const list = [p(1, 'RT-1'), p(2, 'RT-1048'), p(3, null), p(4, 'RT-1048')];
    expect(orderProposals(list, { caseId: 'RT-1048' }).map((x) => x.id)).toEqual([2, 4, 1, 3]);
  });
  it('lists flow, overlay and compose actions first when a flow is in context', () => {
    const list = [p(1, 'RT-1'), p(2, null, 'flow.saveDraft'), p(3, null, 'compose.submit'), p(4, null, 'overlay.apply')];
    expect(orderProposals(list, { flow: true }).map((x) => x.id)).toEqual([2, 3, 4, 1]);
    expect(inContext(p(5, null, 'flow.x'), {})).toBe(false);
  });
  it('keeps the order with no context', () => {
    expect(orderProposals([p(2, 'A'), p(1, 'B')], {}).map((x) => x.id)).toEqual([2, 1]);
  });
  it("never offers Accept on the signed-in person's own agent proposal", () => {
    expect(canAccept({ own: true })).toBe(false);
    expect(canAccept({ own: false })).toBe(true);
    expect(canAccept({})).toBe(true);
  });
  it('links the run to the Agents page', () => {
    expect(runHref('run 7')).toBe('#/agents?run=run%207');
  });
});
