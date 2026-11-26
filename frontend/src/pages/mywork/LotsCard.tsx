import { useCallback, useEffect, useState } from 'react';
import { approveLot, buildLots, listLots, proposeLot, rejectLot, type LotList, type LotView } from '../../api/device';
import { allowedTenants } from '../../api/session';
import type { ActionResult } from '../../api/types';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { canApprove, droppedLine, lotLine, waitLine } from './lots';

/** Wholesale lots (plan 9, P9-6.11, story DV-07): the lots of received devices that are collecting bids or wait for a decision, each
 *  with its best approved bid, the bids dropped because their buyer is not approved, and who it waits for. Build, Propose and
 *  Approve or Reject are the person's; the server checks maker-checker, the approval limit and the tenant again. An agent never approves. */
export function LotsCard() {
  const [list, setList] = useState<LotList | null>(null);
  const [org, setOrg] = useState(() => allowedTenants()[0] ?? '');
  const [rejecting, setRejecting] = useState<LotView | null>(null);
  const action = useAction();
  const reload = useCallback(async () => {
    const r = await listLots();
    if (r.ok) setList(r.output);
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  if (!list) return null;
  const run = async <R extends ActionResult<unknown>>(call: () => Promise<R>, done: string) => {
    const r = await action.run(call);
    if (r.ok) toast(done);
    await reload();
  };
  const open = list.lots.filter((l) => l.status !== 'rejected' && l.status !== 'sold');
  if (!open.length && !list.can.build) return null;
  return (
    <section aria-label="Wholesale lots" data-testid="lots-card" style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Wholesale lots</h2>
        {list.can.build && (
          <>
            <select aria-label="Org unit to build lots for" value={org} onChange={(e) => setOrg(e.target.value)}>
              {allowedTenants().map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button className="btn sm pri" disabled={action.pending || !org} onClick={() => run(() => buildLots(org), 'Lots built.')}>Build lots</button>
          </>
        )}
      </div>
      {!open.length && <p className="note">No wholesale lot is open. Build lots from the devices routed to wholesale.</p>}
      <ul className="frbl" aria-label="Wholesale lots">
        {open.map((l) => {
          const blocked = canApprove(l, list.me);
          return (
            <li key={l.id} data-id={l.id} data-status={l.status}>
              <span>
                <span className="chip line" style={{ marginRight: 6 }}>{l.status}</span>
                <b>{lotLine(l)}</b>
                <span className="note">{l.lot_ref} · {l.bids_received} bids received</span>
                {l.dropped.map((d) => <span key={d.bid_id} className="note">Dropped {droppedLine(d)}</span>)}
                {waitLine(l) && <span className="note">{waitLine(l)}</span>}
                <span className="row">
                  {list.can.build && l.status === 'bidding' && (
                    <button className="btn sm pri" disabled={action.pending || !l.best_bid} title={l.best_bid ? undefined : 'No approved bid yet'} onClick={() => run(() => proposeLot(l.id), 'Lot proposed.')}>Propose</button>
                  )}
                  {list.can.approve && l.status === 'proposed' && (
                    <>
                      <button className="btn sm pri" disabled={action.pending || !!blocked} title={blocked ?? undefined} onClick={() => run(() => approveLot(l.id), 'Lot approved.')}>Approve</button>
                      <button className="btn sm" disabled={action.pending} onClick={() => setRejecting(l)}>Reject</button>
                    </>
                  )}
                </span>
                {l.status === 'proposed' && blocked && list.can.approve && <span className="note">{blocked}</span>}
              </span>
            </li>
          );
        })}
      </ul>
      {rejecting && (
        <RejectDialog
          lot={rejecting}
          onClose={() => setRejecting(null)}
          onReject={async (reason, inline) => {
            const r = await action.run(() => rejectLot(rejecting.id, reason), { inline });
            if (!r.ok) return;
            toast('Lot rejected.');
            setRejecting(null);
            await reload();
          }}
        />
      )}
    </section>
  );
}

function RejectDialog({ lot, onClose, onReject }: { lot: LotView; onClose: () => void; onReject: (reason: string, inline: (m: string) => void) => Promise<void> }) {
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  return (
    <Modal
      title={'Reject ' + lot.lot_ref}
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" disabled={reason.trim().length < 10} onClick={() => onReject(reason.trim(), setErr)}>Reject</button>
        </>
      }
    >
      <div className="fld">
        <label htmlFor="lot-reason">Why is the lot sent back? It stays on record.</label>
        <textarea id="lot-reason" maxLength={300} value={reason} onChange={(e) => { setReason(e.target.value); setErr(''); }} />
        <div className="err" role="alert" hidden={!err}>{err}</div>
      </div>
    </Modal>
  );
}
