import { describe, expect, it } from 'vitest';
import type { WorkItem } from '../../api/mywork';
import { countsByKind, dueLabel, sortItems } from './mywork';

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
});
