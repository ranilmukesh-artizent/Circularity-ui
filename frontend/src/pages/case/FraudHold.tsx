import { useState } from 'react';
import { when, type CaseRec } from '../../api/case';
import { fraudLine, fraudOf, heldByReview, rejectFraud, releaseFraud, reviewLine, reviewSources, type FraudRecord } from '../../api/fraud';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/** Plan 9, P9-2.11 (X-15), P9-2.24: a case held for fraud review. The banner is the same on the Overview and on every stage page
 *  of a held case (a person who lands on a stage page meets it there). Everyone sees the score and each signal with its source and time; a
 *  person with approval rights releases the hold or rejects the return, giving a reason (no agent does either). */
export function FraudHold({ c }: { c: CaseRec }) {
  const f: FraudRecord | null = fraudOf(c);
  const action = useAction();
  const [reason, setReason] = useState('');
  if (!f || f.status !== 'held') return null;
  const ready = reason.trim().length >= 10;
  const decide = async (kind: 'release' | 'reject') => {
    const r = await action.run(() => (kind === 'release' ? releaseFraud(c.id, reason.trim()) : rejectFraud(c.id, reason.trim())), 4200);
    if (r.ok) toast(kind === 'release' ? `${c.id} released from fraud review.` : `The return of ${c.id} was rejected.`);
  };
  return (
    <section className="callout bad" role="alert" aria-label="Fraud hold" data-testid="fraud-hold">
      <p style={{ margin: 0 }}><b>{fraudLine(f)}</b></p>
      {heldByReview(f) && <p className="note" style={{ margin: '4px 0 0' }} data-testid="fraud-review-hold">The model&apos;s review asked for this hold; the score alone did not.</p>}
      {reviewLine(f) && (
        <p className="note" style={{ margin: '4px 0 0' }} data-testid="fraud-review">
          {reviewLine(f)}
          {reviewSources(f).length > 0 && <> · sources: {reviewSources(f).join(', ')}</>}
        </p>
      )}
      <ul className="note" style={{ margin: '6px 0', paddingLeft: 16 }}>
        {f.signals.map((s) => (
          <li key={s.id}>{s.id} · {s.source}{s.at ? ' · ' + when(s.at) : ''}</li>
        ))}
      </ul>
      {can('approve') ? (
        <div className="fld">
          <label htmlFor="fraud-reason">Why release it or reject it? The reason stays on the record.</label>
          <textarea id="fraud-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="row" style={{ gap: 8 }}>
            <button className="btn sm pri" disabled={!ready || action.pending} onClick={() => decide('release')}>Release</button>
            <button className="btn sm" disabled={!ready || action.pending} onClick={() => decide('reject')}>Reject</button>
          </div>
        </div>
      ) : (
        <p className="note" style={{ margin: 0 }}>An Approver releases the hold or rejects the return.</p>
      )}
    </section>
  );
}
