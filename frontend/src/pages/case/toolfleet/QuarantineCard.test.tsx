// @vitest-environment jsdom
// Plan 9, P9-3.7 (TF-04): the quarantine card of a recalled tool, and who sees the release button.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuarantineView } from '../../../api/toolFleet';
import { QuarantineCard, canRelease, quarantineLine } from './QuarantineCard';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const m = vi.hoisted(() => ({ release: vi.fn(async () => ({ ok: true, output: { released: true }, key: null, action: 'recall.release' })) }));
vi.mock('../../../api/toolFleet', () => ({ releaseQuarantine: m.release }));

const q = (over: Partial<QuarantineView>): QuarantineView => ({
  recall_id: 'RC-2026-017', remedy: 'repair', blocked: ['release', 'redeploy', 'resell'], affected_parts: ['Impact mechanism'], released: null, ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); m.release.mockClear(); });
afterEach(() => act(() => root.unmount()));
const render = (v: QuarantineView | null, may: boolean) => {
  act(() => root.render(<QuarantineCard caseId="RT-1" q={v} mayRelease={may} />));
  return host;
};
const button = () => host.querySelector('[data-testid="tf-quarantine-release"]') as HTMLButtonElement | null;

describe('quarantine line', () => {
  it('names the recall, the remedy and what is blocked', () => {
    expect(quarantineLine(q({}))).toBe('Safety recall RC-2026-017 (repair): quarantined, blocked: release, redeploy, resell');
    expect(quarantineLine(q({ released: { by: 'approver', at: 'x', note: 'Fixed at the depot' }, blocked: [] }))).toBe('Safety recall RC-2026-017 (repair): released');
  });
});

describe('release button visibility', () => {
  it('shows for an Approver or Admin on a repair recall', () => {
    expect(render(q({}), true).textContent).toContain('Release after the fix');
    expect(button()).not.toBeNull();
  });
  it('does not show for a person who may not release', () => {
    render(q({}), false);
    expect(button()).toBeNull();
  });
  it('does not show for a replace or refund recall, which says it is never released', () => {
    for (const remedy of ['replace', 'refund']) {
      expect(canRelease(q({ remedy }), true)).toBe(false);
      const t = render(q({ remedy, blocked: ['release', 'refurb', 'redeploy', 'resell'] }), true).textContent;
      expect(button()).toBeNull();
      expect(t).toContain('never released to the fleet');
    }
  });
  it('does not show once released, and says who released it', () => {
    const t = render(q({ blocked: [], released: { by: 'approver', at: 'x', note: 'Fixed at the depot' } }), true).textContent;
    expect(button()).toBeNull();
    expect(t).toContain('Released by approver: Fixed at the depot');
  });
  it('renders nothing for a tool with no recall', () => {
    expect(render(null, true).innerHTML).toBe('');
  });
});

describe('release', () => {
  it('needs a note of 10 characters, then calls releaseQuarantine with it', async () => {
    render(q({}), true);
    expect(button()?.disabled).toBe(true);
    const ta = host.querySelector('textarea') as HTMLTextAreaElement;
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    await act(async () => { set?.call(ta, 'Mechanism replaced at the depot'); ta.dispatchEvent(new Event('input', { bubbles: true })); });
    expect(button()?.disabled).toBe(false);
    await act(async () => { button()?.click(); });
    expect(m.release).toHaveBeenCalledWith('RT-1', 'Mechanism replaced at the depot');
  });
});
