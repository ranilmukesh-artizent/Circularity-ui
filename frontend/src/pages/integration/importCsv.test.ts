import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/actions', () => ({ invoke: vi.fn() }));

import { importSummary, templateColumnsNote, validateCsv } from './importCsv';

const F = ['Warehouse 1', 'Warehouse 2'], T = ['Customer A'];
const HEAD = 'asset_id,qty,condition_grade,location,owner,received';

describe('validateCsv (manual import, by template)', () => {
  it('checks the industrial asset id pattern', () => {
    const r = validateCsv(HEAD + '\nMTR-3101,1,B,Warehouse 1,Customer A,2026-10-05\nT-CMH-9911,1,B,Warehouse 1,Customer A,2026-10-05', 'industrial', F, T);
    if (typeof r === 'string') throw new Error(r);
    expect(r.rows.map((x) => x.errors)).toEqual([[], ['asset_id does not match a known class pattern']]);
  });

  it('accepts any id-shaped asset id for a tool fleet or device template, and refuses a malformed one', () => {
    for (const tpl of ['tool_fleet', 'device']) {
      const r = validateCsv(HEAD + '\nT-CMH-9911,1,B,Warehouse 1,Customer A,2026-10-05\n-bad id,1,B,Warehouse 1,Customer A,2026-10-05', tpl, F, T);
      if (typeof r === 'string') throw new Error(r);
      expect(r.rows.map((x) => x.errors)).toEqual([[], ["asset_id is required (letters, digits, '.', '_' or '-')"]]);
      expect([r.ok, r.err]).toEqual([1, 1]);
    }
  });

  it("keeps the template's columns of each row, valid or rejected", () => {
    const tf = validateCsv(HEAD + ',cls,ft,site,rul\nT-1,1,B,Warehouse 1,Customer A,2026-10-05,core_drill,rental,Site 3,40\nT-2,0,B,Warehouse 1,Customer A,2026-10-05,saw,rental,,', 'tool_fleet', F, T);
    if (typeof tf === 'string') throw new Error(tf);
    expect(tf.rows[0]).toMatchObject({ cls: 'core_drill', ft: 'rental', site: 'Site 3', rul: '40' });
    expect(tf.rows[1]).toMatchObject({ cls: 'saw', ft: 'rental', site: '', rul: '' });
    expect(tf.rows[1].errors).toEqual(['qty must be a positive whole number']);
    const dv = validateCsv(HEAD + ',brand,model,band,ref,doh\nD-77,2,A,Warehouse 2,Customer A,2026-10-05,Acme,X1,mid,320,12', 'device', F, T);
    if (typeof dv === 'string') throw new Error(dv);
    expect(dv.rows[0]).toMatchObject({ brand: 'Acme', model: 'X1', band: 'mid', ref: '320', doh: '12' });
    const ind = validateCsv(HEAD + ',cls\nMTR-3101,1,B,Warehouse 1,Customer A,2026-10-05,motor', 'industrial', F, T);
    if (typeof ind === 'string') throw new Error(ind);
    expect(ind.rows[0]).not.toHaveProperty('cls');
  });

  it('names a missing required column', () => {
    expect(validateCsv('asset_id,qty\nT-1,1', 'tool_fleet', F, T)).toBe('Missing required column: condition_grade, location, owner, received');
  });
});

describe('the import help and the result', () => {
  it('lists the columns a template reads', () => {
    expect(templateColumnsNote('industrial')).toBe('');
    expect(templateColumnsNote('tool_fleet')).toBe('Tool fleet cases also read: cls, ft, site, rul (grade from condition_grade).');
    expect(templateColumnsNote('device')).toBe('Device cases also read: brand, model, band, ref, doh (grade from condition_grade, qty from qty).');
  });

  it('says how many cases opened, were already open or did not open, with the reasons', () => {
    const base = '3 rows loaded for evaluation. They are tagged manual and will not trigger any instruction.';
    expect(importSummary(3, { id: 'IMP-1', ok: 3 })).toBe(base);
    expect(importSummary(3, { id: 'IMP-1', ok: 3, cases_opened: 1, cases_skipped: 1, cases_failed: 1,
      case_failures: [{ asset_id: 'T-2', code: 'validation_error', reason: 'grade must be A-D' }] })) // prettier-ignore
      .toBe(base + ' Cases: 1 opened, 1 already open, 1 not opened. T-2: grade must be A-D');
    expect(importSummary(3, { id: 'IMP-1', ok: 3, cases_opened: 3 })).toBe(base + ' Cases: 3 opened, 0 already open, 0 not opened.');
  });
});
