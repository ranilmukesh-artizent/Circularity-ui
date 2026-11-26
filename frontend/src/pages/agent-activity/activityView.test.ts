import { describe, expect, it } from 'vitest';
import type { ActivityEvent } from '../../api/agentActivity';
import { countByKind, filterEvents, KIND_LABEL, NO_FILTER } from './activityView';

const ev = (id: string, o: Partial<ActivityEvent>): ActivityEvent => ({
  id, at: '2026-11-26T10:00:00+00:00', agent: 'coordinator', agentName: 'Handoff Coordinator', kind: 'held', title: 'Submit a decision',
  detail: '', case_id: 'RT-1002', pack: 'industrial', run_id: null, proposal_id: null, ...o,
});
const list = [
  ev('a', { kind: 'held' }),
  ev('b', { kind: 'refused', agent: 'finder', agentName: 'Opportunity Finder' }),
  ev('c', { kind: 'accepted', pack: 'tool_fleet', case_id: 'TF-1' }),
  ev('d', { kind: 'run', case_id: null }),
];

describe('filterEvents', () => {
  it('keeps everything with no filter', () => expect(filterEvents(list, NO_FILTER)).toHaveLength(4));
  it('filters by kind, agent and pack', () => {
    expect(filterEvents(list, { ...NO_FILTER, kind: 'refused' }).map((e) => e.id)).toEqual(['b']);
    expect(filterEvents(list, { ...NO_FILTER, agent: 'finder' }).map((e) => e.id)).toEqual(['b']);
    expect(filterEvents(list, { ...NO_FILTER, pack: 'tool_fleet' }).map((e) => e.id)).toEqual(['c']);
  });
  it('filters by case id, ignoring case and spaces', () => {
    expect(filterEvents(list, { ...NO_FILTER, caseText: ' rt-1002 ' }).map((e) => e.id)).toEqual(['a', 'b']);
  });
});

describe('countByKind', () => {
  it('counts each kind, zero for the missing ones', () => {
    expect(countByKind(list)).toEqual({ held: 1, accepted: 1, rejected: 0, refused: 1, run: 1 });
  });
  it('has a plain label for every kind', () => {
    expect(Object.keys(KIND_LABEL).sort()).toEqual(['accepted', 'held', 'refused', 'rejected', 'run']);
  });
});
