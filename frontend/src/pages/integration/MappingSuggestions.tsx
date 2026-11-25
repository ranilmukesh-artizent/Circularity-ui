/* Suggested field mappings for a source (plan 9, P9-8.2, registry entry I-19): "Suggest mappings" in the Data Mapping tab profiles
   the sample the source landed (up to 500 records per resource) and proposes a canonical field for each source field, with a
   calibrated confidence, a band and a reason. Read only: nothing is saved here (the choices arrive in P9-8.4). Sample values are
   masked by the server before they reach this table, and the model's own number is never shown as confidence. */
import { useState } from 'react';
import { suggestFieldMappings, type MappingBand, type MappingSuggestions } from '../../api/integration';
import { StatusPill } from '../../components/kit/StatusPill';
import { refused } from '../../hooks/useAction';

const BAND: Record<MappingBand, [string, string]> = { pre_ticked: ['Pre-ticked', 'ok'], check: ['Check', 'warn'], none: ['No proposal', 'line'] };
const pct = (c: number) => Math.round(c * 100) + '%';

export function MappingSuggestions({ sourceId }: { sourceId: string }) {
  const [state, setState] = useState<'idle' | 'running' | MappingSuggestions | { fail: string }>('idle');
  async function run() {
    setState('running');
    const r = await suggestFieldMappings(sourceId);
    if (refused(r)) return setState({ fail: r.error.message });
    setState(r.output);
  }
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}>
        <button className="btn sm" onClick={run} disabled={state === 'running'}>Suggest mappings</button>
        <span className="note">Proposes a canonical field for each field in the sample. Nothing is saved.</span>
      </div>
      {state === 'running' && <div className="note"><span className="spin" /> Profiling the sample…</div>}
      {typeof state === 'object' && 'fail' in state && <div className="err">{state.fail}</div>}
      {typeof state === 'object' && 'rows' in state && <Result r={state} />}
    </div>
  );
}

function Result({ r }: { r: MappingSuggestions }) {
  if (!r.rows.length) return <div className="empty"><b>No sample yet</b>Sync this source once so there are records to profile.</div>;
  return (
    <>
      <div className="tw">
        <table className="t static maptbl" aria-label="Suggested field mappings">
          <thead><tr><th>Source field</th><th>Sample values</th><th>Proposed field</th><th>Confidence</th><th>Band</th><th>Reason</th></tr></thead>
          <tbody>
            {r.rows.map((x) => {
              const [label, tone] = BAND[x.band];
              return (
                <tr key={x.resource + '/' + x.field}>
                  <td className="mono">{x.field}</td>
                  <td className="mono">{x.samples.slice(0, 3).join(', ') || '—'}</td>
                  <td className="mono">
                    {x.target ?? <>No proposal{x.candidates.length > 0 && <span className="note"> · candidates: {x.candidates.map(([t, s]) => `${t} (${s.toFixed(2)})`).join(', ')}</span>}</>}
                  </td>
                  <td>{pct(x.confidence)}</td>
                  <td><StatusPill tone={tone} label={label} /></td>
                  <td>{x.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {r.gaps.length > 0 && <div className="note">Required canonical fields with no proposal: <span className="mono">{r.gaps.join(', ')}</span></div>}
    </>
  );
}
