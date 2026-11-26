import { useRef, useState } from 'react';
import { refreshWhatIf, type RefreshWhatIf } from '../../../api/refresh';
import { totalsLine } from './RefreshTools';

const money = (n: number, currency: string): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2, signDisplay: 'exceptZero' }).format(n);

const START = 25; // the pack's table starts at 25% of life left; the slider only moves what is sent once it is touched

/** "keep 5, swap 1, upgrade 1" to "keep 4, swap 2, upgrade 1": the split before and with the levers. */
export const splitLine = (r: RefreshWhatIf): string => `${totalsLine(r.before)} → ${totalsLine(r.split)}`;

/**
 * Test the proposal's levers (plan 9, P9-5.6, CR-06): a slider for the swap threshold and a switch for upgrades. The server runs the
 * refresh again on a copy of the market's table (refresh.whatIf, a read) and answers which tools change action and the fee, credit and
 * renewal impact; every figure is the server's, none is a model's. Nothing is stored or sent: a new threshold goes live only through
 * the table's own approval.
 */
export function RefreshLevers({ caseId }: { caseId: string }) {
  const [threshold, setThreshold] = useState(START);
  const [upgrades, setUpgrades] = useState(true);
  const [res, setRes] = useState<RefreshWhatIf | null>(null);
  const [err, setErr] = useState('');
  const latest = useRef(0);
  const run = (t: number, u: boolean) => {
    const n = ++latest.current;
    void refreshWhatIf(caseId, { swapThreshold: t, upgrades: u }).then((r) => {
      if (n !== latest.current) return; // a newer move is already on its way
      if (r.ok) { setRes(r.output); setErr(''); } else setErr(r.error.message);
    });
  };
  return (
    <div data-testid="rf-levers">
      <p style={{ margin: '12px 0 4px' }}>Test the levers. Nothing is sent: this only recalculates the proposal.</p>
      <label style={{ display: 'block' }}>
        Swap tools with less than {threshold}% of life left{' '}
        <input type="range" min={10} max={50} value={threshold} aria-label="Swap threshold" data-testid="rf-lever-threshold"
          onChange={(ev) => { const t = Number(ev.target.value); setThreshold(t); run(t, upgrades); }} />
      </label>
      <label style={{ display: 'block' }}>
        <input type="checkbox" checked={upgrades} data-testid="rf-lever-upgrades"
          onChange={(ev) => { setUpgrades(ev.target.checked); run(threshold, ev.target.checked); }} /> Upgrade tools whose parts end before the term
      </label>
      {err && <p style={{ color: 'var(--bad)' }} data-testid="rf-lever-error">{err}</p>}
      {res && (
        <div data-testid="rf-lever-result">
          <p style={{ margin: '4px 0' }} data-testid="rf-lever-split">{splitLine(res)}</p>
          {res.changed.length === 0 ? (
            <p className="note" data-testid="rf-lever-none">No tool changes action.</p>
          ) : (
            <ul className="note" style={{ margin: '4px 0', paddingLeft: 18 }} data-testid="rf-lever-changed">
              {res.changed.map((c) => <li key={c.serial}>{c.serial}: {c.from} → {c.to}</li>)}
            </ul>
          )}
          <p style={{ margin: '4px 0' }} data-testid="rf-lever-impact">
            Fee a month {money(res.fee_delta, res.currency)}; credits {money(res.credit_total, res.currency).replace('+', '')}; renewal likelihood{' '}
            {res.renewal_delta >= 0 ? '+' : ''}{(res.renewal_delta * 100).toFixed(1)} points
            {res.flips_route && <span className="chip warn"> another route ranks first</span>}
          </p>
          <p className="note" data-testid="rf-lever-note">{res.note}</p>
        </div>
      )}
    </div>
  );
}
