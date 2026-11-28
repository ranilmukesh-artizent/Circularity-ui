import type { Composition } from '../../api/compose';
import { accounts, canPage, currentAccount, rolePolicy } from '../../api/session';
import { makers } from '../modeler/compose/composeView';
import { orgName } from './setupView';

/** What a role does in a setup. For display only: the server decides (di.core.policy EXTRA_PERMS managePacks, approve.packs,
 *  manageFlows, approve.flows, manageIntegrations) and refuses every call that does not hold the permission. */
const PART: Record<string, string> = {
  Admin: 'Makes or approves a setup, never both for the same one',
  Planner: 'Makes a setup and shapes the flow',
  Approver: 'Approves and publishes',
  Developer: 'Connects systems and maps their data',
  Engineer: 'Works the cases it routes',
  Finance: 'Reads the outcome and the figures',
  Executive: 'Reads the outcome and the figures',
  'Warehouse Manager': 'Receives and moves the items',
};

/**
 * The access stop of Set up: who can reach this organisation and what each does in a setup, so the maker sees before sending
 * it on that a different person is there to approve. It changes nothing: accounts, tenant access and delegations are changed
 * in Access & Governance, with their own approvals. A composition holds no access settings of its own.
 */
export function AccessStep({ c }: { c: Composition }) {
  const org = c.org_unit_id;
  const people = accounts().filter((a) => !a.tenant || a.tenant === org);
  const made = makers(c);
  const me = currentAccount()?.id;
  const approvers = people.filter((a) => (a.role === 'Approver' || a.role === 'Admin') && !made.includes(a.id));
  return (
    <div className="sup-access">
      <p className={'sup-access-check' + (approvers.length ? '' : ' bad')} role="status">
        {approvers.length
          ? `${approvers.length === 1 ? '1 person' : `${approvers.length} people`} can approve this setup: ${approvers.map((a) => a.label).join(', ')}.`
          : 'Nobody else can approve this setup yet. An Approver or a second Admin needs access to this organisation.'}
        {made.includes(me ?? '') && ' You made it, so you cannot approve it yourself.'}
      </p>
      <table className="t static sup-people" aria-label={'People who reach ' + orgName(org)}>
        <thead><tr><th>Person</th><th>Role</th><th>In a setup</th><th>Reach</th></tr></thead>
        <tbody>
          {people.map((a) => (
            <tr key={a.id}>
              <td><b>{a.label}</b>{made.includes(a.id) && <span className="note"> · made this setup</span>}</td>
              <td>{a.role}<div className="note">{rolePolicy(a.role)?.desc}</div></td>
              <td>{PART[a.role] ?? 'Reads'}</td>
              <td className="note">{a.tenant ? orgName(a.tenant) + ' only' : 'Every organisation'}{a.warehouse ? `, ${a.warehouse}` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="sup-access-links">
        {canPage('access', 'accounts') && <li><a className="lnk" href="#/access/accounts">Change who has an account and a role</a></li>}
        {canPage('access', 'requests') && <li><a className="lnk" href="#/access/requests">Give or end access to a customer</a></li>}
        {canPage('access', 'delegations') && <li><a className="lnk" href="#/access/delegations">Set who stands in when an approver is away</a></li>}
        {canPage('access', 'autonomy') && <li><a className="lnk" href="#/access/autonomy">Set what agents may do without a person</a></li>}
      </ul>
    </div>
  );
}
