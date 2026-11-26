import { describe, expect, it } from 'vitest';
import { fixedAssetLine, leaseResidualLine } from './case';

describe('P9-13.1 fixedAssetLine (X-13)', () => {
  it('shows the ERP retirement with its gain', () => {
    const line = fixedAssetLine({ finance: { asset: { kind: 'retire', doc: 'FA-100001', proceeds: 19250, book_value: 18000, gain_loss: 1250 } } });
    expect(line).toBe('Fixed-asset retirement · FA-100001 · proceeds $19,250 · book value $18,000 · gain $1,250 (from the ERP)');
  });
  it('says loss for a negative result, and shows a transfer document', () => {
    expect(fixedAssetLine({ finance: { asset: { kind: 'retire', doc: 'FA-2', proceeds: 100, book_value: 300, gain_loss: -200 } } })).toContain('loss $200');
    expect(fixedAssetLine({ finance: { asset: { kind: 'transfer', doc: 'FA-3' } } })).toBe('Asset transfer · FA-3 (from the ERP)');
  });
  it('is null for a case without the asset block (the industrial cases)', () => {
    expect(fixedAssetLine({})).toBeNull();
  });
});

describe('P9-13.2 leaseResidualLine (X-13)', () => {
  it('shows the gain against the residual', () => {
    const r = { contract_ref: 'LC-900001', residual: 18000, proceeds: 19250, gain_loss: 1250 };
    expect(leaseResidualLine({ finance: { residual: r } })).toBe('Lease residual · contract LC-900001 · residual $18,000 · proceeds $19,250 · gain against residual $1,250');
    expect(leaseResidualLine({ finance: { residual: { ...r, proceeds: 16400, gain_loss: -1600 } } })).toContain('loss against residual $1,600');
  });
  it('has no line without a residual', () => {
    expect(leaseResidualLine({})).toBeNull();
  });
});
