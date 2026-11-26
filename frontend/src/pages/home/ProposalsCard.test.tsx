// @vitest-environment jsdom
// Home's "Proposals for you" (Gaps-B): not drawn when nothing is pending (Home as before); otherwise each proposal with
// Accept (proposal.accept) and Reject, which asks for a reason (proposal.reject).
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HomeProposal } from '../../api/home';

const m = vi.hoisted(() => ({
  list: [] as HomeProposal[],
  accept: vi.fn(async (_id: number) => ({ ok: true as const, output: { id: 1, status: 'accepted', action: 'x' }, key: null, action: 'proposal.accept' })),
  reject: vi.fn(async (_id: number, _r: string) => ({ ok: true as const, output: { id: 1, status: 'rejected' }, key: null, action: 'proposal.reject' })),
}));
vi.mock('../../api/home', () => ({
  proposals: () => m.list,
  acceptProposal: m.accept,
  rejectProposal: m.reject,
  rgTime: (d: string) => d,
}));
vi.mock('../../components/toast', () => ({ toast: vi.fn() }));

import { ProposalsCard } from './ProposalsCard';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  m.accept.mockClear();
  m.reject.mockClear();
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const P: HomeProposal = {
  id: 7, agent: 'ext', agentName: 'Inbox proposer', action: 'evidence.request', title: 'Request evidence',
  why: 'The inspection report is missing.', input: { case_id: 'RT-1051' }, case_id: 'RT-1051', run_id: null, at: '2026-10-07T09:30:00+00:00',
};
const draw = () => act(() => root.render(<ProposalsCard />));
const button = (label: string) => [...document.querySelectorAll('button')].find((b) => b.textContent === label)!;

describe('ProposalsCard', () => {
  it('draws nothing when no proposal is pending', () => {
    m.list = [];
    draw();
    expect(host.innerHTML).toBe('');
  });

  it('shows what, for which case, why and when, and accepts through proposal.accept', async () => {
    m.list = [P];
    draw();
    const t = host.textContent!;
    for (const s of ['Proposals for you', 'Request evidence', 'RT-1051', 'The inspection report is missing.', 'Inbox proposer']) expect(t).toContain(s);
    act(() => button('Accept, runs as you').click());
    await act(async () => button('Run as me').click());
    expect(m.accept).toHaveBeenCalledWith(7);
  });

  it('shows a held requisition reduction with Accept and Reject (P9-10.16, TN-19)', () => {
    m.list = [{ ...P, id: 9, action: 'requisition.reduce', title: 'Reduce purchase requisition', case_id: 'RT-1048', input: { case_id: 'RT-1048', req_id: 'PR-3302', qty: 1 } }];
    draw();
    expect(host.textContent).toContain('Reduce purchase requisition');
    expect(button('Accept, runs as you')).toBeTruthy();
    expect(button('Reject…')).toBeTruthy();
  });

  it('shows why the hold policy held it (plan 9 P9-2.4), and nothing for a proposal held before', () => {
    m.list = [{ ...P, reasons: [{ reason: 'value', detail: 'Value $900 is above the $600 limit' }, { reason: 'confidence', detail: 'Confidence 0.62 is below 0.75' }] }];
    draw();
    expect(host.querySelector('[data-reasons]')!.textContent).toBe('Held because: Value $900 is above the $600 limit · Confidence 0.62 is below 0.75');
    m.list = [{ ...P, reasons: [] }];
    draw();
    expect(host.querySelector('[data-reasons]')).toBeNull();
  });

  it("the person's own agent's proposal: no Accept (the server refuses it), a note, Reject stays", () => {
    m.list = [{ ...P, own: true }];
    draw();
    expect(button('Accept, runs as you')).toBeUndefined();
    expect(host.textContent).toContain("Your agent's proposal: another person accepts it.");
    expect(button('Reject…')).toBeDefined();
  });

  it('reject asks for a reason first', async () => {
    m.list = [P];
    draw();
    act(() => button('Reject…').click());
    expect(m.reject).not.toHaveBeenCalled();
    const ta = document.querySelector('textarea')!;
    const confirm = [...document.querySelectorAll('button')].filter((b) => b.textContent === 'Reject proposal').at(-1)!;
    expect(confirm.disabled).toBe(true); // no reason yet
    act(() => {
      const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!;
      set.call(ta, 'Inspection already booked.');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => confirm.click());
    expect(m.reject).toHaveBeenCalledWith(7, 'Inspection already booked.');
  });
});
