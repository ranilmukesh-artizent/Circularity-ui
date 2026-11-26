import type { FollowThroughView } from '../../../api/toolFleet';
import { money } from '../../../api/format';

/** What a step reads after the approval: the system's reference once it acknowledged, else what it waits for or the error. */
function stepText(s: FollowThroughView['steps'][number]): string {
  if (s.ack) return `acknowledged ${s.ack.ref}${s.ack.sim ? ' (simulated)' : ''}`;
  if (s.error) return `failed: ${s.error}`;
  if (s.waiting) return `waiting for ${s.waiting}`;
  if (s.status === 'sent') return 'sent, waiting for the system';
  return s.state === 'active' ? 'queued' : s.state === 'done' ? 'done' : 'to do';
}

/** The tool fleet's follow-through (plan 9, P9-3.17, TF-10): each step of the approved plan with the system that carries it out and its acknowledgement, then realised against predicted once Finance confirmed the outcome. The server words nothing here; it reads the instruction rows and the outcome. */
export function FollowThroughSection({ followThrough }: { followThrough: FollowThroughView | null | undefined }) {
  if (!followThrough) return null;
  const { steps, outcome } = followThrough;
  return (
    <div style={{ margin: '8px 0 0' }} data-testid="tf-follow-through">
      <b>Follow-through</b> <span className="muted">{followThrough.ref}</span>
      <ol style={{ margin: '4px 0 0', paddingLeft: 18 }}>
        {steps.map((s) => (
          <li key={s.k} data-testid={`tf-ft-${s.k}`}>
            {s.label} <span className="muted">· {s.system}</span> <span className={`chip ${s.ack ? 'ok' : s.error ? 'bad' : 'warn'}`}>{stepText(s)}</span>
          </li>
        ))}
      </ol>
      {outcome && (
        <div style={{ marginTop: 4 }} data-testid="tf-ft-outcome">
          Realised {money(outcome.actual)} against predicted {money(outcome.predicted)} ({outcome.variance < 0 ? '−' : '+'}
          {money(Math.abs(outcome.variance))}, tolerance {money(outcome.tolerance)}){' '}
          {outcome.flagged ? <span className="chip warn">{outcome.task ? 'Finance is checking the variance' : 'Variance checked'}</span> : <span className="chip ok">Within tolerance</span>}
        </div>
      )}
    </div>
  );
}
