/** The Ticket tab of a service-desk case (P9-4.3, SD-01): ticket number, account code, market, site, loaner promised and one row
 * per tool (serial, family, age, fault or "unclear", cover) with the result of the contract right and recall checks. Starts
 * stage 6 of a service-desk case (tabs/index.tsx). */
import { useEffect, useState } from 'react';
import { can } from '../../../api/session';
import { FAULT_CODES, postFault, serviceDeskView, serviceDeskWhatIf, tablesLine, type WhatIfResult } from '../../../api/serviceDesk';
import { toast } from '../../../components/toast';
import { refused } from '../../../hooks/useAction';
import { Kv } from '../CaseBlocks';
import { approvalLine, estimateLine, estimateStatus, expectedLine, flipLine, gateLine, keyUsed, lineProblem, lineSummary, money, optionOrder, optionSummary, peakLine, ticketLine } from '../serviceDesk';
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
      {tablesLine(v) && <p className="stpad" data-sd-tables>{tablesLine(v)}</p>}
      {v.approval && <p className="stpad">{approvalLine(v.approval)}</p>}
      {c.exec?.terms && <p className="stpad">{termsLine(c.exec.terms)}</p>}{/* the terms of an approved plan (P9-4.9) */}
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

/** The Credit lever tab (P9-4.10, SD-09): sliders for the credit, the take-up, the repair cost and the wait; the options run again on the
 * server with them (serviceDesk.whatIf, a read), and the expected margin of the upgrade is shown over credits from 0 to 40%, where it
 * peaks and where the recommendation flips. Nothing is stored or sent; the numbers are the server's, never a model's. */
export function CreditLeverTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  const [credit, setCredit] = useState(10);
  const [takeUp, setTakeUp] = useState<number | null>(null);
  const [cost, setCost] = useState(100);
  const [wait, setWait] = useState(0);
  const [line, setLine] = useState(v?.lines[0]?.n ?? 1);
  const [res, setRes] = useState<WhatIfResult | null>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      serviceDeskWhatIf(c.id, { line, credit_pct: credit / 100, repair_cost_pct: cost, wait_days: wait, ...(takeUp === null ? {} : { take_up: takeUp / 100 }) }).then((r) => {
        if (!live) return;
        if (r.ok) { setRes(r.output); setErr(''); } else setErr(r.error.message);
      });
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [c.id, line, credit, takeUp, cost, wait]);
  if (!v) return null;
  const r = res?.lines[0];
  const slider = (label: string, value: number, set: (n: number) => void, min: number, max: number, unit: string) => (
    <label style={{ display: 'block' }}>{label}: {value}{unit}{' '}
      <input type="range" min={min} max={max} value={value} aria-label={label} onChange={(ev) => set(Number(ev.target.value))} />
    </label>
  );
  return (
    <div className="stpad" aria-label="Credit lever">
      <p>Test a credit before offering it. Nothing is sent: this only recalculates the options.</p>
      {v.lines.length > 1 && (
        <label>Tool <select value={line} onChange={(ev) => setLine(Number(ev.target.value))} aria-label="Tool to test">
          {v.lines.map((l) => <option key={l.n} value={l.n}>{l.n}. {l.serial}</option>)}
        </select></label>
      )}
      {slider('Credit', credit, setCredit, 0, 40, '%')}
      <label style={{ display: 'block' }}>
        <input type="checkbox" checked={takeUp === null} onChange={(ev) => setTakeUp(ev.target.checked ? null : 50)} /> Use the take-up curve
      </label>
      {takeUp !== null && slider('Take-up', takeUp, setTakeUp, 0, 100, '%')}
      {slider('Repair cost', cost, setCost, 80, 150, '% of the estimate')}
      {slider('Extra wait', wait, setWait, 0, 30, ' days')}
      {err && <p style={{ color: 'var(--bad)' }}>{err}</p>}
      {r && (
        <>
          <p><b>{flipLine(r)}.</b> {r.flips ? 'This differs from the recommendation the case holds.' : 'The recommendation stays as the case holds it.'}</p>
          <p>{peakLine(r)}</p>
          {res && res.gr_c1.length > 0 && <p>{res.gr_c1[0].reason} A person must approve it.</p>}
          <table aria-label={`Expected margin by credit for ${r.serial}`}>
            <thead><tr><th>Credit</th><th>Take-up</th><th>Upgrade, expected margin</th><th>Fix and return</th><th>Best</th></tr></thead>
            <tbody>
              {r.curve.map((p) => (
                <tr key={p.credit_pct} style={r.peak?.credit_pct === p.credit_pct ? { fontWeight: 600 } : undefined}>
                  <td>{Math.round(p.credit_pct * 100)}%</td>
                  <td>{p.take_up === null ? 'n/a' : `${Math.round(p.take_up * 100)}%`}</td>
                  <td>{p.upgrade === null ? 'Not offered' : money(p.upgrade, r.currency)}</td>
                  <td>{p.fix === null ? 'n/a' : money(p.fix, r.currency)}</td>
                  <td>{p.best ? optionName(p.best) : 'None'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

const optionName = (k: string) => (k === 'fix' ? 'Fix and return' : k === 'swap' ? 'Covered swap' : 'Upgrade with credit');

// The Batch tab (P9-4.8): its own imports sit with it, so the block stands alone.
import { batchTotalsLine, splitLine, termsLine } from '../serviceDesk';

/** The Batch tab of a batch case (P9-4.8, SD-07): the split ("Upgrade 9 · Fix 11 · Covered swap 2"), the totals of the chosen
 * options for the customer and the margin, and a table of the lines with each line's option and reason; a line opens to its
 * options. The split, the totals and every reason are the server's, computed per tool, never a model's. */
export function BatchTab({ c }: TabProps) {
  const v = serviceDeskView(c);
  const sp = v?.split;
  if (!v || !sp) return null;
  const cur = v.lines.find((l) => l.estimate)?.estimate?.currency ?? '';
  const byN = new Map(v.lines.map((l) => [l.n, l]));
  return (
    <>
      <Kv rows={[
        ['Split', splitLine(sp.counts) || 'No option can be offered yet'],
        ['Totals', batchTotalsLine(sp.totals, cur)],
      ]} />
      <table className="stpad" aria-label="The lines of the batch and the option each takes">
        <thead><tr><th>#</th><th>Serial</th><th>Option</th><th>Why</th><th>Options</th></tr></thead>
        <tbody>
          {sp.lines.map((x) => {
            const l = byN.get(x.n);
            return (
              <tr key={x.n}>
                <td>{x.n}</td><td>{x.serial}</td><td>{x.name ?? 'None yet'}</td><td>{x.why}</td>
                <td>
                  {l?.options && (
                    <details>
                      <summary>Options</summary>
                      {optionOrder(l.options, l.best).map((o) => <div key={o.k}>{o.name}: {optionSummary(o, cur)}</div>)}
                    </details>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
