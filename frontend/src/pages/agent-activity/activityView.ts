/** View logic of the Agent activity page: the filters and the counts per kind. Pure, so it is tested without the page. */
import type { ActivityEvent, ActivityKind } from '../../api/agentActivity';

export const KIND_LABEL: Record<ActivityKind, string> = {
  held: 'Held for a person',
  accepted: 'Accepted',
  rejected: 'Rejected',
  refused: 'Refused',
  run: 'Run',
};

export const KIND_CHIP: Record<ActivityKind, string> = { held: 'y', accepted: 'ok', rejected: 'warn', refused: 'bad', run: 'line' };

export const KINDS = Object.keys(KIND_LABEL) as ActivityKind[];

export interface ActivityFilter {
  kind: ActivityKind | 'all';
  agent: string;
  pack: string;
  caseText: string;
}

export const NO_FILTER: ActivityFilter = { kind: 'all', agent: '', pack: '', caseText: '' };

/** The events that pass every filter that is set; the case filter matches a part of the case id. */
export function filterEvents(events: readonly ActivityEvent[], f: ActivityFilter): ActivityEvent[] {
  const c = f.caseText.trim().toLowerCase();
  return events.filter(
    (e) =>
      (f.kind === 'all' || e.kind === f.kind) &&
      (!f.agent || e.agent === f.agent) &&
      (!f.pack || e.pack === f.pack) &&
      (!c || (e.case_id ?? '').toLowerCase().includes(c)),
  );
}

export function countByKind(events: readonly ActivityEvent[]): Record<ActivityKind, number> {
  const out = { held: 0, accepted: 0, rejected: 0, refused: 0, run: 0 };
  for (const e of events) out[e.kind] += 1;
  return out;
}
