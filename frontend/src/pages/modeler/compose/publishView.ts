/* Pure helper of the Publish step (28 Nov 2026): the four things publishing needs, and where each stands. */
import type { CompositionStatus } from '../../../api/compose';

export type CheckState = 'done' | 'now' | 'todo';
export interface PublishCheck {
  id: 'approved' | 'flow' | 'replay' | 'publish';
  state: CheckState;
}

/**
 * The checklist for a composition, its decision flow's status (pub: live with no draft; draft; review; shadow) and whether the
 * draft's replay has a report. A line that is not done is "now" when someone can act on it today and "todo" when it waits
 * for another line: the approval and the flow can move at any time, the replay needs the flow's draft, and publishing needs
 * the three before it. The replay may be run before the flow is approved, so it is done as soon as it has a report.
 */
export function publishChecks(status: CompositionStatus, flowStatus: string, hasReport: boolean): PublishCheck[] {
  const done = {
    approved: status === 'approved' || status === 'published',
    flow: flowStatus === 'shadow' || status === 'published',
    replay: hasReport || status === 'published',
    publish: status === 'published',
  };
  const waits = { approved: false, flow: false, replay: flowStatus === 'pub', publish: !(done.approved && done.flow && done.replay) };
  return (['approved', 'flow', 'replay', 'publish'] as const).map((id) => ({ id, state: done[id] ? 'done' : waits[id] ? 'todo' : 'now' }));
}
