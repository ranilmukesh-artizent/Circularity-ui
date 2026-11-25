// @vitest-environment jsdom
// Suggested field mappings (plan 9, P9-8.2): the button asks the server, the table shows the masked samples, the calibrated
// confidence as a percentage, the band as a pill and the reason; a row below the bar shows "No proposal" with its candidates.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MappingSuggestion } from '../../api/integration';

const m = vi.hoisted(() => ({ suggest: vi.fn(async (): Promise<unknown> => ({ ok: true, output: {} })), toast: vi.fn() }));
vi.mock('../../api/integration', () => ({ suggestFieldMappings: m.suggest }));
vi.mock('../../components/toast', () => ({ toast: m.toast }));

import { MappingSuggestions } from './MappingSuggestions';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
const row = (o: Partial<MappingSuggestion>): MappingSuggestion => ({
  field: 'SERNR', target: 'asset.serial_number', confidence: 0.91, reason: 'name match 1.00 with serial_number', rule: 'copy',
  proposed_by: 'rule', candidates: [['asset.serial_number', 0.85]], band: 'pre_ticked', resource: 'orders', samples: ['MTR-2041'], ...o,
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
        source_id: 'repair', by_model: false, gaps: ['asset.asset_id'],
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
    expect(cells[0]).toEqual(['SERNR', 'MTR-2041', 'asset.serial_number', '91%', 'Pre-ticked', 'name match 1.00 with serial_number']);
    expect(cells[1][2]).toContain('No proposal');
    expect(cells[1][2]).toContain('asset.lease_rate (0.37)');
    expect(cells[1][4]).toBe('No proposal');
    expect(cells[1][5]).toContain('coded 0/1');
    expect(cells[2][1]).toBe('«masked»');
    expect(cells[2][4]).toBe('Check');
    expect(host.textContent).toContain('asset.asset_id');
  });

  it('p9-8.2: a source with no sample says so; a refusal shows its message', async () => {
    m.suggest.mockResolvedValueOnce({ ok: true, output: { source_id: 'repair', rows: [], gaps: [], by_model: false } });
    await click();
    expect(host.textContent).toContain('No sample yet');
    m.suggest.mockResolvedValueOnce({ ok: false, error: { code: 'not_found', message: 'No source repair.' } });
    await click();
    expect(m.toast).toHaveBeenCalled();
  });
});
