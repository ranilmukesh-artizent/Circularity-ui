import { useState } from 'react';
import { refreshAccess } from '../../../api/access';
import { renameOrg } from '../../../api/orgs';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';

/** Rename an org unit in place (org.update, manageOrgs). Its id stays: grants and cases keep pointing at it. */
export function RenameOrg({ id, name, onDone }: { id: string; name: string; onDone: () => void }) {
  const action = useAction();
  const [value, setValue] = useState(name);
  const [err, setErr] = useState('');
  const save = async () => {
    const next = value.trim();
    const r = await action.run(() => renameOrg(id, next), { all: setErr });
    if (!r.ok) return;
    toast(name + ' is now called ' + next + '.');
    void refreshAccess();
    onDone();
  };
  return (
    <span className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
      <label className="sr" htmlFor={'org-rn-' + id}>New name of {name}</label>
      <input id={'org-rn-' + id} value={value} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && value.trim()) void save(); if (e.key === 'Escape') onDone(); }} style={{ width: 180 }} />
      <button className="btn sm pri" disabled={action.pending || !value.trim() || value.trim() === name} onClick={() => void save()}>Save</button>
      <button className="btn sm" onClick={onDone}>Cancel</button>
      {err && <span className="note err">{err}</span>}
    </span>
  );
}
