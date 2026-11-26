import type { ApprovalView } from '../../../api/toolFleet';

const KEY_ACCOUNT_HOLD = 'TF-KEY'; // the pack's key-account hold (P9-3.16, TF-12): its reason names the customer

/** Who approves a tool return (plan 9, P9-3.15, TF-09): "Approved by policy SP-1 v1 (owner admin)" or "Waits for the Fleet manager: Repair $702 is over $600 (GR-14)". The server words it; the holds list the other reasons. */
export function ApprovalSection({ approval }: { approval: ApprovalView | null }) {
  if (!approval) return null;
  const policy = approval.kind === 'policy';
  return (
    <div style={{ margin: '8px 0 0' }} data-testid="tf-approval">
      <span className={`chip ${policy ? 'ok' : 'warn'}`}>{policy ? 'Policy' : 'Person'}</span> <span data-testid="tf-approval-text">{approval.text}</span>
      {!policy && approval.holds.some((h) => h.id === KEY_ACCOUNT_HOLD) && (
        <span className="chip warn" style={{ marginLeft: 6 }} data-testid="tf-approval-key">Key account: account manager review</span>
      )}
      {approval.holds.length > 1 && (
        <ul style={{ margin: '4px 0 0', paddingLeft: 18 }} data-testid="tf-approval-holds">
          {approval.holds.slice(1).map((h) => (
            <li key={h.id}>{h.reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
