import { useState, type ReactNode } from 'react';
import { compositionHistory, publishComposition, type Composition, type Published } from '../../../api/compose';
import { forkFlow, saveDraft, useModeler } from '../../../api/modeler';
import { importSampleHistory } from '../../../api/replay';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { LifecycleBar } from '../LifecycleBar';
import { ReplayPanel } from '../ReplayPanel';
import { SHARE_DEFAULT, parseShare, publishLabel, reportLines, rolloutLine } from './composeView';
import { publishChecks, type CheckState } from './publishView';
import './publish.css';

/**
 * Step 5 of Compose (plan 9, P9-8.20; reshaped 28 Nov 2026): publishing as a checklist. Four things must be true and each line
 * says which, who does it, and has its own control: the setup is approved; the decision flow has a draft that a different person
 * approved into shadow (the flow's own lifecycle buttons, here); a replay of that draft over past items has a report (import
 * history or use the sample, then replay, here); then "Publish to <region> at 20 %" starts the canary as the signed-in person.
 * The server checks every one again and refuses the maker and every agent; this only shows where things stand.
 */
export function PublishStep({ c }: { c: Composition }) {
  const h = compositionHistory(c.id);
  const s = useModeler(c.pack_key, c.org_unit_id);
  const [region, setRegion] = useState(c.org_unit_id);
  const [share, setShare] = useState(String(SHARE_DEFAULT));
  const [err, setErr] = useState('');
  const [done, setDone] = useState<Published | null>(null);
  const [replayKey, setReplayKey] = useState(0);
  const action = useAction();
  const amount = parseShare(share);
  const r = h.publish.report;
  const flow = s.flow;
  const own = flow.org_unit_id === c.org_unit_id;
  const checks = publishChecks(c.status, flow.status, !!r);
  const ready = checks.every((k) => k.state === 'done' || k.id === 'publish');
  const formBlock = amount === null ? 'The share is a whole number from 1 to 99.' : !region.trim() ? 'Name the region.' : null;
  const state = (id: string): CheckState => checks.find((k) => k.id === id)?.state ?? 'todo';

  const run = async <T,>(call: () => Promise<{ ok: boolean; output?: T }>, said: string) => {
    setErr('');
    const out = await action.run(call as never, { all: setErr });
    if (out.ok) toast(said);
    return out.ok;
  };
  const publish = async () => {
    setErr('');
    const out = await action.run(() => publishComposition(c.id, region.trim(), amount ?? undefined), { all: setErr });
    if (out.ok) {
      setDone(out.output);
      toast(out.output.log ?? 'Published.');
    }
  };
  const sample = async () => {
    if (await run(() => importSampleHistory(c.pack_key, c.org_unit_id), 'Sample history imported.')) setReplayKey((k) => k + 1);
  };

  return (
    <div className="cmp-step pub">
      <ol className="pub-list">
        <Check n={1} state={state('approved')} title="The setup is approved" who="A different person from the one who made it">
          {c.status === 'approved' || c.status === 'published'
            ? <p className="note">Approved by {c.approved_by}.</p>
            : <p className="note">It is {c.status === 'submitted' ? 'waiting for its approver' : c.status === 'sent_back' ? 'sent back' : 'still a draft'}. <a className="lnk" href={`#/setup?compose=${c.id}&step=approve`}>{c.status === 'submitted' ? 'See the approval' : 'Send it for approval on the Approve step'}</a></p>}
        </Check>

        <Check n={2} state={state('flow')} title="The decision flow is approved into shadow" who="You submit the draft; a different person approves it">
          {!own && (
            <p className="note">
              This organisation uses the flow of {flow.org_unit_id}.{' '}
              {s.can.fork && <button className="btn sm" disabled={action.pending} onClick={() => void run(() => forkFlow(c.pack_key, c.org_unit_id), 'It now has its own flow.')}>Give it its own flow</button>}
            </p>
          )}
          {flow.status === 'pub' && (
            <>
              <p className="note">The flow is live as version {flow.ver} with no draft. Publishing a setup needs a draft of it: start one as it is, or change it on the Shape the flow step.</p>
              {s.can.edit && <button className="btn sm" disabled={action.pending} onClick={() => void run(() => saveDraft(flow.id, flow.graph, `Draft for setup ${c.id}`), 'Draft started.')}>Start a draft as it is</button>}
            </>
          )}
          {flow.status === 'draft' && <p className="note">The draft is yours to submit. Run the replay below first if you want its numbers in front of the approver.</p>}
          {flow.status === 'review' && <p className="note">Submitted. A different person approves it; that starts a shadow run, where it decides beside the live flow without acting.</p>}
          {flow.status === 'shadow' && <p className="note">In shadow: it decides beside the live flow without acting.</p>}
          {flow.status !== 'pub' && <LifecycleBar s={s} flush={async () => undefined} quiet />}
        </Check>

        <Check n={3} state={state('replay')} title="A replay of the draft has a report" who="You, on past items; nothing is written to a case">
          {r ? (
            <>
              <p className="note">{r.n_decided} of {r.n_items} past items decided over {r.days} business days.</p>
              <table className="t static" aria-label="Route mix">
                <thead><tr><th>Route</th><th>What happened</th><th>What this flow would do</th></tr></thead>
                <tbody>
                  {r.route_mix.map((m) => <tr key={m.route}><td>{m.route}</td><td>{m.actual_pct.toFixed(1)} %</td><td>{m.flow_pct.toFixed(1)} %</td></tr>)}
                </tbody>
              </table>
              <ul className="cmp-ops">{reportLines(r).map((l) => <li key={l}>{l}</li>)}</ul>
            </>
          ) : flow.status === 'pub' ? (
            <p className="note">The replay runs on the draft, so start the draft in line 2 first.</p>
          ) : (
            <>
              <p className="note">Import past decisions as a CSV, or use the template’s sample history (every value in it is invented), then press “Replay the draft”. It takes up to a few minutes and the report appears here.</p>
              <div className="row">
                <button className="btn sm" disabled={action.pending} onClick={() => void sample()}>Use the sample history</button>
              </div>
              <ReplayPanel key={replayKey} s={s} />
            </>
          )}
        </Check>

        <Check n={4} state={state('publish')} title="Publish to a share of one region" who="An approver; it starts small and widens in the Modeler">
          {c.status === 'published' ? (
            <p className="note">Published. {rolloutLine(h.publish.rollouts)}.</p>
          ) : (
            <>
              <div className="pub-form">
                <label>Region<input value={region} maxLength={80} autoComplete="off" onChange={(e) => setRegion(e.target.value)} /></label>
                <label>Share of cases<span className="pub-unit"><input inputMode="numeric" size={3} value={share} autoComplete="off" onChange={(e) => setShare(e.target.value)} /> %</span></label>
                <button className="btn pri" disabled={action.pending || !ready || !!formBlock} onClick={() => void publish()}>
                  {publishLabel(region, amount ?? SHARE_DEFAULT)}
                </button>
              </div>
              <p className="note">{!ready ? 'Waits for lines 1 to 3.' : formBlock ?? 'Ready. It starts for that share only; the rest keep the live flow.'}</p>
            </>
          )}
          {done && <p role="status">{done.text}{done.by_model ? ' (worded by a model; the numbers are the report’s)' : ''}</p>}
        </Check>
      </ol>
      {err && <p className="err" role="alert">{err}</p>}

      <details className="pub-hist">
        <summary>History of this setup</summary>
        <h4>Rollout</h4>
        <p>{rolloutLine(h.publish.rollouts)}</p>
        <h4>Versions</h4>
        <ul className="cmp-ops" aria-label="Version history">
          {h.versions.map((v) => <li key={v.version}>v{v.version} {v.status.replace('_', ' ')} by {v.by}{v.at ? ` · ${new Date(v.at).toLocaleString()}` : ''}</li>)}
          {h.versions.length === 0 && <li className="note">No version yet: it is a draft.</li>}
        </ul>
        <h4>Journal</h4>
        <ul className="cmp-ops" aria-label="Journal">
          {h.journal.map((j) => <li key={j.seq}>{j.action} by {j.actor}{j.at ? ` · ${new Date(j.at).toLocaleString()}` : ''}</li>)}
        </ul>
      </details>
    </div>
  );
}

const STATE_WORD: Record<CheckState, string> = { done: 'Done', now: 'To do', todo: 'Waits' };

function Check({ n, state, title, who, children }: { n: number; state: CheckState; title: string; who: string; children: ReactNode }) {
  return (
    <li className="pub-item" data-state={state}>
      <span className="pub-mark" aria-hidden="true">{state === 'done' ? <svg viewBox="0 0 12 12"><path d="M2.6 6.4l2.3 2.3 4.6-5" fill="none" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg> : n}</span>
      <div className="pub-body">
        <h4>{title} <span className="pub-state">{STATE_WORD[state]}</span></h4>
        <p className="pub-who">{who}</p>
        {children}
      </div>
    </li>
  );
}
