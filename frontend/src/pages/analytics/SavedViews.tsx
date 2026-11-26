import { useId, useState } from 'react';
import { analyticsOrgs, saveView, savedViews, setViewAlert, shareView, type AlertOp, type SavedView } from '../../api/analytics';
import { roles } from '../../api/access';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { OPS, alertText, audienceText, measureLabel, parseThreshold, toggleRole, viewsOfPack } from './viewLogic';

/** "Save view": keep the chosen worked question as a view of an org unit (view.save). The list below shows it at once. */
export function SaveViewForm({ pack, questionId, question }: { pack: string; questionId: string; question: string }) {
  const uid = useId();
  const act = useAction();
  const orgs = analyticsOrgs();
  const [org, setOrg] = useState(orgs[0]?.id ?? '');
  const [name, setName] = useState(question);
  if (!can('saveView')) return null;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await act.run(() => saveView(org, pack, questionId, name.trim()), 4200);
    if (r.ok) toast(`Saved the view ${name.trim()}.`);
  };
  return (
    <form className="sv-form" onSubmit={save} aria-label="Save view" data-testid="save-view">
      <div className="fld">
        <label htmlFor={`${uid}-name`}>View name</label>
        <input id={`${uid}-name`} name="name" autoComplete="off" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="fld">
        <label htmlFor={`${uid}-org`}>Org unit</label>
        <select id={`${uid}-org`} className="sel" value={org} onChange={(e) => setOrg(e.target.value)}>
          {orgs.map((o) => <option key={o.id} value={o.id}>{`${' '.repeat(o.depth)}${o.name}`}</option>)}
        </select>
      </div>
      <button type="submit" className="btn pri" disabled={act.pending || !name.trim() || !org}>Save view</button>
    </form>
  );
}

function ShareControl({ v }: { v: SavedView }) {
  const act = useAction();
  const all = roles();
  const [picked, setPicked] = useState(v.shared_with_roles);
  const save = async () => {
    const r = await act.run(() => shareView(v.id, picked), 4200);
    if (r.ok) toast(picked.length ? `Shared ${v.name} with ${picked.join(', ')}.` : `${v.name} is no longer shared.`);
  };
  return (
    <fieldset className="sv-set">
      <legend>Share with role…</legend>
      <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
        {all.map((r) => (
          <label key={r} className="sv-check">
            <input type="checkbox" checked={picked.includes(r)} onChange={(e) => setPicked(toggleRole(picked, r, e.target.checked, all))} /> {r}
          </label>
        ))}
      </div>
      <button type="button" className="btn" disabled={act.pending} onClick={save}>Save sharing</button>
    </fieldset>
  );
}

function AlertControl({ v }: { v: SavedView }) {
  const uid = useId();
  const act = useAction();
  const [measure, setMeasure] = useState(v.alert?.measure ?? v.measures[0] ?? '');
  const [op, setOp] = useState<AlertOp>(v.alert?.op ?? '>');
  const [limit, setLimit] = useState(v.alert ? String(v.alert.threshold) : '');
  const threshold = parseThreshold(limit);
  const set = async (e: React.FormEvent) => {
    e.preventDefault();
    if (threshold === null) return;
    const r = await act.run(() => setViewAlert(v.id, { measure, op, threshold }), 4200);
    if (r.ok) toast(`Alert set on ${v.name}.`);
  };
  const clear = async () => {
    const r = await act.run(() => setViewAlert(v.id, null), 4200);
    if (r.ok) toast(`Alert removed from ${v.name}.`);
  };
  if (v.measures.length === 0) return <p className="note" style={{ margin: 0 }}>This question has no measure to alert on.</p>;
  return (
    <form onSubmit={set} aria-label={`Alert on ${v.name}`}>
      <fieldset className="sv-set">
        <legend>Alert when…</legend>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <div className="fld">
            <label htmlFor={`${uid}-m`}>Measure</label>
            <select id={`${uid}-m`} className="sel" value={measure} onChange={(e) => setMeasure(e.target.value)}>
              {v.measures.map((m) => <option key={m} value={m}>{measureLabel(m)}</option>)}
            </select>
          </div>
          <div className="fld">
            <label htmlFor={`${uid}-o`}>Condition</label>
            <select id={`${uid}-o`} className="sel" value={op} onChange={(e) => setOp(e.target.value as AlertOp)}>
              {OPS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
            </select>
          </div>
          <div className="fld">
            <label htmlFor={`${uid}-t`}>Threshold</label>
            <input id={`${uid}-t`} name="threshold" inputMode="decimal" autoComplete="off" value={limit} onChange={(e) => setLimit(e.target.value)} aria-invalid={limit !== '' && threshold === null} />
          </div>
          <button type="submit" className="btn pri" disabled={act.pending || threshold === null}>Set alert</button>
          {v.alert && <button type="button" className="btn" disabled={act.pending} onClick={clear}>Clear alert</button>}
        </div>
      </fieldset>
    </form>
  );
}

function ViewRow({ v }: { v: SavedView }) {
  return (
    <li className="sv-row" data-testid="saved-view" data-view={v.id}>
      <div className="row" style={{ justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <b>{v.name}</b>
        <span className="note">{audienceText(v)}</span>
      </div>
      <p className="note" style={{ margin: '4px 0' }}>
        {v.question}, {v.org_unit_id}. {alertText(v.alert)}{v.alert_active ? ': it has crossed, see My work' : ''}
      </p>
      {v.mine && (
        <div className="sv-controls">
          {can('saveView') && <ShareControl key={v.shared_with_roles.join()} v={v} />}
          {can('saveView') && <AlertControl key={JSON.stringify(v.alert)} v={v} />}
        </div>
      )}
    </li>
  );
}

/** The saved views of a pack that the account owns or that are shared with its role, each with its share and alert controls. */
export function SavedViewsList({ pack }: { pack: string }) {
  const mine = viewsOfPack(savedViews(), pack);
  return (
    <section aria-label="Saved views" data-testid="saved-views" style={{ marginTop: 16 }}>
      <h3 className="sv-h">Saved views</h3>
      {mine.length === 0
        ? <p className="note" style={{ margin: 0 }}>No saved view yet. Choose a question and save it.</p>
        : <ul className="sv-list">{mine.map((v) => <ViewRow key={v.id} v={v} />)}</ul>}
    </section>
  );
}
