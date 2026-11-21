import { describe, expect, it, vi } from 'vitest';

vi.mock('./actions', () => ({ invoke: vi.fn() }));

import { hashId, importInput, layoutTables, type ImportRow, type TableModel } from './integration';

const row = (asset_id: string, errors: string[] = []): ImportRow & { warn: string[] } => ({
  asset_id, qty: '1', grade: 'B', location: 'Warehouse 1', owner: 'Customer A', received: '2026-10-05', errors, warn: [],
});

describe('importInput (import.commit)', () => {
  it('keeps the demo hash over every validated row and sends only the valid rows, without the check results', () => {
    const rows = [row('MTR-3101'), row('BAT-0201', ['qty must be a positive whole number']), row('PMP-2210')];
    const i = importInput(2, 1, rows);
    expect(i.ok).toBe(2);
    expect(i.err).toBe(1);
    expect(i.hash).toBe(hashId(JSON.stringify(rows)));
    expect(i.rows.map((r) => r.asset_id)).toEqual(['MTR-3101', 'PMP-2210']);
    expect(Object.keys(i.rows[0]).sort()).toEqual(['asset_id', 'grade', 'location', 'owner', 'qty', 'received']);
  });
  it('sends the rejected rows too, so the server holds them as failed records (plan 6 B3)', () => {
    const i = importInput(1, 1, [row('MTR-3101'), row('BAT-0201', ['qty must be a positive whole number'])]);
    expect(i.rejected.map((r) => r.asset_id)).toEqual(['BAT-0201']);
    expect(Object.keys(i.rejected[0]).sort()).toEqual(['asset_id', 'grade', 'location', 'owner', 'qty', 'received']);
  });
});

describe('layoutTables (tgLayout)', () => {
  it('places a cluster of up to two tables per row, starting at the top left', () => {
    const t = (n: string, cl: string) => ({ n, cl, desc: '', cols: [['ID', '']] as [string, string][], rows: '—', x: 0, y: 0 });
    const m: TableModel = { cl: [['a', 'A Tables'], ['b', 'B Tables']], t: [t('A1', 'a'), t('A2', 'a'), t('B1', 'b')], fk: [] } as unknown as TableModel;
    layoutTables(m);
    expect([m.t[0].x, m.t[0].y]).toEqual([24, 58]);
    expect(m.t[1].x).toBe(24 + 190 + 16);
    expect(m.t[2].x).toBe(24 + 2 * 190 + 16 + 44 + 14);
  });
});
