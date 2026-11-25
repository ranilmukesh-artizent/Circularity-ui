import { useState } from 'react';
import {
  fitModel, fitStageCalibration, promoteModel, proposeModel, STAGE_OPTIONS, stageCalibrationOf, stageLabel, useModels, type ModelVersion,
} from '../../api/agents'; // prettier-ignore
import { fmtDateYear, money } from '../../api/format';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const STATUS_CHIP: Record<ModelVersion['status'], string> = { candidate: 'y', active: 'ok', retired: 'line' };
const TEMPLATE_LABEL: Record<string, string> = { industrial: 'Industrial', tool_fleet: 'Tool fleet', device: 'Device recommerce' };
const label = (t: string) => TEMPLATE_LABEL[t] ?? t;
const err = (v: number | null) => (v == null ? '—' : money(v));
/** A price model's template, or a stage calibration's pack and stage (P9-2.9). */
const templateLabel = (t: string) => {
  const sc = stageCalibrationOf(t);
  return sc ? `${label(sc.pack)} · ${stageLabel(sc.stage)} confidence` : label(t);
};
const describe = (m: ModelVersion) => {
  if (stageCalibrationOf(m.template)) return m.factors.map((f) => `${f.raw?.toFixed(2)} → ${f.cal?.toFixed(2)}`).join('; ') || 'No steps';
  return m.factors.length ? m.factors.map((f) => `${f.route} · ${f.cls} ×${(f.factor ?? 0).toFixed(2)}`).join('; ') : 'No factors: too few outcomes';
};

/**
 * Models (plan 8 UI gaps): the model that values new intake cases and its calibration on the confirmed outcomes. A
 * Planner or Admin fits a candidate and proposes it; a different person with approve.flows approves the promotion.
 * The buttons show why the signed-in person may not press them; the server checks again (maker-checker).
 * Shown on the Agents page and on the Modeler.
 */
export function ModelsPanel() {
  const s = useModels();
  const action = useAction();
  const templates = Object.keys(s.active).filter((t) => !stageCalibrationOf(t));
  const [template, setTemplate] = useState(templates[0] ?? 'industrial');
  const [stage, setStage] = useState(STAGE_OPTIONS[0] ?? 'intake');
  const fitStage = async () => {
    const r = await action.run(() => fitStageCalibration(template, stage));
    if (r.ok) toast(`Candidate ${r.output.id} calibrates ${stageLabel(stage)} confidence on ${r.output.metrics.n} decided outcomes.`);
  };
  const fit = async () => {
    const r = await action.run(() => fitModel(template));
    if (r.ok) toast(`Candidate ${r.output.id} fitted on ${r.output.metrics.n} confirmed outcomes.`);
  };
  const propose = async (m: ModelVersion) => {
    const r = await action.run(() => proposeModel(m.id));
    if (r.ok) toast(`${m.id} is proposed. A different person approves the promotion.`);
  };
  const promote = async (m: ModelVersion) => {
    const r = await action.run(() => promoteModel(m.id));
    if (r.ok) toast(`${m.id} is the active model for new ${label(m.template).toLowerCase()} cases${r.output.retired ? `; ${r.output.retired} is retired` : ''}.`);
  };
  return (
    <section className="sect" id="agModels">
      <div className="sh">
        <h2>Models</h2>
        <span className="note">
          Base model {s.base} ·{' '}
          {templates.map((t, k) => (
            <span key={t}>{k > 0 && ' · '}{label(t)}: {s.active[t] ? <b>{s.active[t]}</b> : 'no calibration'}</span>
          ))}
        </span>
      </div>
      <div className="panel">
        <div className="pb">
          <p className="note" style={{ marginTop: 0 }}>
            A candidate is fitted on the confirmed outcomes. It values new intake cases only once it is proposed and a different person approves the
            promotion. Open cases keep their values.
          </p>
          {s.can.fit && (
            <div className="row" style={{ gap: 8 }}>
              <label htmlFor="ag-mdl-template">Template</label>
              <select id="ag-mdl-template" value={template} onChange={(e) => setTemplate(e.target.value)}>
                {templates.map((t) => <option key={t} value={t}>{label(t)}</option>)}
              </select>
              <button className="btn sm pri" id="ag-mdl-fit" disabled={action.pending} onClick={fit}>Fit a candidate</button>
              <label htmlFor="ag-mdl-stage">Stage</label>
              <select id="ag-mdl-stage" value={stage} onChange={(e) => setStage(e.target.value)}>
                {STAGE_OPTIONS.map((t) => <option key={t} value={t}>{stageLabel(t)}</option>)}
              </select>
              <button className="btn sm" id="ag-mdl-fit-stage" disabled={action.pending} onClick={fitStage} title="Needs 20 decided outcomes of the stage; until then it keeps its raw confidence (not calibrated yet).">Fit stage calibration</button>
            </div>
          )}
        </div>
        {s.models.length ? (
          <div className="tw">
            <table className="t static">
              <thead>
                <tr>
                  <th>Model</th><th>Template</th><th>Status</th><th className="r">Outcomes</th><th className="r">Error, current</th>
                  <th className="r">Error, this model</th><th>Fitted by</th><th>Promotion</th><th></th>
                </tr>
              </thead>
              <tbody>
                {s.models.map((m) => (
                  <tr key={m.id} data-model={m.id}>
                    <td>
                      <b className="mono">{m.id}</b>
                      <div className="note">{describe(m)}</div>
                    </td>
                    <td>{templateLabel(m.template)}</td>
                    <td><span className={'chip ' + STATUS_CHIP[m.status]}>{m.status}</span></td>
                    <td className="r num">{m.metrics.n}</td>
                    <td className="r num" title="Mean absolute error of the active model's net on the outcomes">{err(m.metrics.mae_active)}</td>
                    <td className="r num" title="Mean absolute error of this model's net on the outcomes">{err(m.metrics.mae_candidate)}</td>
                    <td className="nowrap">{m.created_by}<div className="note">{fmtDateYear(m.created_at)}</div></td>
                    <td className="nowrap">
                      {m.approved_by ? <>Approved by {m.approved_by}</> : m.proposal ? <>Proposed by {m.proposal.by}<div className="note">{fmtDateYear(m.proposal.at)}</div></> : <span className="note">Not proposed</span>}
                    </td>
                    <td>{m.status === 'candidate' && <Buttons m={m} can={s.can} busy={action.pending} onPropose={propose} onPromote={promote} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pb"><div className="empty"><b>No models fitted yet</b>New cases are valued with the base model {s.base}.</div></div>
        )}
      </div>
    </section>
  ); // prettier-ignore
}

function Buttons({ m, can, busy, onPropose, onPromote }: {
  m: ModelVersion; can: { fit: boolean; promote: boolean }; busy: boolean;
  onPropose: (m: ModelVersion) => void; onPromote: (m: ModelVersion) => void;
}) {
  const why = can.promote ? m.blocks.promote : null;
  return (
    <div style={{ display: 'grid', gap: 4, justifyItems: 'start' }}>
      {can.fit && !m.proposal && (
        <button className="btn sm" disabled={busy || !!m.blocks.propose} title={m.blocks.propose ?? undefined} onClick={() => onPropose(m)}>Propose promotion</button>
      )}
      {can.promote && (
        <button className="btn sm pri" disabled={busy || !!why} title={why ?? undefined} onClick={() => onPromote(m)}>Approve promotion</button>
      )}
      {why && <span className="note">{why}</span>}
    </div>
  );
}
