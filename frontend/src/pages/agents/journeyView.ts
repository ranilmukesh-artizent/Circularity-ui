import type { JourneyStage, JourneyStatus } from '../../api/agents';

/** What the journey timeline shows and which controls are on (plan 9, P9-2.21). Pure: Back and Replay change the view only and
 * write nothing; Next is offered only where this person can act (the approval card), never as a silent skip. */

export const STATUS_CHIP: Record<JourneyStatus, string> = {
  Queued: 'line', Running: 'y', Completed: 'ok', 'Waiting for approval': 'y', Warning: 'warn', Failed: 'bad', Skipped: 'line',
};

/** The timeline label of a stage: its number and name. */
export const stageTitle = (s: Pick<JourneyStage, 'n' | 'name'>): string => `${s.n}. ${s.name}`;

/** A stage the run has a record for: Queued means "not reached". */
export const reached = (s: Pick<JourneyStage, 'status'>): boolean => s.status !== 'Queued';

/** Done with: nothing more happens in it. */
export const finished = (s: Pick<JourneyStage, 'status'>): boolean => s.status === 'Completed' || s.status === 'Skipped';

/** A stage that is blocked: it says why and offers escalation, it never skips silently. */
export const blocked = (s: Pick<JourneyStage, 'status'>): boolean => s.status === 'Warning' || s.status === 'Failed';

/** The index of the current stage: the first one not finished and not blocked-before-it; the last stage once all are. */
export function currentIndex(journey: readonly JourneyStage[]): number {
  const i = journey.findIndex((s) => !finished(s));
  return i === -1 ? Math.max(0, journey.length - 1) : i;
}

export interface Controls {
  /** Back: one stage earlier in the view (never writes) */
  back: boolean;
  /** Replay: step through the stored records (never writes); needs at least one record */
  replay: boolean;
  next: { enabled: boolean; label: string; note: string | null; kind: 'approve' | 'wait' | 'none' };
}

/** Which controls are on for the selected stage. `canApprove`: the signed-in person may approve decisions. */
export function controls(journey: readonly JourneyStage[], selected: number, canApprove: boolean, replaying: boolean): Controls {
  const cur = journey[currentIndex(journey)];
  const back = selected > 0 && !replaying;
  const replay = journey.some(reached) && !replaying;
  if (!cur || selected !== currentIndex(journey) || replaying) return { back, replay, next: { enabled: false, label: 'Next', note: null, kind: 'none' } };
  if (cur.status === 'Waiting for approval') {
    return canApprove
      ? { back, replay, next: { enabled: true, label: 'Open the approval', note: null, kind: 'approve' } }
      : { back, replay, next: { enabled: false, label: 'Next', note: 'Waiting for an Approver', kind: 'wait' } };
  }
  if (blocked(cur)) return { back, replay, next: { enabled: false, label: 'Next', note: 'Blocked: escalate to an Admin', kind: 'none' } };
  return { back, replay, next: { enabled: false, label: 'Next', note: 'The agent takes the next step itself', kind: 'none' } };
}

/** The stage indexes a replay walks through, in order: the stages that have a record. */
export const replayFrames = (journey: readonly JourneyStage[]): number[] => journey.flatMap((s, i) => (reached(s) ? [i] : []));
