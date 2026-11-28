import { useState } from 'react';
import { compositionHistory, markStep, setStageAgents, type Autonomy, type Composition, type StageView } from '../../../api/compose';
import { canPage } from '../../../api/session';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { AUTONOMY_ITEMS, GUARDRAIL_NOTE, THRESHOLD, cleanRows, thresholdError, thresholdText } from './composeView';
import './publish.css';

const HELP: Record<Autonomy, string> = {
  recommend: 'It prepares; a person decides every time.',
  limits: 'It acts up to the limits; above them a person decides.',
  alone: 'It acts on its own.',
};

/**
 * Step 3 of Compose (plan 9, P9-8.20; reshaped 28 Nov 2026): one row per stage of the pack. Each names the registered agent
 * that runs it (the Agents page's registry: the same agent, its runs and its tools are there), and the person chooses how far
 * it goes alone: recommend only, act within limits (a value and an item count), or act alone. One confidence threshold (65 to
 * 85 %) applies to all. The server checks every row and the range, and the platform's guardrails hold whatever is chosen. Once
 * the setup is approved these settings are what the stage chain runs with for this organisation.
 */
export function AgentsStep({ c }: { c: Composition }) {
  const h = compositionHistory(c.id);
  const [rows, setRows] = useState<StageView[]>(h.stages);
  const [pct, setPct] = useState(Math.round(h.threshold * 100));
  const [err, setErr] = useState('');
  const [dirty, setDirty] = useState(false);
  const action = useAction();
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const saved = (c.steps.agents.settings as unknown[] | undefined)?.length ?? 0;
  const done = c.steps.agents.state === 'done';
  const bad = thresholdError(pct);

  const change = (stage: string, patch: Partial<StageView>) => {
    setDirty(true);
    setRows((all) => all.map((r) => (r.stage === stage ? { ...r, ...patch } : r)));
  };
  const limit = (stage: string, key: 'value_limit' | 'bulk_limit', v: string) => {
    setDirty(true);
    setRows((all) => all.map((r) => {
      if (r.stage !== stage) return r;
      const next = { ...(r.limits ?? {}) };
      if (v.trim() === '' || Number.isNaN(Number(v))) delete next[key];
      else next[key] = Math.max(0, Number(v));
      return { ...r, limits: next };
    })); // prettier-ignore
  };

  const save = async () => {
    setErr('');
    const r = await action.run(() => setStageAgents(c.id, cleanRows(rows), pct / 100), { all: setErr });
    if (r.ok) {
      setDirty(false);
      toast('Saved the agent settings.');
    }
  };
  const mark = async () => {
    const r = await action.run(() => markStep(c.id, 'agents'), { all: setErr });
    if (r.ok) toast('The agents step is done.');
  };
  const needsSave = dirty || saved === 0;

  return (
    <div className="cmp-step agt">
      <p className="note">{GUARDRAIL_NOTE} Below the confidence threshold an agent’s write waits for a person, whatever its autonomy.</p>
      <ul className="agt-rows" aria-label="Stage agents">
        {rows.map((r) => {
          const runners = r.runs_as ?? [];
          const off = runners.filter((a) => !a.enabled);
          return (
            <li key={r.stage} className="agt-row" data-stage={r.stage}>
              <div className="agt-stage">
                <b>{r.label}</b>
                <span className="note">
                  {runners.length
                    ? <>Run by {runners.map((a, k) => <span key={a.id}>{k > 0 && ', '}{canPage('agents') ? <a className="lnk" href="#/agents">{a.name ?? a.id}</a> : a.name ?? a.id}</span>)}</>
                    : <>Run by the {r.agent_id} agent</>}
                  {off.length > 0 && <span className="off"> · switched off in Agents</span>}
                </span>
              </div>
              <div className="agt-seg" role="radiogroup" aria-label={`Autonomy of ${r.label}`}>
                {AUTONOMY_ITEMS.map(([k, label]) => (
                  <label key={k} title={HELP[k]}>
                    <input type="radio" name={`agt-${r.stage}`} value={k} checked={r.autonomy === k} disabled={!editable} onChange={() => change(r.stage, { autonomy: k })} />
                    {label}
                  </label>
                ))}
              </div>
              <div className="agt-limits">
                {r.autonomy === 'limits' ? (
                  <>
                    <label>
                      Up to a value of
                      <span className="agt-field">$<input aria-label={`Value limit of ${r.label}`} type="number" inputMode="decimal" min={0} placeholder="no limit" value={r.limits?.value_limit ?? ''} disabled={!editable} onChange={(e) => limit(r.stage, 'value_limit', e.target.value)} /></span>
                    </label>
                    <label>
                      At most at once
                      <span className="agt-field"><input aria-label={`Bulk limit of ${r.label}`} type="number" inputMode="numeric" min={0} placeholder="no limit" value={r.limits?.bulk_limit ?? ''} disabled={!editable} onChange={(e) => limit(r.stage, 'bulk_limit', e.target.value)} /> items</span>
                    </label>
                  </>
                ) : <span className="note">{HELP[r.autonomy]}</span>}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="agt-th">
        <div className="agt-th-h">
          <label htmlFor="agt-th">Confidence threshold</label>
          <output htmlFor="agt-th">{thresholdText(pct / 100)}</output>
        </div>
        <input id="agt-th" aria-label="Confidence threshold" type="range" min={THRESHOLD.min} max={THRESHOLD.max} step={1} value={pct} disabled={!editable} onChange={(e) => { setDirty(true); setPct(Number(e.target.value)); }} />
        <div className="agt-scale" aria-hidden="true"><span>{THRESHOLD.min} %: agents act more often</span><span>{THRESHOLD.max} %: people decide more often</span></div>
      </div>

      {(bad || err) && <p className="err" role="alert">{bad ?? err}</p>}
      {editable && (
        <div className="agt-acts">
          <button className={'btn' + (needsSave ? ' pri' : '')} disabled={action.pending || !!bad} onClick={() => void save()}>Save settings</button>
          <button className={'btn' + (needsSave ? '' : ' pri')} disabled={action.pending || done || needsSave} onClick={() => void mark()}>{done ? 'Done' : 'Mark done'}</button>
          {needsSave && !done && <span className="note">{saved === 0 ? 'Save the settings first.' : 'You have changes that are not saved.'}</span>}
        </div>
      )}
      {!editable && <p className="note">These settings are fixed while the setup is {c.status.replace('_', ' ')}. To change them later, start another setup; each agent’s tools and runs are on the Agents page.</p>}
    </div>
  );
}
