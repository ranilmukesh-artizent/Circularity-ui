import { describe, expect, it } from 'vitest';
import { recordLabel } from './fabricFormat';

describe('recordLabel (UI QA 21)', () => {
  it('splits a tenant-scoped key into the record and its tenant', () => {
    expect(recordLabel('Customer A:SYNUC000000000001')).toEqual({ name: 'SYNUC000000000001', scope: 'Customer A' });
  });
  it('leaves a plain key alone', () => {
    expect(recordLabel('MTR-2041')).toEqual({ name: 'MTR-2041', scope: null });
    expect(recordLabel(':x')).toEqual({ name: ':x', scope: null });
  });
});
