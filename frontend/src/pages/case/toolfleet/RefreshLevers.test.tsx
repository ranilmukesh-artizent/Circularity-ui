// @vitest-environment jsdom
// Plan 9, P9-5.6 (CR-06): the proposal's levers: moving the threshold or the upgrade switch asks the server and shows what changes.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RefreshWhatIf } from '../../../api/refresh';
import { RefreshLevers, splitLine } from './RefreshLevers';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const m = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../../../api/refresh', () => ({ refreshWhatIf: m.call }));

const result = (over: Partial<RefreshWhatIf> = {}): RefreshWhatIf => ({
  case_id: 'RT-1', before: { keep: 5, swap: 1, upgrade: 1 }, split: { keep: 3, swap: 3, upgrade: 1 },
  changed: [{ serial: 'CMH-A4', from: 'keep', to: 'swap' }, { serial: 'CMH-A5', from: 'keep', to: 'swap' }],
  fee_delta: -12.5, renewal_delta: -0.0123, credit_total: 155, flips_route: true, best_before: 'proposal', best_after: 'renew_as_is',
  currency: 'USD', note: 'Before: 5 keep, 1 swap, 1 upgrade. With swap below 40% of life: 3 keep, 3 swap, 1 upgrade.', ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { m.call.mockReset(); host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const q = (id: string) => host.querySelector(`[data-testid="${id}"]`);

const move = async (value: string) => {
  const input = q('rf-lever-threshold') as HTMLInputElement;
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
  await act(async () => { set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
};

describe('RefreshLevers', () => {
  it('asks nothing until a lever moves', () => {
    act(() => root.render(<RefreshLevers caseId="RT-1" />));
    expect(m.call).not.toHaveBeenCalled();
    expect(q('rf-lever-result')).toBeNull();
  });
  it('moving the threshold to 40 shows the tools that change and the impact', async () => {
    m.call.mockResolvedValue({ ok: true, output: result() });
    act(() => root.render(<RefreshLevers caseId="RT-1" />));
    await move('40');
    expect(m.call).toHaveBeenCalledWith('RT-1', { swapThreshold: 40, upgrades: true });
    expect(q('rf-lever-split')?.textContent).toBe('keep 5, swap 1, upgrade 1 → keep 3, swap 3, upgrade 1');
    expect(q('rf-lever-changed')?.textContent).toBe('CMH-A4: keep → swapCMH-A5: keep → swap');
    expect(q('rf-lever-impact')?.textContent).toContain('-$12.50');
    expect(q('rf-lever-impact')?.textContent).toContain('-1.2 points');
    expect(q('rf-lever-impact')?.textContent).toContain('another route ranks first');
    expect(q('rf-lever-note')?.textContent).toContain('Before: 5 keep');
  });
  it('the upgrades switch sends upgrades false', async () => {
    m.call.mockResolvedValue({ ok: true, output: result({ changed: [], flips_route: false }) });
    act(() => root.render(<RefreshLevers caseId="RT-1" />));
    await act(async () => { (q('rf-lever-upgrades') as HTMLInputElement).click(); });
    expect(m.call).toHaveBeenCalledWith('RT-1', { swapThreshold: 25, upgrades: false });
    expect(q('rf-lever-none')?.textContent).toBe('No tool changes action.');
  });
  it('shows a refusal in words', async () => {
    m.call.mockResolvedValue({ ok: false, error: { code: 'validation_error', message: 'The swap threshold is a whole number from 10 to 50.' } });
    act(() => root.render(<RefreshLevers caseId="RT-1" />));
    await move('40');
    expect(q('rf-lever-error')?.textContent).toContain('whole number from 10 to 50');
  });
  it('words the split', () => {
    expect(splitLine(result())).toBe('keep 5, swap 1, upgrade 1 → keep 3, swap 3, upgrade 1');
  });
});
