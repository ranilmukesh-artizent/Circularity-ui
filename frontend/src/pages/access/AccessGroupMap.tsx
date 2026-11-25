import { useState } from 'react';
import { approveGroupMap, groupMap, idpRoles, saveGroupMap, refreshAccess, type GroupMapRow } from '../../api/access';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/** The scope a mapping gives: the organisation, site and warehouse, as one line. */
export const scopeText = (r: Pick<GroupMapRow, 'org_unit_id' | 'site' | 'warehouse'>): string =>
  [r.org_unit_id, r.site, r.warehouse].filter(Boolean).join(' · ') || 'All';

/** "from 2026-01-01 to 2026-12-31", "from 2026-01-01", "until 2026-12-31" or "No dates". */
export const datesText = (r: Pick<GroupMapRow, 'valid_from' | 'valid_to'>): string =>
  r.valid_from && r.valid_to ? `${r.valid_from} to ${r.valid_to}` : r.valid_from ? 'from ' + r.valid_from : r.valid_to ? 'until ' + r.valid_to : 'No dates';

/**
 * Directory group to role mapping as data (P9-8.10): each row, its status, who changed it and who approved it, with
 * "Add mapping". A change is a draft until another person approves it. Display only: the server enforces maker-checker.
 */
export function GroupMap() {
  const rows = groupMap();
  const manage = can('manageIdentity');
  const approve = can('approve.tenantAccess');
  const action = useAction();
  const [group, setGroup] = useState('');
  const [role, setRole] = useState(idpRoles()[0] ?? '');
  const [org, setOrg] = useState('');
  const [site, setSite] = useState('');
  const [from, setFrom] = useState('');
  const [until, setUntil] = useState('');

  const add = async () => {
    const r = await action.run(() => saveGroupMap({
      group_id: group.trim(), role, ...(org && { org_unit_id: org.trim() }), ...(site && { site: site.trim() }),
      ...(from && { valid_from: from }), ...(until && { valid_to: until }),
    }), 4200);
    if (!r.ok) return;
    toast('Mapping drafted. Another person approves it before it takes effect.');
    setGroup('');
    void refreshAccess();
  };
  const decide = async (id: number) => {
    const r = await action.run(() => approveGroupMap(id), 4200);
    if (!r.ok) return;
    toast('Mapping approved. It applies at the next sign-in.');
    void refreshAccess();
  };

  return (
    <>
      <h4 style={{ margin: '14px 0 6px' }}>Group mappings</h4>
      <div className="tw">
        <table className="t static tight" id="idpGroupMap">
          <thead>
            <tr><th>Group</th><th>Role</th><th>Scope</th><th>Valid</th><th>Status</th><th>Changed by</th><th>Approved by</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.group_id}</td>
                <td>{r.role}</td>
                <td>{scopeText(r)}</td>
                <td className="note">{datesText(r)}</td>
                <td><span className={'chip ' + (r.status === 'approved' ? 'ok' : 'line')}>{r.status}</span></td>
                <td className="note">{r.created_by}</td>
                <td className="note">{r.approved_by ?? '—'}</td>
                <td>{approve && r.status === 'draft' && <button className="btn sm" disabled={action.pending} onClick={() => void decide(r.id)}>Approve</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {manage && (
        <div className="grid g3" style={{ gap: '0 12px', marginTop: 8 }}>
          <div className="fld"><label htmlFor="gm-group">Directory group</label><input id="gm-group" value={group} onChange={(e) => setGroup(e.target.value)} /></div>
          <div className="fld">
            <label htmlFor="gm-role">Role</label>
            <select id="gm-role" value={role} onChange={(e) => setRole(e.target.value)}>{idpRoles().map((r) => <option key={r}>{r}</option>)}</select>
          </div>
          <div className="fld"><label htmlFor="gm-org">Organisation</label><input id="gm-org" value={org} onChange={(e) => setOrg(e.target.value)} /></div>
          <div className="fld"><label htmlFor="gm-site">Site or warehouse</label><input id="gm-site" value={site} onChange={(e) => setSite(e.target.value)} /></div>
          <div className="fld"><label htmlFor="gm-from">Valid from</label><input id="gm-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
          <div className="fld"><label htmlFor="gm-until">Valid until</label><input id="gm-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></div>
        </div>
      )}
      {manage && <button className="btn sm" disabled={action.pending || !group.trim()} onClick={() => void add()}>Add mapping</button>}
    </>
  );
}
