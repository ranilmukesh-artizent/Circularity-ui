import { describe, expect, it } from 'vitest';
import type { Rollout } from '../../api/rollout';
import { currentStep, stepStates } from './rolloutSteps';

const R = (stage: Rollout['stage'], can: Partial<Rollout['can']> = {}): Rollout => ({
  flow_id: 1, name: 'Industrial returns', stage, status: 'draft', base_ver: 1, candidate_ver: 2, rollouts: [], counts: { canary: 0, control: 0 },
  replay_run_id: null, replay_done: stage !== 'replay', can: { startCanary: null, widen: null, pause: null, full: null, rollback: null, ...can },
});
const states = (r: Rollout) => stepStates(r).map((x) => [x.step, x.state]);

describe('stepStates', () => {
  it('in shadow: replay done, shadow current, canary and full next', () => {
    expect(states(R('shadow'))).toEqual([['replay', 'done'], ['shadow', 'current'], ['canary', 'next'], ['full', 'next']]);
  });

  it('a step that cannot be taken yet says why', () => {
    const got = stepStates(R('shadow', { startCanary: 'Replay the candidate first.', full: 'Run a canary first.' }));
    expect(got[2]).toMatchObject({ step: 'canary', state: 'unavailable', note: 'Replay the candidate first.' });
    expect(got[3]).toMatchObject({ step: 'full', state: 'unavailable', note: 'Run a canary first.' });
  });

  it('a running canary: earlier steps done, canary current, full next or unavailable with the reason', () => {
    expect(states(R('canary'))).toEqual([['replay', 'done'], ['shadow', 'done'], ['canary', 'current'], ['full', 'next']]);
    expect(stepStates(R('canary', { full: 'The person who made the changes cannot publish them.' }))[3].state).toBe('unavailable');
  });

  it('paused stays on canary and says paused; rolled back is back at shadow', () => {
    expect(currentStep('paused')).toBe('canary');
    expect(stepStates(R('paused'))[2]).toMatchObject({ state: 'current', note: 'Paused' });
    expect(states(R('rolled_back'))[1]).toEqual(['shadow', 'current']);
  });

  it('full: everything before is done and full is current', () => {
    expect(states(R('full'))).toEqual([['replay', 'done'], ['shadow', 'done'], ['canary', 'done'], ['full', 'current']]);
  });
});
