import { useState } from 'react';
import { approvePack, importPack, rejectPack, submitPack } from '../../api/modeler';
import type { ActionResult, ModelerScreen, PackVersion } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { Field } from './Field';
import { impactLine, packTitle, partsLine, refusalLine, STATUS_LABEL } from './packs';

const MIN_REASON = 15;
const EVERY_ORG = '';

/**
 * Packs (plan 9, P9-1.6, stories X-01 and X-03): every pack's versions with their status, who imported them, the parts
 * check and the impact of publishing on the open and sample decisions. "Import a pack" takes a JSON file as a draft; a
 * person with `managePacks` submits it, a different person with `approve.packs` approves or returns it (maker-checker).
 * A published version decides the org's cases from the next decision; the template list below shows what a case can use.
 */
export function PacksPanel({ s }: { s: ModelerScreen }) {
  const p = s.packs;
  const action = useAction();
  const [err, setErr] = useState('');
  const [scope, setScope] = useState(s.org);
  const [returning, setReturning] = useState<number | null>(null);
  const [reason, setReason] = useState('');

  const go = async (call: () => Promise<ActionResult<{ log?: string }>>) => {
    setErr('');
    const r = await action.run(call, { inline: (m) => setErr(refusalLine(m)), ms: 4200 });
    if (r.ok && r.output.log) toast(r.output.log + '.');
    return r.ok;
  };
  const pick = async (file: File | undefined) => {
    if (!file) return;
    let doc: unknown;
    try {
      doc = JSON.parse(await file.text());
    } catch {
      setErr(`${file.name} is not a JSON file.`);
      return;
    }
    await go(() => importPack(doc, scope === EVERY_ORG ? undefined : scope));
  };
  const giveBack = async (id: number) => {
    if (await go(() => rejectPack(id, reason.trim()))) {
      setReturning(null);
      setReason('');
    }
  };

  return (
    <Panel title="Packs" sub="Versions of each pack: import, check, approve" cls="mdl-packs">
      {p.can.import && (
        <div className="mdl-form mdl-packs-import" data-pack-import>
          <Field id="mdl-pk-scope" label="Import for" hint="The org the imported draft belongs to.">
            <select id="mdl-pk-scope" value={scope} onChange={(e) => setScope(e.target.value)}>
              {s.orgs.map((o) => <option key={o} value={o}>{o}</option>)}
              <option value={EVERY_ORG}>Every org (Admin)</option>
            </select>
          </Field>
          <div className="mdl-form-go">
            <label className={'btn sm pri' + (action.pending ? ' off' : '')} htmlFor="mdl-pk-file" aria-disabled={action.pending}>Import a pack (JSON)</label>
            <input id="mdl-pk-file" type="file" accept="application/json,.json" className="sr" disabled={action.pending}
                   onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ''; }} />
          </div>
        </div>
      )}
      {err && <p className="mdl-msg blk" role="alert" data-pack-refusal>{err}</p>}
      {p.keys.map((k) => (
        <div key={k.key} className="mdl-pack" data-pack-key={k.key}>
          <h4>{packTitle(k)} <span className="note">{k.file_version ? `file v${k.file_version}` : ''}{k.versions.length === 0 ? `${k.file_version ? ' · ' : ''}no imported versions, the pack file decides` : ''}</span></h4>
          {k.versions.length > 0 && <ul className="mdl-hist">
            {k.versions.map((v) => (
              <li key={v.id} data-pack-version={v.id}>
                <b>v{v.version}</b> <span className={'pill mdl-st ' + (v.status === 'retired' ? 'draft' : v.status)}>{STATUS_LABEL[v.status]}</span>{' '}
                <span className="note">
                  · {v.org_unit_id ?? 'every org'} · imported by {v.maker ?? '—'} · {partsLine(v)} · {impactLine(v.impact)}
                  {v.note ? ` · ${v.note}` : ''}
                </span>{' '}
                <Actions v={v} can={p.can} busy={action.pending} returning={returning === v.id}
                         onSubmit={() => go(() => submitPack(v.id))} onApprove={() => go(() => approvePack(v.id))} onReturn={() => setReturning(v.id)} />
                {returning === v.id && (
                  <span className="mdl-row">
                    <label className="sr" htmlFor="mdl-pk-reason">Reason</label>
                    <input id="mdl-pk-reason" value={reason} placeholder="Why it goes back (15 characters or more)" style={{ width: 280 }} onChange={(e) => setReason(e.target.value)} />
                    <button className="btn sm" disabled={action.pending || reason.trim().length < MIN_REASON} onClick={() => giveBack(v.id)}>Return</button>
                    <button className="btn sm ghost" onClick={() => setReturning(null)}>Cancel</button>
                  </span>
                )}
              </li>
            ))}
          </ul>}
        </div>
      ))}
      <h4>Templates a case can use</h4>
      <p className="note" data-pack-templates>{p.templates.map((t) => t.name).join(' · ')}</p>
    </Panel>
  ); // prettier-ignore
}

interface ActionsProps {
  v: PackVersion;
  can: ModelerScreen['packs']['can'];
  busy: boolean;
  returning: boolean;
  onSubmit: () => void;
  onApprove: () => void;
  onReturn: () => void;
}

function Actions({ v, can, busy, returning, onSubmit, onApprove, onReturn }: ActionsProps) {
  return (
    <>
      {can.import && v.status === 'draft' && <button className="btn sm pri" disabled={busy} onClick={onSubmit}>Submit for approval</button>}
      {can.approve && v.status === 'review' && <button className="btn sm pri" disabled={busy} onClick={onApprove}>Approve</button>}
      {can.approve && v.status === 'review' && !returning && <button className="btn sm" onClick={onReturn}>Return to draft</button>}
    </>
  );
}
