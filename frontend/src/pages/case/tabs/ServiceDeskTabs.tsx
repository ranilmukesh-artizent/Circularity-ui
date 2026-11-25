/** The Ticket tab of a service-desk case (P9-4.3, SD-01): ticket number, account code, market, site, loaner promised and one row
 * per tool (serial, family, age, fault or "unclear", cover) with the result of the contract right and recall checks. Starts
 * stage 6 of a service-desk case (tabs/index.tsx). */
import { useState } from 'react';
import { can } from '../../../api/session';
import { FAULT_CODES, postFault, serviceDeskView } from '../../../api/serviceDesk';
import { toast } from '../../../components/toast';
import { refused } from '../../../hooks/useAction';
import { Kv } from '../CaseBlocks';
import { approvalLine, estimateLine, estimateStatus, expectedLine, gateLine, keyUsed, lineProblem, lineSummary, money, optionOrder, optionSummary, ticketLine } from '../serviceDesk';
import type { TabProps } from './index';

export function TicketTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  if (!v) return null;
  const rows: [string, string][] = [
    ['Ticket', ticketLine(v)],
    ['Account', v.account ?? 'Not given'],
    ['Market', v.market ?? 'Not given'],
    ['Site', v.site ?? 'Not given'],
    ['Loaner promised', v.loanerPromised ? 'Yes' : 'No'],
  ];
  return (
    <>
      <Kv rows={rows} />
      <table className="stpad" aria-label="Tools on the ticket">
        <thead><tr><th>#</th><th>Serial</th><th>Tool</th><th>Checks</th></tr></thead>
        <tbody>
          {v.lines.map((l) => {
            const bad = lineProblem(l);
            return (
              <tr key={l.n} style={bad ? { color: 'var(--bad)', background: 'var(--bad-soft)' } : undefined} title={bad ?? undefined}>
                <td>{l.n}</td><td>{l.serial}</td><td>{lineSummary(l)}</td>
                <td>{l.gates.map((g) => <div key={g.id}>{gateLine(g)}</div>)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

/** The Estimate tab (P9-4.4, SD-02): per tool the point estimate, its range, the confidence, the match count and key used, the
 * price lines with what each cites, and whether it is priced without a technician or a draft with the reason. The numbers are
 * the server's: computed from similar past repairs, never written by a model. */
export function EstimateTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  if (!v) return null;
  return (
    <>
      {v.lines.map((l) => {
        const e = l.estimate;
        return (
          <div key={l.n} className="stpad" aria-label={`Estimate for ${l.serial}`}>
            <h4>{l.n}. {l.serial} · {lineSummary(l)}</h4>
            {!e ? <p>No estimate yet.</p> : (
              <>
                <Kv rows={[
                  ['Estimate', e.n ? estimateLine(e) : 'No estimate'],
                  ['Matches', e.n ? `${e.n} similar repairs, ${keyUsed(e.key_used)}` : 'None in the last 3 years'],
                  ['Pricing', estimateStatus(e)],
                ]} />
                {e.lines.length > 0 && (
                  <table aria-label={`Price lines for ${l.serial}`}>
                    <thead><tr><th>Line</th><th>Amount</th><th>Basis</th><th>Cites</th></tr></thead>
                    <tbody>
                      {e.lines.map((p) => (
                        <tr key={p.label}><td>{p.label}</td><td>{money(p.amount, e.currency)}</td><td>{p.basis}</td><td>{p.cites}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
            {e && !e.auto && can('assess') && <PostFaultForm caseId={c.id} line={l.n} serial={l.serial} />}
          </div>
        );
      })}
    </>
  );
}

/** The Options tab (P9-4.6, SD-04): per tool the three options side by side, the recommended one first, each with the customer's
 * price, the margin, the days out of use, the expected take-up (upgrade), why, and its value lines with the table each cites. An
 * option that cannot be offered shows its reason. Under them, who approves. The numbers are the server's, never a model's. */
export function OptionsTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  if (!v) return null;
  return (
    <>
      {v.lines.map((l) => {
        const cur = l.estimate?.currency ?? '';
        return (
          <div key={l.n} className="stpad" aria-label={`Options for ${l.serial}`}>
            <h4>{l.n}. {l.serial} · {lineSummary(l)}</h4>
            {!l.options ? <p>No options yet.</p> : optionOrder(l.options, l.best).map((o) => (
              <div key={o.k} aria-label={`${o.name} for ${l.serial}`} style={o.eligible ? undefined : { opacity: 0.7 }}>
                <h5>{o.name}{o.k === l.best ? ' (recommended)' : ''}</h5>
                <p>{optionSummary(o, cur)}</p>
                {o.eligible && (
                  <>
                    <p>{expectedLine(o, cur)}. {o.why}</p>
                    <table aria-label={`Value lines of ${o.name} for ${l.serial}`}>
                      <thead><tr><th>Line</th><th>Amount</th><th>Basis</th><th>Cites</th></tr></thead>
                      <tbody>
                        {o.lines.map((x) => (
                          <tr key={x.label}><td>{x.label}</td><td>{x.type === 'c' ? '−' : ''}{money(x.amt, cur)}</td><td>{x.basis}</td><td>{x.cites}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            ))}
          </div>
        );
      })}
      {v.approval && <p className="stpad">{approvalLine(v.approval)}</p>}
    </>
  );
}

/** "Post the fault" (P9-4.7, SD-06): on a draft line, a technician (a role with `assess`) picks the fault code and may add a note; the
 * server prices the line again and runs its options again, and the Estimate and Options tabs refresh without re-keying. */
function PostFaultForm({ caseId, line, serial }: { caseId: string; line: number; serial: string }) {
  const [code, setCode] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const post = async () => {
    setBusy(true);
    try {
      const r = await postFault(caseId, line, code, note.trim() || undefined);
      if (!refused(r, 4200)) toast(`Fault posted for ${serial}: ${code}. Options re-run.`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div aria-label={`Post the fault for ${serial}`}>
      <h5>Post the fault</h5>
      <label>Fault <select value={code} onChange={(ev) => setCode(ev.target.value)} aria-label={`Fault code for ${serial}`}>
        <option value="">Choose the fault</option>
        {FAULT_CODES.map((f) => <option key={f.code} value={f.code}>{f.code} {f.name}</option>)}
      </select></label>{' '}
      <label>Note <input value={note} onChange={(ev) => setNote(ev.target.value)} aria-label={`Note for ${serial}`} /></label>{' '}
      <button className="btn pri" disabled={!code || busy} onClick={post}>Post the fault</button>
    </div>
  );
}
