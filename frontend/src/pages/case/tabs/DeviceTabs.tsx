/** The Device tab of a received-device case (P9-6.4, DV-01): IMEI, model and storage, grade and quote, partner, batch, received
 * date and, for a bulk lot, the device lines. Starts stage 5 of a device case (tabs/index.tsx). */
import { deviceView } from '../../../api/device';
import { fmtDateYear } from '../../../api/format';
import { Kv } from '../CaseBlocks';
import { deviceLine, gradeLine, lotLines, mismatchLine, quoteCheckLine, refLine, registryLine, registryState } from '../device';
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
  const r = deviceView(c)?.registry;
  if (!r) return null;
  return (
    <>
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