import { useState } from 'react';
import { useSurface } from '../../../utils/workSurface';
import { canUndo, flowSurface, undoApplied, useChange } from './changeStore';

/**
 * The done line after Apply to draft (plan 10, 2.4 and 2.7): "Saved to draft v2 · not published", with Undo while the
 * draft still equals what was applied, and a link to History. Undo is the person's own saveDraft of the earlier graph.
 */
export function AppliedLine() {
  const st = useChange();
  const sf = useSurface(); // re-reads whether the draft still equals what was applied when the page's surface changes
  const [busy, setBusy] = useState(false);
  const a = st.applied;
  if (!a || sf?.kind !== 'flow') return null;
  const ver = sf.draftVer;
  const undo = async () => {
    setBusy(true);
    try {
      await undoApplied();
    } finally {
      setBusy(false);
    }
  };
  return (
    <p className="as-status" data-state="done" role="status" aria-live="polite">
      <span>Saved {a.label} to {ver != null ? `draft v${ver}` : 'the draft'} · not published</span>
      {canUndo(st) && <button type="button" className="as-link" disabled={busy} onClick={() => void undo()}>Undo</button>}
      <button type="button" className="as-link" onClick={() => flowSurface()?.select(null, 'history')}>See in History</button>
    </p>
  );
}
