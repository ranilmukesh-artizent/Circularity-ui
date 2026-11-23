import { useState } from 'react';
import { refreshAccess } from '../../api/access';
import { createOrg, flatten, moveOrg, ORG_KINDS, useOrgTree, type OrgKind } from '../../api/orgs';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/**
 * Organisation (Admin, plan 8 MVP-1.5): the org tree that tenant access reads. A grant on a unit covers every unit
 * below it, so moving a unit changes who sees its cases.
 */
export function Orgs() {
  const rows = flatten(useOrgTree());
  const manage = can('manageOrgs');
  const action = useAction();
  const [parent, setParent] = useState(rows[0]?.node.id ?? 'workspace');
  const [kind, setKind] = useState<OrgKind>('company');
  const [name, setName] = useState('');
  const [err, setErr] = useState('');

  const create = async () => {
    const id = name.trim();
    const r = await action.run(() => createOrg({ id, parent_id: parent, kind, name: id }), { all: setErr });
    if (!r.ok) return;
    setErr('');
    setName('');
    toast(id + ' added under ' + parent + '.');
    void refreshAccess();
  };
  const move = async (id: string, to: string) => {
    const r = await action.run(() => moveOrg(id, to), 4200);
    if (!r.ok) return;
    toast(id + ' moved under ' + to + '. Grants on ' + to + ' now cover it.');
    void refreshAccess();
  };

  return (
    <section className="panel sect" id="axOrgs">
      <div className="ph">
        <h3>Organisation</h3>
        <span className="chip line">{rows.length} units</span>
      </div>
      <div className="pb">
        <div className="tw">
          <table className="t static tight">
            <thead>
              <tr><th>Unit</th><th>Kind</th><th>Parent</th></tr>
            </thead>
            <tbody>
              {rows.map(({ node, depth }) => (
                <tr key={node.id}>
                  <td style={{ paddingLeft: 10 + depth * 18 }}><b>{node.name}</b>{node.name !== node.id && <span className="note"> · {node.id}</span>}</td>
                  <td>{node.kind}</td>
                  <td>
                    {node.parent_id === null || !manage ? (
                      node.parent_id ?? '—'
                    ) : (
                      <>
                        <label className="sr" htmlFor={'org-mv-' + node.id}>Parent of {node.name}</label>
                        <select id={'org-mv-' + node.id} value={node.parent_id} disabled={action.pending} onChange={(e) => move(node.id, e.target.value)}>
                          {rows.filter((x) => x.node.id !== node.id).map((x) => (
                            <option key={x.node.id} value={x.node.id}>{' '.repeat(x.depth * 2) + x.node.name}</option>
                          ))}
                        </select>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {manage && (
          <div className="axrl" style={{ marginTop: 10 }}>
            <label htmlFor="org-parent">Parent</label>
            <select id="org-parent" value={parent} onChange={(e) => setParent(e.target.value)}>
              {rows.map((x) => <option key={x.node.id} value={x.node.id}>{' '.repeat(x.depth * 2) + x.node.name}</option>)}
            </select>
            <label htmlFor="org-kind">Kind</label>
            <select id="org-kind" value={kind} onChange={(e) => setKind(e.target.value as OrgKind)}>
              {ORG_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <label htmlFor="org-name">Name</label>
            <input id="org-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. East region" style={{ width: 200 }} />
            <button className="btn sm" disabled={action.pending || !name.trim()} onClick={create}>Add unit</button>
          </div>
        )}
        {err && <div className="note err">{err}</div>}
        <div className="note" style={{ paddingTop: 8 }}>
          A tenant grant on a unit covers every unit below it. Cases belong to a customer or company unit.
        </div>
      </div>
    </section>
  );
}
