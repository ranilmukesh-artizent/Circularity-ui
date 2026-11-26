import { useState } from 'react';
import { compositionHistory, publishComposition, type Composition, type Published } from '../../../api/compose';
import { StatusPill } from '../../../components/kit/StatusPill';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { SHARE_DEFAULT, parseShare, publishBlock, publishLabel, reportLines, rolloutLine } from './composeView';

/**
 * Step 5 of Compose (plan 9, P9-8.20, story X-10): the replay report of the org's decision flow (route mix, straight-through,
 * approvals and exceptions a day, uplift with its band) and "Publish to <region> at 20 %". Publishing starts the canary of the
 * rollout (P9-7.3) as the signed-in person; widening it stays in the Rollout panel. Afterwards: the rollout state and the
 * version history. The words about the report are the server's (a model's only when its numbers check out).
 */
export function PublishStep({ c }: { c: Composition }) {
  const h = compositionHistory(c.id);
  const [region, setRegion] = useState(c.org_unit_id);
  const [share, setShare] = useState(String(SHARE_DEFAULT));
  const [err, setErr] = useState('');
  const [done, setDone] = useState<Published | null>(null);
  const action = useAction();
  const amount = parseShare(share);
  const block = publishBlock(c.status, h.publish) ?? (amount === null ? 'The share is a whole number from 1 to 99.' : !region.trim() ? 'Name the region.' : null);
  const r = h.publish.report;

  const publish = async () => {
    setErr('');
    const out = await action.run(() => publishComposition(c.id, region.trim(), amount ?? undefined), { all: setErr });
    if (out.ok) {
      setDone(out.output);
      toast(out.output.log ?? 'Published.');
    }
  };

  return (
    <div className="cmp-step">
      <h4>Replay report</h4>
      {r ? (
        <>
          <p className="note">{r.n_decided} of {r.n_items} past items decided over {r.days} business days.</p>
          <table className="t static" aria-label="Route mix">
            <thead><tr><th>Route</th><th>Actual</th><th>Flow</th></tr></thead>
            <tbody>
              {r.route_mix.map((m) => <tr key={m.route}><td>{m.route}</td><td>{m.actual_pct.toFixed(1)} %</td><td>{m.flow_pct.toFixed(1)} %</td></tr>)}
            </tbody>
          </table>
          <ul className="cmp-ops">{reportLines(r).map((l) => <li key={l}>{l}</li>)}</ul>
        </>
      ) : <p className="note">No replay report yet. Run a replay of the draft flow in the Modeler (Replay).</p>}
      {done && <p role="status">{done.text}{done.by_model ? ' (worded by a model; the numbers are the report’s)' : ''}</p>}
      {c.status === 'approved' && (
        <div className="cmp-question">
          <div className="row">
            <label>Region <input aria-label="Region" value={region} maxLength={80} onChange={(e) => setRegion(e.target.value)} /></label>
            <label>Share % <input aria-label="Share" inputMode="numeric" size={3} value={share} onChange={(e) => setShare(e.target.value)} /></label>
            <button className="btn sm pri" disabled={action.pending || !!block} title={block ?? undefined} onClick={() => void publish()}>
              {publishLabel(region, amount ?? SHARE_DEFAULT)}
            </button>
          </div>
          {block && <span className="note">{block}</span>}
        </div>
      )}
      {c.status !== 'approved' && c.status !== 'published' && <p className="note">{publishBlock(c.status, h.publish)}</p>}
      {err && <p className="err" role="alert">{err}</p>}
      <h4>Rollout</h4>
      <p>
        <StatusPill tone={h.publish.rollouts.length ? 'ok' : 'line'} label={h.publish.flow_stage ?? 'no flow'} /> {rolloutLine(h.publish.rollouts)}
      </p>
      <h4>Version history</h4>
      <ul className="cmp-ops" aria-label="Version history">
        {h.versions.map((v) => <li key={v.version}>v{v.version} {v.status.replace('_', ' ')} by {v.by}{v.at ? ` · ${new Date(v.at).toLocaleString()}` : ''}</li>)}
        {h.versions.length === 0 && <li className="note">No version yet: it is a draft.</li>}
      </ul>
      <h4>Journal</h4>
      <ul className="cmp-ops" aria-label="Journal">
        {h.journal.map((j) => <li key={j.seq}>{j.action} by {j.actor}{j.at ? ` · ${new Date(j.at).toLocaleString()}` : ''}</li>)}
      </ul>
    </div>
  );
}
