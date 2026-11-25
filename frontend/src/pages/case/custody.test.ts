import { describe, expect, it } from 'vitest';
import type { CustodyEntry, RecordMatchView } from '../../api/case';
import { ago, custodyLines, recordMatchLine } from './custody';

const log: CustodyEntry[] = [
  { at: '2026-10-07T09:00:00+00:00', event: 'received', source: 'wms', location: 'Warehouse 1', by: 'planner.a' },
  { at: '2026-10-07T11:30:00+00:00', event: 'moved', source: 'wms', location: 'Warehouse 2', by: 'system' },
  { at: '2026-10-08T08:05:00+00:00', event: 'matched', source: 'lease', location: 'Warehouse 2', by: 'system' },
];

describe('P9-1.10 custodyLines (X-08)', () => {
  it('lists the newest event first, with where, from which source, when and by whom', () => {
    const lines = custodyLines(log);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe('Matched to the system of record at Warehouse 2 · lease · 08 Oct 08:05 UTC · by system');
    expect(lines[1]).toBe('Moved to Warehouse 2 · wms · 07 Oct 11:30 UTC · by system');
    expect(lines[2]).toBe('Received at Warehouse 1 · wms · 07 Oct 09:00 UTC · by planner.a');
  });

  it('leaves out what an entry does not know and writes nothing for no custody', () => {
    expect(custodyLines([{ at: '2026-10-07T09:00:00+00:00', event: 'released', source: null, location: null, by: 'system' }]))
      .toEqual(['Released · 07 Oct 09:00 UTC · by system']);
    expect(custodyLines(null)).toEqual([]);
    expect(custodyLines([])).toEqual([]);
  });

  it('does not reorder the list it is given', () => {
    custodyLines(log);
    expect(log[0].event).toBe('received');
  });
});

describe('P9-1.10 recordMatchLine (X-08)', () => {
  const found: RecordMatchView = {
    found: true, system: 'Lease system', key: 'LS-5412', syncedAt: '2026-10-07T08:00:00+00:00', syncedMinutesAgo: 180, since: null, owner: null,
  };

  it('says where the record is and how long ago it synced', () => {
    expect(recordMatchLine(found)).toBe('System of record: found in Lease system record LS-5412, synced 3 h ago');
  });

  it('says who got the exception when the asset is not found', () => {
    expect(recordMatchLine({ ...found, found: false, key: null, syncedAt: null, syncedMinutesAgo: undefined, owner: 'Planner' }))
      .toBe('Not found in Lease system: exception sent to Planner');
  });

  it('has no line for a pack without a system of record', () => {
    expect(recordMatchLine(null)).toBeNull();
  });

  it('formats minutes, hours and days', () => {
    expect([ago(5), ago(125), ago(3000)]).toEqual(['5 min ago', '2 h ago', '2 d ago']);
  });
});
