import { describe, expect, it } from 'vitest';
import { LABELS, sample } from '../charts/testRows';
import {
  activeFacets, ariaSort, cellText, DECISION_COLUMNS, emptyState, exportRows, facet, filterRows, localDataset, matchesQuery, measures, nextSort, reconcileLine, rowCount, sortRows,
  subtitleOf, toCsv, toDataRow, type ViewSpec,
} from './dataView';

const spec = (facets = [facet.status('reconciled')]): ViewSpec => ({ title: 'T', chart: 'flow', section: 'pipeline', facets, measure: measures.uplift });
const run = (s = spec(), st = emptyState()) => localDataset(sample(), s, st, LABELS, 'Jan to Mar', true);

describe('View data: filters', () => {
  it('keeps the rows every chip matches and drops the chip a person removes', () => {
    const rows = sample();
    const s = spec([facet.status('reconciled'), facet.route('resale', LABELS)]);
    expect(filterRows(rows, s, emptyState())).toHaveLength(5);
    const st = { ...emptyState(), removed: ['route:resale'] };
    expect(activeFacets(s, st).map((f) => f.id)).toEqual(['status:reconciled']);
    expect(filterRows(rows, s, st)).toHaveLength(11);
  });
  it('searches the case id, model, asset id and site, and nothing else', () => {
    const [r] = sample();
    expect(matchesQuery(r, r.id.toLowerCase())).toBe(true);
    expect(matchesQuery(r, 'plant 1')).toBe(true);
    expect(matchesQuery(r, r.tenant)).toBe(false);
  });
  it('says what each chip is in plain words', () => {
    expect(facet.route('exit', LABELS).label).toBe('Route: Exit');
    expect(facet.month(2, LABELS).label).toBe('Month: March');
    expect(facet.status('cancelled').label).toBe('Status: demand cancelled');
  });
});

describe('View data: the table', () => {
  it('counts every match and reports the page', () => {
    const d = run();
    expect(d.total).toBe(11);
    expect(d.shown).toBe(11);
    expect(d.subtitle).toBe('11 rows · Jan to Mar · Customer A, Customer B');
  });
  it('adds up what the figure adds up, over every match, not just the page', () => {
    const d = run();
    expect(d.sum).toMatchObject({ value: 6 * 10 + 5 * -20, unit: 'usd' });
    expect(reconcileLine(d.total, d.sum)).toBe('These 11 rows add up to −$40 recovered above the baseline, the figure you opened.');
    expect(reconcileLine(d.total, d.sum, false)).not.toContain('you opened');
    expect(reconcileLine(1, { label: 'decisions', value: 1, unit: 'count' })).toBe('This row adds up to 1 decisions, the figure you opened.');
  });
  it('reports a median as a median', () => {
    const med = localDataset(sample(), { ...spec(), measure: { ...measures.uplift, agg: 'median' } }, emptyState(), LABELS, '', true);
    expect(reconcileLine(med.total, med.sum)).toContain('The median across these 11 rows is');
  });
  it('totals the money columns over the whole selection', () => {
    const d = run();
    expect(d.totals).toMatchObject({ actual: 6 * 110 + 5 * 80, baseline: 11 * 100, vs: -40 });
  });
  it('sorts ascending, then descending, then back to the default; empty cells go last either way', () => {
    expect(nextSort(null, 'actual')).toEqual({ key: 'actual', dir: 'asc' });
    expect(nextSort({ key: 'actual', dir: 'asc' }, 'actual')).toEqual({ key: 'actual', dir: 'desc' });
    expect(nextSort({ key: 'actual', dir: 'desc' }, 'actual')).toBeNull();
    const rows = sample().map((r) => toDataRow(r, LABELS));
    expect(sortRows(rows, { key: 'actual', dir: 'asc' })[0].actual).toBe(80);
    expect(sortRows(rows, { key: 'actual', dir: 'desc' })[0].actual).toBe(110);
    expect(sortRows(rows, { key: 'actual', dir: 'asc' }).slice(-3).every((r) => r.actual == null)).toBe(true);
    expect(sortRows(rows, { key: 'actual', dir: 'desc' }).slice(-3).every((r) => r.actual == null)).toBe(true);
  });
  it('sets aria-sort from the sort', () => {
    expect(ariaSort({ key: 'days', dir: 'desc' }, 'days')).toBe('descending');
    expect(ariaSort({ key: 'days', dir: 'desc' }, 'actual')).toBe('none');
    expect(ariaSort(null, 'actual')).toBe('none');
  });
  it('shows an empty cell as a dash and money as dollars', () => {
    expect(cellText(null, { kind: 'money' })).toBe('—');
    expect(cellText(-1234, { kind: 'money' })).toBe('−$1,234');
    expect(cellText(1, { kind: 'days' })).toBe('1 day');
    expect(cellText('2026-03-04', { kind: 'date' })).toMatch(/Mar 2026/);
  });
  it('says what the subtitle is', () => {
    expect(subtitleOf(1277, 'Jan to Dec', ['A', 'B'])).toBe('1,277 rows · Jan to Dec · A, B');
  });
});

describe('View data: export', () => {
  it('writes every selected row, the shown columns only, and never the override reason', () => {
    const rows = exportRows(sample(), spec(), emptyState(), LABELS);
    expect(rows).toHaveLength(11);
    const csv = toCsv(DECISION_COLUMNS, rows).split('\n');
    expect(csv).toHaveLength(12);
    expect(csv[0]).not.toContain('Override reason');
    expect(csv.join('\n')).not.toContain('Customer asked');
    expect(csv[0].split(',')).toHaveLength(DECISION_COLUMNS.length - 1);
  });
  it('defuses text that a spreadsheet would run as a formula', () => {
    const csv = toCsv([{ key: 'id', label: 'Case', kind: 'text' }], [{ id: '=SUM(A1)' }]);
    expect(csv.split('\n')[1]).toBe("'=SUM(A1)");
  });
});

describe('row counts in the right number', () => {
  it('says 1 row, never 1 rows, in the helper, the subtitle and the reconciliation line', () => {
    expect(rowCount(0)).toBe('0 rows');
    expect(rowCount(1)).toBe('1 row');
    expect(rowCount(1277)).toBe('1,277 rows');
    expect(subtitleOf(1, 'Jan', ['Customer A'])).toBe('1 row · Jan · Customer A');
    expect(reconcileLine(1, null)).toBe('1 row match.');
    expect(reconcileLine(1, { label: 'net', unit: 'usd', value: 5 } as never)).toMatch(/^This row adds up/);
    expect(reconcileLine(2, { label: 'net', unit: 'usd', value: 5 } as never)).toMatch(/^These 2 rows add up/);
  });
});
