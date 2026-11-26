import { useState } from 'react';
import type { ModelerScreen } from '../../../api/types';
import { previewOf } from '../../../pages/modeler/proposal';
import { PreviewCard, sectionsOf, type CardAction } from '../PreviewCard';
import { prefill } from '../store';
import { applyPending, dismissPending, flowSurface, useChange } from './changeStore';

/**
 * The preview card of the proposal waiting for the person (plan 10, 2.3): shown in the column's Proposals section, or in
 * the transcript turn when no column shows that section. Apply to draft is the person's own flow.saveDraft; the
 * assistant never applies, approves or publishes.
 */
export function PendingCard({ s }: { s: ModelerScreen }) {
  const st = useChange();
  const [busy, setBusy] = useState(false);
  const sf = flowSurface();
  const pd = st.pending;
  if (!pd || !sf) return null;
  // the card compares with the working graph the person sees, not the last read
  const m = previewOf(pd.proposal, { ...s, flow: { ...s.flow, graph: sf.graph() } });
  const run = async (adjust: boolean) => {
    setBusy(true);
    try {
      await applyPending(adjust);
    } finally {
      setBusy(false);
    }
  };
  // the sentence goes back in the composer, unsent: the person edits it and proposes again (2.3)
  const rephrase = () => {
    dismissPending();
    prefill(pd.text, 'change');
  };
  const actions: CardAction[] = [
    ...(m.canApply
      ? [
          { label: 'Apply to draft', primary: true, onClick: () => void run(false), disabled: st.stale },
          { label: 'Apply and adjust', onClick: () => void run(true), disabled: st.stale },
        ]
      : []),
    { label: st.stale ? 'Propose again' : 'Rephrase', onClick: rephrase },
    { label: 'Dismiss', onClick: dismissPending },
  ];
  return (
    <PreviewCard
      title={m.title}
      tag={m.tag}
      basis={m.basis}
      where={m.blocked ? undefined : 'Drawn dashed on the canvas'}
      variant={m.blocked ? 'blocked' : 'proposal'}
      sections={sectionsOf(m)}
      limits={m.limits}
      note={st.stale ? 'The draft changed since this was proposed.' : undefined}
      actions={actions}
      busy={busy}
    />
  );
}
