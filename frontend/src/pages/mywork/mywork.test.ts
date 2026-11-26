import { describe, expect, it } from 'vitest';
import type { WorkItem } from '../../api/mywork';
import { conflictGroupTitle, countsByKind, dueLabel, groupConflicts, meaningful, nonReturnLine, readable, sortItems } from './mywork';

const item = (o: Partial<WorkItem>): WorkItem => ({
  id: 'w:1', kind: 'exception', case_id: null, title: 't', cause: null, action: null, owner: 'Planner', due: null, overdue: false, priority: 100, go: null, ...o,
}); // prettier-ignore

describe('My work (plan 9 P9-1.7, I-20)', () => {
  it('sorts by priority, then due time, with no due time last', () => {
    const rows = [
      item({ id: 'a', priority: 100, due: null }),
      item({ id: 'b', priority: 100, due: '2026-10-08T09:00:00+00:00' }),
      item({ id: 'c', priority: 50, due: null }),
      item({ id: 'd', priority: 100, due: '2026-10-07T09:00:00+00:00' }),
    ];
    expect(sortItems(rows).map((r) => r.id)).toEqual(['c', 'd', 'b', 'a']);
    expect(rows.map((r) => r.id)).toEqual(['a', 'b', 'c', 'd']); // the input is not changed
  });

  it('counts the items of each kind, with every kind present', () => {
    const rows = [item({ kind: 'exception' }), item({ kind: 'exception' }), item({ kind: 'proposal' }), item({ kind: 'task' })];
    expect(countsByKind(rows)).toEqual({ exception: 2, approval: 0, needs_info: 0, proposal: 1, conflict: 0, task: 1 });
  });

  it('says when an item is due or overdue', () => {
    expect(dueLabel(item({ due: null }))).toBe('');
    expect(dueLabel(item({ due: '2026-10-08T09:00:00+00:00' }))).toMatch(/^Due /);
    expect(dueLabel(item({ due: '2026-10-06T09:00:00+00:00', overdue: true }))).toMatch(/^Overdue /);
  });

  it('finds the contract line of a non-return fee item, and only of that item (P9-3.18)', () => {
    expect(nonReturnLine(item({ title: 'Non-return fee FL-30128-04' }))).toBe('FL-30128-04');
    expect(nonReturnLine(item({ id: 'p:1', title: 'Non-return fee FL-30128-04' }))).toBeNull();
    expect(nonReturnLine(item({ kind: 'task', title: 'Non-return fee FL-30128-04' }))).toBeNull();
    expect(nonReturnLine(item({ title: 'Check the variance on RT-1' }))).toBeNull();
    expect(nonReturnLine(item({ title: 'Non-return fee ' }))).toBeNull();
  });
});

describe('My work conflict grouping (UI audit gap 20)', () => {
  const rows = [
    item({ id: 'c:1', kind: 'conflict', go: 'integration/conflicts' }),
    item({ id: 'a:1', kind: 'approval' }),
    item({ id: 'c:2', kind: 'conflict', go: 'integration/conflicts' }),
    item({ id: 'p:1', kind: 'proposal' }),
  ];
  it('moves the conflicts into one group and keeps every other row in order', () => {
    const g = groupConflicts(rows);
    expect(g.rows.map((r) => r.id)).toEqual(['a:1', 'p:1']);
    expect(g.conflicts.map((r) => r.id)).toEqual(['c:1', 'c:2']);
  });
  it('words the group row with the count', () => {
    expect(conflictGroupTitle(154)).toBe('154 data conflicts');
    expect(conflictGroupTitle(1)).toBe('1 data conflict');
  });
  it('has no group without conflicts', () => {
    expect(groupConflicts([item({ id: 'a:1', kind: 'approval' })]).conflicts).toEqual([]);
  });
});

describe('My work text (UI fix 29)', () => {
  it('reads snake_case field names as words and keeps ids', () => {
    expect(readable('Sources disagree on work_order_ref of MTR-1108')).toBe('Sources disagree on work order reference of MTR-1108');
    expect(readable('Sources disagree on work_order_type of RT-1073')).toBe('Sources disagree on work order type of RT-1073');
  });
  it('drops a lone dot', () => {
    expect(meaningful('.')).toBe('');
    expect(meaningful(null)).toBe('');
    expect(meaningful('Demand cancelled.')).toBe('Demand cancelled.');
  });
});
