import { describe, expect, it } from 'vitest';
import { modelSentence, partsOf, readingLine, rowsText, runUnits, selectionLine, tickedTables, toggleTable, waitedLine, WHOLE_SOURCE } from './systemsView';

const T = (n: string, resource?: string) => ({ n, resource });
const none = { fields: 0, pre_ticked: 0, check: 0, none: 0, asked_owner: 0 };

describe('tables ticked', () => {
  const ts = [T('a'), T('b'), T('c')];
  it('every table until the person chooses', () => {
    expect(tickedTables(ts, null).map((t) => t.n)).toEqual(['a', 'b', 'c']);
  });
  it('the first change starts from every table', () => {
    const s = toggleTable(ts, null, 'b');
    expect([...s].sort()).toEqual(['a', 'c']);
    expect(tickedTables(ts, s).map((t) => t.n)).toEqual(['a', 'c']);
    expect([...toggleTable(ts, s, 'b')].sort()).toEqual(['a', 'b', 'c']);
  });
});

describe('selectionLine', () => {
  it('says how many tables are used', () => {
    expect(selectionLine(0, 0)).toBe('No tables yet');
    expect(selectionLine(0, 3)).toBe('No table used');
    expect(selectionLine(3, 3)).toBe('All 3 tables used');
    expect(selectionLine(2, 3)).toBe('2 of 3 tables used');
    expect(selectionLine(1, 1)).toBe('The table is used');
  });
});

describe('rowsText', () => {
  it('formats a count and leaves other text alone', () => {
    expect(rowsText('1204')).toBe('1,204 rows');
    expect(rowsText('1')).toBe('1 row');
    expect(rowsText('1.2k')).toBe('1.2k rows');
    expect(rowsText('')).toBe('');
  });
});

describe('runUnits', () => {
  it('one run per resource; modelled tables share one run on the whole source', () => {
    expect(runUnits([T('orders', 'orders'), T('parts', 'parts')]).map((u) => u.resource)).toEqual(['orders', 'parts']);
    expect(runUnits([T('x'), T('y')])).toEqual([WHOLE_SOURCE]);
    expect(runUnits([T('orders', 'orders'), T('x')]).map((u) => u.key)).toEqual(['orders', '*']);
    expect(runUnits([])).toEqual([]);
  });
});

describe('partsOf', () => {
  it('a system with no source waits at the connection', () => {
    const p = partsOf({ status: 'needs_adapter', source_id: null, mapping: none }, 0, 0, true);
    expect(p.map((x) => x.state)).toEqual(['now', 'todo', 'todo']);
  });
  it('a connected source without tables waits at the data', () => {
    const p = partsOf({ status: 'connected', source_id: 's', mapping: none }, 0, 0, true);
    expect(p.map((x) => x.state)).toEqual(['done', 'now', 'todo']);
    expect(p[1].note).toBe('No sample yet');
  });
  it('a source that sent records without tables is past the data', () => {
    const p = partsOf({ status: 'connected', source_id: 's', mapping: { ...none, fields: 49, check: 49 } }, 0, 0, true);
    expect(p.map((x) => x.state)).toEqual(['done', 'done', 'done']);
    expect(p[1].note).toBe('Records sent, no tables');
  });
  it('tables ticked, then mapped', () => {
    const p = partsOf({ status: 'connected', source_id: 's', mapping: none }, 3, 3, true);
    expect(p.map((x) => x.state)).toEqual(['done', 'done', 'now']);
    const q = partsOf({ status: 'connected', source_id: 's', mapping: { ...none, fields: 9, pre_ticked: 9 } }, 3, 3, true);
    expect(q.map((x) => x.state)).toEqual(['done', 'done', 'done']);
  });
  it('a role that cannot read tables is told so', () => {
    expect(partsOf({ status: 'connected', source_id: 's', mapping: none }, 0, 0, false)[1].note).toBe('Not shown to your role');
  });
});

describe('modelSentence', () => {
  it('says what the model read, or that none answered', () => {
    expect(modelSentence(undefined, 5)).toBe('');
    expect(modelSentence({ asked: 14, answered: 14, fields: 41, seconds: 12, stopped: null }, 41)).toBe('A model read 14 of 41 fields; the rest were matched by name and values.');
    expect(modelSentence({ asked: 14, answered: 0, fields: 41, seconds: 1, stopped: 'no_model' }, 41)).toBe('No model answered; every field was matched by name and values.');
    expect(modelSentence({ asked: 14, answered: 6, fields: 41, seconds: 25, stopped: 'budget' }, 41)).toContain('before its time ran out');
  });
});

describe('lines', () => {
  it('progress and waiting', () => {
    expect(readingLine(1, 3)).toBe('Reading table 2 of 3…');
    expect(waitedLine(7)).toBe('7 s');
    expect(waitedLine(75)).toBe('1 min 15 s');
  });
});
