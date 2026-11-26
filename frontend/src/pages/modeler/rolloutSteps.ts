/** What each step of the Rollout panel is now (pure; everything comes from `rollout.get`, nothing is computed on the server for it). */
import { ROLLOUT_STEPS, type Rollout } from '../../api/rollout';

export type RolloutStep = (typeof ROLLOUT_STEPS)[number];
export type StepState = 'done' | 'current' | 'next' | 'unavailable';
export interface StepView { step: RolloutStep; state: StepState; note: string }

/** The step to mark as current: a paused canary is still the Canary step; a rolled-back flow is back at Shadow. */
export const currentStep = (stage: Rollout['stage']): RolloutStep | null =>
  stage === 'paused' ? 'canary' : stage === 'rolled_back' ? 'shadow' : stage;

/** What each step means, shown under its name. */
export const STEP_MEANING: Record<RolloutStep, string> = {
  replay: 'Run the candidate over past cases',
  shadow: 'Run it beside the live flow, no effect',
  canary: 'Release it to one region at a share',
  full: 'Publish it for every case',
};

/** The state of every step: before the current one done, the current one, the later ones next, or unavailable with the server's reason. */
export function stepStates(r: Rollout): StepView[] {
  const cur = currentStep(r.stage);
  const at = cur ? ROLLOUT_STEPS.indexOf(cur) : -1;
  return ROLLOUT_STEPS.map((step, i): StepView => {
    if (i < at) return { step, state: 'done', note: 'Done' };
    if (i === at) return { step, state: 'current', note: r.stage === 'paused' ? 'Paused' : r.stage === 'rolled_back' ? 'Rolled back, back here' : 'Now' };
    const reason = step === 'canary' ? r.can.startCanary : step === 'full' ? r.can.full : null;
    return reason ? { step, state: 'unavailable', note: reason } : { step, state: 'next', note: 'Next' };
  });
}
