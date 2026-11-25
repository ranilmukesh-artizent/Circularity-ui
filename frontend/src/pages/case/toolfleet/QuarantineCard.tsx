import { useState } from 'react';
import { releaseQuarantine, type QuarantineView } from '../../../api/toolFleet';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';

/** "Safety recall RC-2026-017 (repair): quarantined, blocked: release, redeploy, resell". */
export const quarantineLine = (q: QuarantineView): string =>
  `Safety recall ${q.recall_id} (${q.remedy}): ${q.released ? 'released' : 'quarantined'}` +
  (q.blocked.length ? `, blocked: ${q.blocked.join(', ')}` : '');

/** The release button shows for a person who may release, on a repair recall not yet released. */
export const canRelease = (q: QuarantineView, mayRelease: boolean): boolean => mayRelease && q.remedy === 'repair' && !q.released && q.blocked.length > 0;

/** The quarantine of a recalled tool (plan 9, P9-3.7, TF-04): the recall, what it blocks, and for Approver and Admin the release
 * after the fix. A replace or refund recall is never released to the fleet. The server enforces who may release. */
export function QuarantineCard({ caseId, q, mayRelease }: { caseId: string; q: QuarantineView | null; mayRelease: boolean }) {
  const [note, setNote] = useState('');
  const act = useAction();
  if (!q) return null;
  const ready = note.trim().length >= 10;
  const release = async () => {
    const r = await act.run(() => releaseQuarantine(caseId, note.trim()), 4200);
    if (r.ok) toast(`${caseId} released from quarantine.`);
  };
  return (
    <section className={`callout ${q.released ? 'ok' : 'bad'}`} aria-label="Recall quarantine" data-testid="tf-quarantine" style={{ marginTop: 8 }}>
      <p style={{ margin: 0 }}><b>{quarantineLine(q)}</b></p>
      {q.affected_parts.length > 0 && <p className="note" style={{ margin: '4px 0 0' }}>Affected parts, never certified for reuse: {q.affected_parts.join(', ')}</p>}
      {q.released && <p className="note" style={{ margin: '4px 0 0' }} data-testid="tf-quarantine-released">Released by {q.released.by}: {q.released.note}</p>}
      {!q.released && q.remedy !== 'repair' && <p className="note" style={{ margin: '4px 0 0' }}>A replace or refund recall is never released to the fleet.</p>}
      {canRelease(q, mayRelease) && (
        <div style={{ marginTop: 8 }}>
          <textarea aria-label="Why the tool is released" placeholder="What was fixed, and who checked (10 characters or more)" value={note} onChange={(e) => setNote(e.target.value)} style={{ width: '100%' }} />
          <button className="btn pri" disabled={!ready || act.pending} onClick={release} data-testid="tf-quarantine-release">Release after the fix</button>
        </div>
      )}
    </section>
  );
}
