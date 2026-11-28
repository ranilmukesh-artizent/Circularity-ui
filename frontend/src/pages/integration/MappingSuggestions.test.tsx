// @vitest-environment jsdom
// Suggested field mappings (plan 9, P9-8.2): the button asks the server, the table shows the masked samples, the calibrated
// confidence as a percentage, the band as a pill and the reason; a row below the bar shows "No proposal" with its candidates.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MappingSuggestion } from '../../api/integration';

const m = vi.hoisted(() => ({
  suggest: vi.fn(async (): Promise<unknown> => ({ ok: true, output: {} })), toast: vi.fn(),
  decide: vi.fn(async (..._a: unknown[]): Promise<unknown> => ({ ok: true, output: {} })),
  ask: vi.fn(async (..._a: unknown[]): Promise<unknown> => ({ ok: true, output: {} })),
  answer: vi.fn(async (..._a: unknown[]): Promise<unknown> => ({ ok: true, output: {} })),
  apply: vi.fn(async (..._a: unknown[]): Promise<unknown> => ({ ok: true, output: {} })),
}));
vi.mock('../../api/integration', () => ({
  suggestFieldMappings: m.suggest, decideMapping: m.decide, askOwner: m.ask, answerOwner: m.answer, applyMappings: m.apply,
}));
vi.mock('../../components/toast', () => ({ toast: m.toast }));

import { MappingSuggestions } from './MappingSuggestions';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
const row = (o: Partial<MappingSuggestion>): MappingSuggestion => ({
  field: 'SERNR', target: 'asset.serial_number', confidence: 0.91, reason: 'name match 1.00 with serial_number', rule: 'copy',
  proposed_by: 'rule', candidates: [['asset.serial_number', 0.85]], band: 'pre_ticked', resource: 'orders', samples: ['MTR-2041'], decision: null, ...o,
}); // prettier-ignore

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  m.suggest.mockClear();
  act(() => root.render(<MappingSuggestions sourceId="repair" />));
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const click = async () => { await act(async () => { host.querySelector('button')!.click(); }); };

describe('MappingSuggestions', () => {
  it('p9-8.2: asks for the source, shows the confidence as a percentage, the band and the reason', async () => {
    m.suggest.mockResolvedValueOnce({
      ok: true,
      output: {
        source_id: 'repair', by_model: false, gaps: ['asset.asset_id'], waiting: 0, fields: ['asset.serial_number'],
        rows: [
          row({}),
          row({ field: 'flg_rcl', target: null, confidence: 0.12, band: 'none', reason: 'coded 0/1; meaning taken from the registry documentation', samples: ['0', '1'], candidates: [['asset.lease_rate', 0.37]] }),
          row({ field: 'contact', band: 'check', confidence: 0.55, samples: ['«masked»'], reason: 'values look like ISO dates' }),
        ],
      },
    });
    await click();
    expect(m.suggest).toHaveBeenCalledWith('repair');
    const cells = [...host.querySelectorAll('tbody tr')].map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent));
    expect(cells[0].slice(0, 6)).toEqual(['SERNR', 'MTR-2041', 'asset.serial_number', '91%', 'Pre-ticked', 'name match 1.00 with serial_number']);
    expect(cells[1][2]).toContain('No proposal');
    expect(cells[1][2]).toContain('asset.lease_rate (0.37)');
    expect(cells[1][4]).toBe('No proposal');
    expect(cells[1][5]).toContain('coded 0/1');
    expect(cells[2][1]).toBe('«masked»');
    expect(cells[2][4]).toBe('Check');
    expect(host.textContent).toContain('asset.asset_id');
  });

  it('p9-8.2: a source with no sample says so; a refusal shows its message', async () => {
    m.suggest.mockResolvedValueOnce({ ok: true, output: { source_id: 'repair', rows: [], gaps: [], waiting: 0, fields: [], by_model: false } });
    await click();
    expect(host.textContent).toContain('No sample yet');
    m.suggest.mockResolvedValueOnce({ ok: false, error: { code: 'not_found', message: 'No source repair.' } });
    await click();
    expect(m.toast).toHaveBeenCalled();
  });
});

