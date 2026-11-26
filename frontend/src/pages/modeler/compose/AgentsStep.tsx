import { useState } from 'react';
import { compositionHistory, markStep, setStageAgents, type Autonomy, type Composition, type StageView } from '../../../api/compose';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { AUTONOMY_ITEMS, GUARDRAIL_NOTE, THRESHOLD, cleanRows, thresholdError, thresholdText } from './composeView';

/**
 * Step 3 of Compose (plan 9, P9-8.20, story X-10): one row per stage of the pack with its agent and how alone it may act
 * (Recommend only, Act within limits, Act alone), the limits for "within limits", and one confidence threshold (65 to 85 %). The
 * server checks every row and the range; the guardrails are the platform's whatever is chosen here. "Mark done" waits for a save.
 */
export function AgentsStep({ c }: { c: Composition }) {
  const h = compositionHistory(c.id);
  const [rows, setRows] = useState<StageView[]>(h.stages);
  const [pct, setPct] = useState(Math.round(h.threshold * 100));
  const [err, setErr] = useState('');
  const action = useAction();
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const saved = (c.steps.agents.settings as unknown[] | undefined)?.length ?? 0;
  const done = c.steps.agents.state === 'done';
  const bad = thresholdError(pct);

  const change = (stage: string, patch: Partial<StageView>) => setRows((all) => all.map((r) => (r.stage === stage ? { ...r, ...patch } : r)));
  const limit = (stage: string, key: 'value_limit' | 'bulk_limit', v: string) =>
    setRows((all) => all.map((r) => {
      if (r.stage !== stage) return r;
      const next = { ...(r.limits ?? {}) };
      if (v.trim() === '' || Number.isNaN(Number(v))) delete next[key];
      else next[key] = Math.max(0, Number(v));
      return { ...r, limits: next };
    })); // prettier-ignore

  const save = async () => {
    setErr('');
    const r = await action.run(() => setStageAgents(c.id, cleanRows(rows), pct / 100), { all: setErr });
    if (r.ok) toast('Saved the agent settings.');
  };
  const mark = async () => {
    const r = await action.run(() => markStep(c.id, 'agents'), { all: setErr });
    if (r.ok) toast('The agents step is done.');
  };

  return (
    <div className="cmp-step">
      <p className="note">{GUARDRAIL_NOTE}</p>
      <table className="t static" aria-label="Stage agents">
        <thead><tr><th>Stage</th><th>Agent</th><th>Autonomy</th><th>Limits</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.stage}>
              <td><b>{r.label}</b></td>
              <td>
                <input aria-label={`Agent of ${r.label}`} value={r.agent_id} disabled={!editable} maxLength={80} onChange={(e) => change(r.stage, { agent_id: e.target.value })} />
              </td>
              <td>
                <select aria-label={`Autonomy of ${r.label}`} value={r.autonomy} disabled={!editable} onChange={(e) => change(r.stage, { autonomy: e.target.value as Autonomy })}>
                  {AUTONOMY_ITEMS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                </select>
              </td>
              <td>
                {r.autonomy === 'limits' ? (
                  <span className="row">
                    <input aria-label={`Value limit of ${r.label}`} type="number" min={0} placeholder="Value $" value={r.limits?.value_limit ?? ''} disabled={!editable} onChange={(e) => limit(r.stage, 'value_limit', e.target.value)} />
                    <input aria-label={`Bulk limit of ${r.label}`} type="number" min={0} placeholder="Items" value={r.limits?.bulk_limit ?? ''} disabled={!editable} onChange={(e) => limit(r.stage, 'bulk_limit', e.target.value)} />
                  </span>
                ) : <span className="note">none</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <label className="row">
        <b>Confidence threshold</b>
        <input aria-label="Confidence threshold" type="range" min={THRESHOLD.min} max={THRESHOLD.max} step={1} value={pct} disabled={!editable} onChange={(e) => setPct(Number(e.target.value))} />
        <span>{thresholdText(pct / 100)}</span>
      </label>
      <p className="note">Below it, an agent's write waits for a person, whatever its autonomy.</p>
      {(bad || err) && <p className="err" role="alert">{bad ?? err}</p>}
      {editable && (
        <div className="row">
          <button className="btn sm" disabled={action.pending || !!bad} onClick={() => void save()}>Save settings</button>
          <button className="btn sm pri" disabled={action.pending || done || saved === 0} onClick={() => void mark()}>{done ? 'Done' : 'Mark done'}</button>
          {saved === 0 && <span className="note">Save the settings first.</span>}
        </div>
      )}
    </div>
  );
}
