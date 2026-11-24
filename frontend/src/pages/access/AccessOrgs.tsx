import { useState } from 'react';
import { refreshAccess } from '../../api/access';
import { createOrg, flatten, moveOrg, ORG_KINDS, setPilot, useOrgTree, useOrgUnits, type OrgKind, type OrgUnitRow } from '../../api/orgs';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { ExportPackButton, ImportPackDialog } from './orgs/OrgPack';
import { PILOT_TEXT, PilotReportDialog } from './orgs/PilotReport';
import { RenameOrg } from './orgs/RenameOrg';

type Open = { kind: 'import' | 'report'; unit: string; name: string };

/**
 * Organisation (Admin, plan 8 MVP-1.5): the org tree that tenant access reads. A grant on a unit covers every unit
 * below it, so moving a unit changes who sees its cases. Per unit (plan 8 UI gaps), for accounts with manageOrgs:
 * rename (org.update), export and import a configuration pack (org.exportPack, org.previewPack, org.importPack) and
 * pilot mode (org.setPilot); the pilot report for manageOrgs or approve.flows. The server enforces each permission.
 */
export function Orgs() {
  const rows = flatten(useOrgTree());
  const units = useOrgUnits();
  const manage = can('manageOrgs');
  const report = units.can.report;
  const pilotCol = manage || report;
  const pilotOf = new Map(units.units.map((u) => [u.id, u]));
  const [renaming, setRenaming] = useState<string | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
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
              <tr><th>Unit</th><th>Kind</th><th>Parent</th>{pilotCol && <th>Pilot mode</th>}{(manage || report) && <th>Actions</th>}</tr>
            </thead>
            <tbody>
              {rows.map(({ node, depth }) => (
                <tr key={node.id}>
                  <td style={{ paddingLeft: 10 + depth * 18 }}>
                    {renaming === node.id ? (
                      <RenameOrg id={node.id} name={node.name} onDone={() => setRenaming(null)} />
                    ) : (
                      <><b>{node.name}</b>{node.name !== node.id && <span className="note"> · {node.id}</span>}</>
                    )}
                  </td>
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
                  {pilotCol && <td><PilotCell unit={node.id} name={node.name} row={pilotOf.get(node.id)} manage={manage} /></td>}
                  {(manage || report) && (
                    <td>
                      <span className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                        {manage && renaming !== node.id && <button className="btn sm" onClick={() => setRenaming(node.id)}>Rename</button>}
                        {manage && <ExportPackButton unit={node.id} name={node.name} />}
                        {manage && <button className="btn sm" onClick={() => setOpen({ kind: 'import', unit: node.id, name: node.name })}>Import pack</button>}
                        {report && <button className="btn sm" onClick={() => setOpen({ kind: 'report', unit: node.id, name: node.name })}>Pilot report</button>}
                      </span>
                    </td>
                  )}
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
        {pilotCol && <div className="note" id="orgPilotNote" style={{ paddingTop: 4 }}>{PILOT_TEXT}</div>}
        {manage && (
          <div className="note" style={{ paddingTop: 4 }}>
            A configuration pack holds a unit&rsquo;s source settings, field mappings, workflows and decision flows. It never holds passwords, keys or tokens.
          </div>
        )}
      </div>
      {open?.kind === 'import' && <ImportPackDialog unit={open.unit} name={open.name} onClose={() => setOpen(null)} />}
      {open?.kind === 'report' && <PilotReportDialog unit={open.unit} name={open.name} onClose={() => setOpen(null)} />}
    </section>
  );
}

/** Pilot mode of a unit: a switch for accounts that manage orgs (org.setPilot), else its state. A unit under a pilot
 *  unit is in pilot mode through it; switch it at that unit. */
function PilotCell({ unit, name, row, manage }: { unit: string; name: string; row?: OrgUnitRow; manage: boolean }) {
  const action = useAction();
  if (!row) return <span className="note">—</span>;
  const inherited = row.pilot && row.pilot_via !== unit;
  if (inherited) return <span className="note">On, through {row.pilot_via}</span>;
  if (!manage) return <span>{row.pilot ? 'On' : 'Off'}</span>;
  const flip = async (on: boolean) => {
    const r = await action.run(() => setPilot(unit, on), 4200);
    if (!r.ok) return;
    toast(on ? name + ' is in pilot mode. Its instructions are held, not sent.' : name + ' left pilot mode. Its instructions are sent again.', 4200);
  };
  return (
    <label className="tog">
      <input type="checkbox" checked={!!row.pilot} disabled={action.pending} onChange={(e) => void flip(e.target.checked)} aria-label={'Pilot mode for ' + name} /> {row.pilot ? 'On' : 'Off'}
    </label>
  );
}
