/** The Device tab of a received-device case (P9-6.4, DV-01): IMEI, model and storage, grade and quote, partner, batch, received
 * date and, for a bulk lot, the device lines. Starts stage 5 of a device case (tabs/index.tsx). */
import { useState } from 'react';
import { decidePayout, deviceView } from '../../../api/device';
import { fmtDateYear } from '../../../api/format';
import { can } from '../../../api/session';
import { useAction } from '../../../hooks/useAction';
import { Kv } from '../CaseBlocks';
import { channelRow, deviceLine, gradeLine, lotLines, mismatchLine, payoutLine, payoutState, quoteCheckLine, refLine, registryLine, registryState, usd, wipeState } from '../device';
import type { TabProps } from './index';

const LABEL = { imei: 'IMEI', model: 'Model', storage: 'Storage' } as const;
const shown = (field: keyof typeof LABEL, v: string | number | null) => (v == null ? 'Not read yet' : field === 'storage' ? `${v} GB` : String(v));

/** The Quote tab of a received-device case (P9-6.5, DV-02): the quoted and the read IMEI, model and storage side by side, a
 * mismatch row in red with the exception's owner and state. Only a person resolves the exception (My work). */
export function QuoteTab({ c }: TabProps) {
  const q = deviceView(c)?.quoteCheck;
  if (!q) return null;
  return (
    <>
      <p className="stpad" role="status">{quoteCheckLine(q)}</p>
      <table className="stpad" aria-label="Quote against the device read">
        <thead><tr><th>Field</th><th>Quoted</th><th>Read</th></tr></thead>
        <tbody>
          {q.rows.map((r) => (
            <tr key={r.field} style={r.mismatch ? { color: 'var(--bad)', background: 'var(--bad-soft)' } : undefined} title={r.mismatch ? mismatchLine(r) : undefined}>
              <td>{LABEL[r.field]}</td><td>{shown(r.field, r.quoted)}</td><td>{shown(r.field, r.read)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function DeviceTab({ c }: TabProps) {
  const v = deviceView(c);
  if (!v) return null;
  const rows: [string, string][] = [
    [v.bulk ? 'Lot' : 'Device', deviceLine(v)],
    ['IMEI', v.imei ?? 'None (a bulk lot)'],
    ['Model', v.model + (v.storageGb != null ? ` · ${v.storageGb} GB` : '')],
    ['Grade', gradeLine(v) + (v.declaredGrade !== v.grade ? ` · declared ${v.declaredGrade}` : '')],
    ['Reference', refLine(v)],
    ['Partner', v.partner],
    ['Batch', v.batch ?? 'None'],
    ['Received', fmtDateYear(v.received)],
  ];
  const lines = lotLines(v);
  return (
    <>
      <Kv rows={rows} />
      {lines.length > 0 && (
        <ul className="stsys stpad" aria-label="Device lines">{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      )}
    </>
  );
}

/** The Compliance tab of a received-device case (P9-6.6, DV-03): the registry's status, check date and source; on a hit the
 * exception's owner and state ("Waiting for Compliance") and the routes the device may still take. Only a person releases a
 * hit, and only with a registry check newer than the hit. */
export function ComplianceTab({ c }: TabProps) {
  const d = deviceView(c);
  const r = d?.registry;
  if (!r) return null;
  const w = d?.wipe;
  return (
    <>
      {w && (
        <>
          <p className="stpad" role="status" style={w.state === 'ok' ? undefined : { color: 'var(--bad)' }}>Data wipe: {wipeState(w)}</p>
          {w.certificate && w.state !== 'none' && (
            <Kv rows={[
              ['Certificate', w.certificate.id ?? 'None'],
              ['Method', w.certificate.method ?? 'None'],
              ['Tool version', w.certificate.toolVersion ?? 'None'],
              ['Verification', w.certificate.verification ?? 'None'],
              ['Operator', w.certificate.operator ?? 'None'],
              ['Time', w.certificate.at ? fmtDateYear(w.certificate.at) : 'None'],
            ]} />
          )}
        </>
      )}
      <p className="stpad" role="status" style={r.state === 'hit' ? { color: 'var(--bad)' } : undefined}>{registryLine(r)}</p>
      <Kv rows={[
        ['Status', registryState(r)],
        ['Checked', r.checkedAt ? `${fmtDateYear(r.checkedAt)}${r.ageDays != null ? ` · ${r.ageDays} days ago` : ''}` : 'Never'],
        ['Source', r.source || 'None'],
        ['Re-check after', `${r.recheckDays} days`],
        ['Allowed routes', r.state === 'hit' ? (r.allowedRoutes.length ? r.allowedRoutes.join(', ') : 'None') : 'All'],
      ]} />
    </>
  );
}
/** The Payout tab of a received-device case (P9-6.8, DV-05): the quote, the payout the pack's table gives, the gap, the rule and
 * its table version, and where it stands. A payout that waits shows the grading photos and, for a person with `decidePayouts`,
 * a form (amount, reason) that calls `payout.decide`; the server refuses an amount above the quote. */
export function PayoutTab({ c }: TabProps) {
  const p = deviceView(c)?.payout;
  const act = useAction();
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  if (!p) return null;
  const submit = async () => {
    setErr('');
    const r = await act.run(() => decidePayout(c.id, Number(amount), reason.trim()), { inline: setErr });
    if (r.ok) { setAmount(''); setReason(''); }
  };
  return (
    <>
      <p className="stpad" role="status">{payoutLine(p)}</p>
      <Kv rows={[
        ['Quote', usd(p.quote)],
        ['Payout', usd(p.adjusted)],
        ['Rule', `${p.reason} (${p.table})`],
        ['Status', payoutState(p)],
      ]} />
      {p.status === 'waiting' && (
        <>
          <ul className="stsys stpad" aria-label="Grading photos">
            {p.photos.length ? p.photos.map((id) => <li key={id} className="mono">{id}</li>) : <li>No grading photos on file</li>}
          </ul>
          {can('decidePayouts') && (
            <form className="stpad" onSubmit={(e) => { e.preventDefault(); void submit(); }} aria-label="Decide the payout">
              <label>Payout ($, at most {usd(p.quote)})
                <input type="number" min={0} max={p.quote} step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
              </label>
              <label>Reason
                <input type="text" minLength={10} value={reason} onChange={(e) => setReason(e.target.value)} required />
              </label>
              {err && <p role="alert" style={{ color: 'var(--bad)' }}>{err}</p>}
              <button className="btn pri" type="submit" disabled={act.pending}>Decide the payout</button>
            </form>
          )}
        </>
      )}
    </>
  );
}

/** The Channels tab of a received-device case (P9-6.10, DV-06): the expected net, days to sell, P10 to P90 and feed week of every
 * channel, and a banner for a floor or price-confidence hold with the owner it waits for. Only a person releases a hold. */
export function ChannelsTab({ c }: TabProps) {
  const d = deviceView(c);
  const rows = d?.channels;
  if (!rows) return null;
  const holds = d?.priceHolds ?? [];
  return (
    <>
      {holds.map((h) => (
        <p key={h.id} className="stpad" role="status" style={{ color: 'var(--bad)' }}>{h.reason} · waits for {h.owner}</p>
      ))}
      <ul className="stsys stpad" aria-label="Price per channel">{rows.map((r) => <li key={r.k} title={r.why || undefined}>{channelRow(r)}</li>)}</ul>
    </>
  );
}
