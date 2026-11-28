import type { Composition, CompositionStep } from '../../../api/compose';
import { STEP_ITEMS, sentBackPin } from './composeView';

/**
 * What a step an approver sent back shows its maker: who sent it back, why, and the flow node the comment is about
 * ("About: condition"). Shared by the Compose panel (`brief`: its state line already gives the reason) and the Set up page.
 * With `hrefFor` a step other than the one in view gets a link to its own work. Nothing for a step that was not sent back.
 */
export function SentBackPin({ c, step, brief = false, hrefFor }: {
  c: Composition;
  step: CompositionStep;
  brief?: boolean;
  hrefFor?: (step: CompositionStep) => string;
}) {
  const pin = sentBackPin(c.steps[step]);
  if (!pin) return null;
  const label = STEP_ITEMS.find(([k]) => k === step)?.[1] ?? step;
  return (
    <div className="cmp-pin">
      {!brief && <p className="note">Sent back{pin.by ? ` by ${pin.by}` : ''}: {pin.reason}</p>}
      {pin.node && <p className="note">About: {pin.node}</p>}
      {hrefFor && <a className="lnk" href={hrefFor(step)}>Open {label}</a>}
    </div>
  );
}
