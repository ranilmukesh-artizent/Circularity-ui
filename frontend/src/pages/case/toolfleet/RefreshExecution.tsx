import type { RefreshExecution as Execution } from '../../../api/refresh';

/**
 * What an approved contract refresh carried out (plan 9, P9-5.5, CR-05): the proposal sent, the contract lines drafted and the
 * units reserved, each with the reference its system returned ("Proposal sent PR-40201"). The server words every line; nothing
 * shows before a person approves. When a unit was taken meanwhile it shows where the decision went back to and why.
 */
export function RefreshExecution({ execution }: { execution: Execution | null }) {
  if (!execution) return null;
  return (
    <div data-testid="rf-execution">
      <p style={{ margin: '12px 0 4px' }}>
        Approved under {execution.approval}
        {execution.approver ? ` by ${execution.approver}` : ''}; the proposal is valid until {execution.valid_until}
      </p>
      <ol className="note" style={{ margin: '4px 0', paddingLeft: 18 }}>
        {execution.steps.map((s) => (
          <li key={s.kind} data-testid={`rf-step-${s.kind}`} data-state={s.state}>
            {s.text}
            {s.state !== 'done' && <span className="chip"> {s.state === 'active' ? 'in progress' : 'waiting'}</span>}
          </li>
        ))}
      </ol>
      {execution.back && (
        <p data-testid="rf-back">
          <span className="chip warn">Back to the {execution.back.to}</span> {execution.back.reason}
        </p>
      )}
    </div>
  );
}