describe('MappingSuggestions waiting', () => {
  it('shows the honest wait, lets the person stop waiting, and drops a late answer', async () => {
    vi.useFakeTimers();
    try {
      let release: (v: unknown) => void = () => {};
      m.suggest.mockImplementationOnce(() => new Promise((res) => { release = res; }));
      await click();
      expect(host.textContent).toContain('This takes up to about 30 seconds.');
      await act(async () => { vi.advanceTimersByTime(3000); });
      expect(host.textContent).toContain('3 s');
      await act(async () => { vi.advanceTimersByTime(60000); });
      expect(host.textContent).toContain('Still working…');
      await act(async () => { btn('Stop waiting').click(); });
      expect(host.textContent).toContain('Stopped waiting');
      await act(async () => { release({ ok: true, output: { source_id: 'repair', by_model: false, gaps: [], waiting: 0, fields: FIELDS, rows: [row({})] } }); });
      expect(host.querySelector('table')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('limits the run to one table and says what the model did', async () => {
    m.suggest.mockResolvedValueOnce({
      ok: true,
      output: { source_id: 'repair', by_model: true, gaps: [], waiting: 0, fields: FIELDS, rows: [row({})], model: { asked: 1, answered: 1, fields: 41, seconds: 9, stopped: null } },
    });
    act(() => root.render(<MappingSuggestions key="auto" sourceId="repair" resource="orders" autoRun />));
    await act(async () => {});
    expect(m.suggest).toHaveBeenCalledWith('repair', 'orders');
    expect(host.querySelector('[data-testid="model-line"]')!.textContent).toBe('A model read 1 of 41 fields; the rest were matched by name and values.');
  });
});

// ---------------------------------------------------------------- P9-8.4: the five choices
const FIELDS = ['asset.serial_number', 'asset.location', 'asset.stock_qty'];
const out = (rows: MappingSuggestion[], waiting = 0) => ({ ok: true, output: { source_id: 'repair', by_model: false, gaps: [], waiting, fields: FIELDS, rows } });
const btn = (label: string) => [...host.querySelectorAll('button')].find((b) => b.textContent === label) as HTMLButtonElement;
const setValue = (el: Element, v: string) => {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(el, v);
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
};
const press = async (label: string) => { await act(async () => { btn(label).click(); }); };
const pick = async (aria: string, v: string) => { await act(async () => { setValue(host.querySelector(`[aria-label="${aria}"]`)!, v); }); };
const load = async (rows: MappingSuggestion[], waiting = 0) => { m.suggest.mockResolvedValueOnce(out(rows, waiting)); await click(); };

describe('MappingSuggestions choices', () => {
  beforeEach(() => { m.decide.mockReset(); m.ask.mockReset(); m.apply.mockReset(); m.answer.mockReset(); });

  it('p9-8.4: every row offers the five choices, and nothing is chosen for the person', async () => {
    await load([row({})]);
    for (const l of ['Accept', 'Choose another field', 'Accept with a conversion', 'Not needed', 'Ask the owner']) expect(btn(l)).toBeTruthy();
    expect(btn('Save mapping').disabled).toBe(true);
  });

  it('p9-8.4: Accept records the proposal, shows it, and lets Save mapping send the accepted row', async () => {
    m.decide.mockResolvedValueOnce({ ok: true, output: { id: 7, source_id: 'repair', src: 'SERNR', decision: 'accepted', target: 'asset.serial_number', rule: null } });
    m.apply.mockResolvedValueOnce({ ok: true, output: { source_id: 'repair', version: 3, ver: '1.2', rows: 1 } });
    await load([row({})]);
    await press('Accept');
    expect(m.decide).toHaveBeenCalledWith('repair', 'SERNR', expect.objectContaining({ decision: 'accepted', target: 'asset.serial_number', proposed: 'asset.serial_number', resource: 'orders' }));
    expect(host.textContent).toContain('Accepted asset.serial_number');
    expect(btn('Save mapping').disabled).toBe(false);
    await press('Save mapping');
    expect(m.apply).toHaveBeenCalledWith('repair', [{ src: 'SERNR', target: 'asset.serial_number', resource: 'orders' }]);
    expect(host.textContent).toContain('Saved as mapping version 3');
  });

  it('p9-8.4: Choose another field offers the canonical fields and records the replacement', async () => {
    m.decide.mockResolvedValueOnce({ ok: true, output: { id: 8, source_id: 'repair', src: 'SERNR', decision: 'replaced', target: 'asset.location', rule: null } });
    await load([row({})]);
    await press('Choose another field');
    const opts = [...host.querySelectorAll('select[aria-label="Choose another field"] option')].map((o) => o.getAttribute('value'));
    expect(opts).toEqual(['', ...FIELDS]);
    await pick('Choose another field', 'asset.location');
    await press('Use this field');
    expect(m.decide).toHaveBeenCalledWith('repair', 'SERNR', expect.objectContaining({ decision: 'replaced', target: 'asset.location', proposed: 'asset.serial_number' }));
    expect(host.textContent).toContain('Replaced with asset.location');
  });

  it('p9-8.4: Accept with a conversion shows the converted samples at once', async () => {
    m.decide.mockResolvedValueOnce({ ok: true, output: { id: 9, source_id: 'repair', src: 'WT', decision: 'accepted_with_rule', target: 'asset.stock_qty', rule: 'units:lb>kg', samples: ['10', '22'], values: [4.54, 9.98] } });
    await load([row({ field: 'WT', target: 'asset.stock_qty' })]);
    await press('Accept with a conversion');
    await pick('Conversion', 'units:lb>kg');
    await press('Convert and show values');
    expect(m.decide).toHaveBeenCalledWith('repair', 'WT', expect.objectContaining({ decision: 'accepted_with_rule', target: 'asset.stock_qty', rule: 'units:lb>kg' }));
    expect(host.textContent).toContain('Converted samples: 4.54, 9.98');
  });

  it('p9-8.4: Not needed on a required field shows the blocking warning', async () => {
    m.decide.mockResolvedValueOnce({ ok: true, output: { id: 10, source_id: 'repair', src: 'ID', decision: 'not_needed', target: 'asset.asset_id', rule: null, blocking: true, warning: 'Required field asset.asset_id is marked not needed.' } });
    await load([row({ field: 'ID', target: 'asset.asset_id' })]);
    await press('Not needed');
    expect(host.textContent).toContain('Required field asset.asset_id is marked not needed.');
  });

  it('p9-8.4: Ask the owner sends a short question and holds Save mapping while it is open', async () => {
    m.ask.mockResolvedValueOnce({ ok: true, output: { id: 11, owner: 'approver', item_id: 4, samples: ['MTR-2041'] } });
    await load([row({}), row({ field: 'WT', target: 'asset.stock_qty' })]);
    await press('Ask the owner');
    expect(btn('Send question').disabled).toBe(true); // a question needs words
    await act(async () => { setValue(host.querySelector('[aria-label="Question for the owner"]')!, 'Serial or lot number?'); });
    await press('Send question');
    expect(m.ask).toHaveBeenCalledWith('repair', 'SERNR', 'Serial or lot number?', 'orders');
    expect(host.textContent).toContain('Asked approver: Serial or lot number?');
    expect(host.textContent).toContain('Waiting for the system owner on 1 field');
    expect(btn('Save mapping').disabled).toBe(true);
  });

  it('p9-8.4: an open question from an earlier visit shows, and the owner answers it', async () => {
    m.answer.mockResolvedValueOnce({ ok: true, output: { id: 12, source_id: 'repair', src: 'SERNR', decision: 'accepted', target: 'asset.location', rule: null } });
    const asked = { id: 11, decision: 'asked_owner' as const, target: null, rule: null, owner: 'approver', reason: 'Serial or lot number?' };
    await load([row({ decision: asked })], 1);
    expect(host.textContent).toContain('Waiting for the system owner on 1 field');
    await pick('Owner answer: field', 'asset.location');
    await press('Send answer');
    expect(m.answer).toHaveBeenCalledWith(11, { decision: 'accepted', target: 'asset.location' });
    expect(host.textContent).toContain('Accepted asset.location');
    expect(btn('Save mapping').disabled).toBe(false);
  });
});
