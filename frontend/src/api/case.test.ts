import { describe, expect, it, vi } from 'vitest';
import { invoke } from './actions';
import { TREATMENT_CODE, attachReporting, creditLine, creditMismatch, fixedAssetLine, leaseResidualLine, resolveSettlement, waitingEvidence } from './case';

vi.mock('./actions', () => ({ invoke: vi.fn(async () => ({ ok: true, data: { case_id: 'RT-9', closed: true } })) }));

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

describe('P9-13.4 customer credit (X-16)', () => {
  const credit = { memo: 'CM-90000001', amount: 160, erp_amount: 160, basis: 'grade_table' as const, grade_received: 'B', percent: 80, quote: 200, status: 'matched' as const };
  it('shows the credit with its basis', () => {
    expect(creditLine({ finance: { credit } })).toBe('Customer credit · CM-90000001 · $160.00 (grade B at 80 % of the $200.00 quote)');
    expect(creditLine({})).toBeNull();
  });
  it('names the two amounts of a mismatch, only while it waits', () => {
    expect(creditMismatch({ finance: { credit: { ...credit, erp_amount: 150, status: 'mismatch' } } })).toBe('The ERP posted $150.00; the case says $160.00');
    expect(creditMismatch({ finance: { credit } })).toBeNull();
  });
  it('resolveSettlement is an action of the facade', () => {
    expect(typeof resolveSettlement).toBe('function');
  });
});

describe('P9-13.5 reporting evidence (X-16)', () => {
  it('attachReporting calls case.attachReporting with the facility evidence', async () => {
    await attachReporting('RT-9', { mass_kg: 42.5, material: 'steel', treatment_code: 'R4', source_ref: 'FAC-77' });
    expect(invoke).toHaveBeenCalledWith('case.attachReporting', { case_id: 'RT-9', mass_kg: 42.5, material: 'steel', treatment_code: 'R4', source_ref: 'FAC-77' });
  });
  it('knows an R or D code only', () => {
    expect(TREATMENT_CODE.test('R4') && TREATMENT_CODE.test('D10')).toBe(true);
    expect(TREATMENT_CODE.test('X9') || TREATMENT_CODE.test('R123')).toBe(false);
  });
  it('shows what a waiting case lacks, and nothing otherwise', () => {
    expect(waitingEvidence([{ state: 'done' }, { state: 'waiting_evidence', waiting: 'Waiting for reporting evidence: treatment code (G-REP-2)' }])).toContain('treatment code (G-REP-2)');
    expect(waitingEvidence([{ state: 'done' }])).toBeNull();
  });
});
