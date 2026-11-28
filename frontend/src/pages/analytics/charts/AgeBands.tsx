/**
 * Open decisions by age: how long each decision has waited for approval, split by the route it proposes, with the value at risk
 * (the forecast net of the recommended route: modelled, not realised). Counted on the server over live cases. Every band and
 * every route segment opens the cases behind it.
 */
import { kfmt } from '../../../api/analytics';
import { useOpenAge, type AgeBand, type AgeRoute, type OpenAge } from '../../../api/analyticsRows';
import { Component, Suspense, useEffect, useState, type ReactNode } from 'react';
import { retryFailed } from '../../../api/client';
import { Loading } from '../../../components/Boundary';
import { fmtInt, type ViewSpec } from '../data/dataView';
import { ageSpec } from './specs';
import { useRoving } from './roving';
import './charts.css';

const REF = new Set(['redeploy', 'resale', 'intparts', 'relase', 'material', 'extparts', 'exit']);
const SPARE = ['var(--chart3)', 'var(--chart4)', 'var(--chart5)', 'var(--chart6)', 'var(--chart7)', 'var(--ink2)'];
/** A reference route has its token; any other route a pack brings gets the next spare colour, in the order the server lists them. */
const colorOf = (age: OpenAge) => (id: string) => (REF.has(id) ? `var(--rt-${id})` : SPARE[age.routes.filter((r) => !REF.has(r.id)).findIndex((r) => r.id === id) % SPARE.length]);
const dec = (n: number) => `${fmtInt(n)} ${n === 1 ? 'decision' : 'decisions'}`;

export function ageSummary(a: OpenAge): string {
  if (!a.total.n) return 'No decision is waiting for approval.';
  const old = a.bands.find((b) => b.key === '30+');
  const slow = a.bands.filter((b) => b.key === '15-30' || b.key === '30+').reduce((s, b) => s + b.value, 0);
  const share = a.total.value ? Math.round((slow / a.total.value) * 100) : 0;
  return `${dec(a.total.n)} wait for approval with ${kfmt(a.total.value)} at risk; ${share}% of that value has waited more than 14 days${old && old.n ? `, ${dec(old.n)} over 30` : ''}.`;
}

export function AgeBands({ age, onViewData }: { age: OpenAge; onViewData: (s: ViewSpec) => void }) {
  const { ref: keys, mark } = useRoving();
  if (!age.total.n) return <p className="note">No decisions are waiting.</p>;
  const max = Math.max(1, ...age.bands.map((b) => b.value));
  let i = 0;
  const color = colorOf(age);
  const open = (b: AgeBand, r?: AgeRoute) => onViewData(ageSpec(r ? r.rows : b.rows, [`Age: ${b.label}`, ...(r ? [`Route: ${r.name}`] : [])]));
  return (
    <figure className="ch-fig">
      <p className="ch-sum" id="age-sum">{ageSummary(age)}</p>
      <div className="ag" role="group" aria-label="Open decisions by age and route" aria-describedby="age-sum" ref={keys}>
        {age.bands.map((b) => (
          <div key={b.key} className="ag-row">
            <button type="button" className="ag-label" aria-label={`${b.label}: ${dec(b.n)}, ${kfmt(b.value)} at risk. Opens the cases.`} {...mark(i++)} onClick={() => open(b)}>
              <b>{b.label}</b><span>{dec(b.n)}</span>
            </button>
            <div className="ag-track" style={{ width: `${(b.value / max) * 100}%` }}>
              {b.routes.map((r) => (
                <button
                  key={r.id} type="button" className="ag-seg" style={{ flexGrow: Math.max(r.value, 1), background: color(r.id) }}
                  aria-label={`${b.label}, ${r.name}: ${dec(r.n)}, ${kfmt(r.value)} at risk. Opens the cases.`} {...mark(i++)} onClick={() => open(b, r)}
                />
              ))}
            </div>
            <b className="ag-val num">{kfmt(b.value)}</b>
          </div>
        ))}
      </div>
      <ul className="ag-key">
        {age.routes.map((r) => {
          const n = age.bands.reduce((s, b) => s + (b.routes.find((x) => x.id === r.id)?.n ?? 0), 0);
          return n ? <li key={r.id}><i style={{ background: color(r.id) }} aria-hidden="true" />{r.name} <span className="num">{fmtInt(n)}</span></li> : null;
        })}
      </ul>
      <p className="note ch-hint">Value at risk is the forecast net of each recommended route (modelled, not realised), as of {age.as_of}.</p>
    </figure>
  );
}

function Loaded({ org, onViewData }: { org: string; onViewData: (s: ViewSpec) => void }) {
  return <AgeBands age={useOpenAge(org)} onViewData={onViewData} />;
}

/** "Loading" that turns into an explanation after a while, so a stalled read is never an endless line. */
function Waiting({ onRetry }: { onRetry: () => void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), 15000);
    return () => window.clearTimeout(t);
  }, []);
  if (!slow) return <Loading label="Loading open decisions…" />;
  return (
    <div className="ch-fail" role="status">
      <p className="note">This is taking longer than usual. The server may be restarting.</p>
      <button type="button" className="btn sm" onClick={onRetry}>Try again</button>
    </div>
  );
}

class Failed extends Component<{ children: ReactNode; resetKey: string; onRetry: () => void }, { error: Error | null }> {
  override state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  override componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  override render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="ch-fail" role="alert">
        <p><b>The waiting decisions could not be loaded.</b></p>
        <p className="note">{this.state.error.message ? this.state.error.message + ' ' : ''}Check that you are still signed in, then try again.</p>
        <button type="button" className="btn sm" onClick={() => { retryFailed(); this.setState({ error: null }); this.props.onRetry(); }}>Try again</button>
      </div>
    );
  }
}

/** The ageing chart with its own loading, empty and failure states, so a slow or refused read never takes the page with it. */
export function AgeChart({ org = '', onViewData }: { org?: string; onViewData: (s: ViewSpec) => void }) {
  const [n, setN] = useState(0);
  const retry = () => { retryFailed(); setN((x) => x + 1); };
  return (
    <Failed resetKey={org} onRetry={retry}>
      <Suspense key={n} fallback={<Waiting onRetry={retry} />}><Loaded org={org} onViewData={onViewData} /></Suspense>
    </Failed>
  );
}
