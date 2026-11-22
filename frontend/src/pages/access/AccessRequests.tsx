import { useState } from 'react';
import { invoke } from '../../api/actions';
import { canDecide, REQ_KIND, refreshAccess, type AccessRequest } from '../../api/access';
import { fmtDateYear } from '../../api/format';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/** Status chip (the demo's reqStChip). */
function StatusChip({ r }: { r: AccessRequest }) {
  if (r.status === 'pending') return <span className="chip warn">Pending review</span>;
  if (r.status === 'approved') return <span className="chip ok">Approved</span>;
  return <span className="chip bad">Declined</span>;
}

/** What is asked for (the demo's reqSummary). */
export function ReqSummary({ r }: { r: AccessRequest }) {
  if (r.kind === 'tenant')
    return (
      <>
        <b>Access to {r.tenant}</b>
        <div className="note">{r.reason}</div>
      </>
    );
  const v = r.server!;
  return (
    <>
      <b>{v.name}</b> <span className={'chip ' + (v.access === 'write' ? 'dk' : 'ok')}>{v.access === 'write' ? 'Read and write' : 'Read only'}</span>
      <div className="note">{v.owner} · {v.purpose}</div>
      <div className="note">
        Tools: <span className="mono">{v.tools.join(', ')}</span> · Data: {v.data}
      </div>
    </>
  );
}

type Decision = 'approve' | 'decline';

/** One request row with Approve / Decline when the signed-in account may decide it (the demo's reqRowHTML). */
export function ReqRow({ r, onDecide }: { r: AccessRequest; onDecide: (r: AccessRequest, d: Decision) => void }) {
  return (
    <div className="rqrow" data-req={r.id}>
      <div className="rqm">
        <div className="row" style={{ gap: 6 }}>
          <span className="chip line">{REQ_KIND[r.kind]}</span>
          <StatusChip r={r} />
          <span className="note num">{r.id}</span>
        </div>
        <div style={{ marginTop: 6 }}>
          <ReqSummary r={r} />
        </div>
        <div className="note" style={{ marginTop: 4 }}>
          Requested by {r.by} · {fmtDateYear(r.at)}
          {r.decidedBy && ` · ${r.status === 'approved' ? 'approved' : 'declined'} by ${r.decidedBy} on ${fmtDateYear(r.decidedAt!)}${r.note ? ': ' + r.note : ''}`}
        </div>
      </div>
      {canDecide(r) && (
        <div className="rqa">
          <button className="btn sm pri" onClick={() => onDecide(r, 'approve')}>
            {r.kind === 'tenant' ? 'Approve access' : 'Approve proposal'}
          </button>
          <button className="btn sm" onClick={() => onDecide(r, 'decline')}>
            Decline
          </button>
        </div>
      )}
    </div>
  );
}

/** Approve or decline dialog (the demo's reqDecide / reqDecideOk), through access.decideRequest. */
function DecideModal({ r, dec, onClose }: { r: AccessRequest; dec: Decision; onClose: () => void }) {
  const [note, setNote] = useState('');
  const action = useAction();
  const [err, setErr] = useState('');
  async function ok() {
    if (!canDecide(r)) {
      toast('This request is not yours to decide.');
      return onClose();
    }
    const res = await action.run(() => invoke<{ id: string; status: string }>('access.decideRequest', { id: r.id, decision: dec, note: note.trim() }), { ms: 4200, inline: setErr });
    if (!res.ok) {
      if (res.error.code !== 'validation_error') onClose();
      return;
    }
    onClose();
    void refreshAccess();
    toast(r.id + ' ' + res.output.status + '.' + (r.kind === 'tenant' && res.output.status === 'approved' ? ' ' + r.by + ' can now open ' + r.tenant + '.' : ''), 4200);
  }
  return (
    <Modal
      title={(dec === 'approve' ? 'Approve ' : 'Decline ') + REQ_KIND[r.kind].toLowerCase() + ' ' + r.id}
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className={'btn ' + (dec === 'approve' ? 'pri' : 'danger')} onClick={ok}>
            {dec === 'approve' ? 'Approve' : 'Decline'}
          </button>
        </>
      }
    >
      <div className="callout info" style={{ marginBottom: 12 }}>
        <ReqSummary r={r} />
        <div className="note" style={{ marginTop: 6 }}>Requested by {r.by} on {fmtDateYear(r.at)}</div>
      </div>
      <div className="fld">
        <label htmlFor="rq-note">
          Note <span className="muted">{dec === 'decline' ? '(required)' : '(optional)'}</span>
        </label>
        <textarea
          id="rq-note"
          maxLength={300}
          placeholder={dec === 'decline' ? 'Say what would change your decision.' : 'Anything the requester should know.'}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="hint">Recorded in the audit log. Do not enter personal data.</div>
        {err && <div className="err">{err}</div>}
      </div>
      {r.kind === 'tenant' && dec === 'approve' && (
        <p className="note" style={{ margin: 0 }}>{r.by} will see {r.tenant} cases for the rest of this session.</p>
      )}
      {r.kind === 'mcp' && dec === 'approve' && (
        <p className="note" style={{ margin: 0 }}>The server joins the MCP client list as approved. Connecting it is a separate step.</p>
      )}
    </Modal>
  );
}

/** A list of requests with its empty state and the decide dialog (the demo's reqListHTML). */
export function ReqList({ list, empty }: { list: AccessRequest[]; empty: [string, string] }) {
  const [deciding, setDeciding] = useState<{ r: AccessRequest; dec: Decision } | null>(null);
  return (
    <>
      {list.length ? (
        list.map((r) => <ReqRow key={r.id} r={r} onDecide={(r, dec) => setDeciding({ r, dec })} />)
      ) : (
        <div className="empty">
          <b>{empty[0]}</b>
          {empty[1]}
        </div>
      )}
      {deciding && <DecideModal r={deciding.r} dec={deciding.dec} onClose={() => setDeciding(null)} />}
    </>
  );
}
