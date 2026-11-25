import { describe, expect, it } from 'vitest';
import type { JourneyStage, JourneyStatus } from '../../api/agents';
import { blocked, controls, currentIndex, replayFrames, STATUS_CHIP, stageTitle } from './journeyView';

const NAMES = ['Lease end', 'Return authorised', 'Pickup and transit', 'Received', 'Inspect and grade', 'Decide', 'Approve', 'Execute', 'Outcome', 'Reconcile'];
const stage = (n: number, status: JourneyStatus): JourneyStage => ({
  n, name: NAMES[n - 1], status, agent: 'stage-x', purpose: '', activity: '', evidence: [], calls: [], result: {}, validation: [], state_change: '', next_step: '', reading: null,
});
/** a journey from the statuses of its stages */
const journey = (...s: JourneyStatus[]): JourneyStage[] => s.map((x, i) => stage(i + 1, x));
const WAITING = journey(...Array<JourneyStatus>(3).fill('Skipped'), 'Completed', 'Completed', 'Completed', 'Waiting for approval', 'Queued', 'Queued', 'Queued');

describe('the ten-stage journey view (plan 9, P9-2.21)', () => {
  it('labels a stage with its number and name', () => {
    expect(stageTitle(stage(6, 'Completed'))).toBe('6. Decide');
  });

  it('has a chip for every status', () => {
    const all: JourneyStatus[] = ['Queued', 'Running', 'Completed', 'Waiting for approval', 'Warning', 'Failed', 'Skipped'];
    expect(all.map((s) => STATUS_CHIP[s])).toEqual(['line', 'y', 'ok', 'y', 'warn', 'bad', 'line']);
  });

  it('finds the current stage: the first not finished, the last when all are', () => {
    expect(currentIndex(WAITING)).toBe(6);
    expect(currentIndex(journey(...Array<JourneyStatus>(10).fill('Completed')))).toBe(9);
    expect(currentIndex(journey(...Array<JourneyStatus>(10).fill('Queued')))).toBe(0);
  });

  it('offers Next at the approval only to a person who may approve', () => {
    expect(controls(WAITING, 6, true, false).next).toEqual({ enabled: true, label: 'Open the approval', note: null, kind: 'approve' });
    expect(controls(WAITING, 6, false, false).next).toEqual({ enabled: false, label: 'Next', note: 'Waiting for an Approver', kind: 'wait' });
  });

  it('never offers Next on a stage that is not the current one, or while replaying', () => {
    expect(controls(WAITING, 3, true, false).next.enabled).toBe(false);
    expect(controls(WAITING, 6, true, true).next.enabled).toBe(false);
  });

  it('says a blocked stage is blocked and offers escalation, never a skip', () => {
    const held = journey('Skipped', 'Skipped', 'Skipped', 'Warning', ...Array<JourneyStatus>(6).fill('Queued'));
    expect(blocked(held[3])).toBe(true);
    const c = controls(held, 3, true, false);
    expect(c.next).toEqual({ enabled: false, label: 'Next', note: 'Blocked: escalate to an Admin', kind: 'none' });
  });

  it('enables Back after the first stage and Replay when a record exists', () => {
    expect(controls(WAITING, 0, true, false).back).toBe(false);
    expect(controls(WAITING, 6, true, false).back).toBe(true);
    expect(controls(WAITING, 6, true, true)).toMatchObject({ back: false, replay: false });
    expect(controls(journey(...Array<JourneyStatus>(10).fill('Queued')), 0, true, false).replay).toBe(false);
    expect(controls(WAITING, 6, true, false).replay).toBe(true);
  });

  it('replays only the stages that have a record', () => {
    expect(replayFrames(WAITING)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });
});
