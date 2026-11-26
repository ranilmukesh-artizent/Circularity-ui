import { useState } from 'react';
import {
  computeRepairAccuracy, fitModel, fitStageCalibration, promoteModel, proposeModel, STAGE_OPTIONS, stageCalibrationOf, stageLabel, useModels,
  type ModelVersion,
} from '../../api/agents'; // prettier-ignore
import { barText } from './repairAccuracy';
import { medianLines, qualityLine, skippedLines } from './ratedLife';
import { fmtDateYear, money } from '../../api/format';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const STATUS_CHIP: Record<ModelVersion['status'], string> = { candidate: 'y', active: 'ok', retired: 'line' };
const TEMPLATE_LABEL: Record<string, string> = {
  industrial: 'Industrial', tool_fleet: 'Tool fleet', device: 'Device recommerce', used_cars: 'Used cars',
  telecom_network: 'Telecom network', medical_rental: 'Medical rental', itad: 'IT asset disposition',
};
/** The seven packs a model can be fitted for (P9-13.7), whatever the server has an active model for. */
const PACKS = Object.keys(TEMPLATE_LABEL);
const label = (t: string) => TEMPLATE_LABEL[t] ?? t;
const err = (v: number | null) => (v == null ? '—' : money(v));
const DRIFT_CHIP = { ok: 'ok', watch: 'y', alert: 'bad' } as const;
/** A price model's template, or a stage calibration's pack and stage (P9-2.9). */
const templateLabel = (t: string, kind?: string) => {
  if (kind === 'rated_life') return `${label(t)} · remaining life`;
  if (kind === 'price') return `${label(t)} · price`;
  if (kind === 'take_up') return `${label(t)} · take-up`;
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
  const templates = [...new Set([...PACKS, ...Object.keys(s.active).filter((t) => !stageCalibrationOf(t))])];
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
  const fitLife = async () => {
    const r = await action.run(() => fitModel('tool_fleet', 'rated_life'));
    if (r.ok) toast(`Candidate ${r.output.id} fitted on ${r.output.metrics.n} teardown verdicts.`);
  };
  const fitPrice = async () => {
    const r = await action.run(() => fitModel('device', 'price'));
    if (r.ok) toast(`Candidate ${r.output.id} fitted on ${r.output.metrics.n} settled sales and feed prices.`);
  };
  const fitTakeUp = async () => {
    const r = await action.run(() => fitModel('tool_fleet', 'take_up'));
    if (r.ok) toast(`Candidate ${r.output.id} fitted on ${r.output.metrics.n} past upgrade offers.`);
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
          {' · '}Tool remaining life: {s.activeRatedLife ? <b>{s.activeRatedLife}</b> : 'pack table'}
          {' · '}Device price: {s.activePrice ? <b>{s.activePrice}</b> : 'pack index table'}
          {' · '}Upgrade take-up: {s.activeTakeUp ? <b>{s.activeTakeUp}</b> : 'pack prior'}
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
              {template === 'tool_fleet' && (
                <button className="btn sm" id="ag-mdl-fit-life" disabled={action.pending} onClick={fitLife} title="Fits each component's Weibull remaining life on the depot's teardown verdicts; it values tool life only once a different person promotes it.">Fit remaining life</button>
              )}
              {template === 'tool_fleet' && (
                <button className="btn sm" id="ag-mdl-fit-takeup" disabled={action.pending} onClick={fitTakeUp} title="Fits how the share of customers taking an upgrade rises with the credit offered, on the last 24 months of offers (at least 200); it replaces the pack's prior only once a different person promotes it.">Fit take-up model</button>
              )}
              {template === 'device' && (
                <button className="btn sm" id="ag-mdl-fit-price" disabled={action.pending} onClick={fitPrice} title="Fits a price per channel with a P10 to P90 range on the settled sales and the weekly feed (at least 300 rows); it prices devices only once a different person promotes it.">Fit price model</button>
              )}
              <button className="btn sm" id="ag-mdl-fit-stage" disabled={action.pending} onClick={fitStage} title="Needs 20 decided outcomes of the stage; until then it keeps its raw confidence (not calibrated yet).">Fit stage calibration</button>
            </div>
          )}
        </div>
        {s.models.length ? (
          <div className="tw">
            <table className="t static">
              <thead>
                <tr>
                  <th>Model</th><th>Template</th><th>Status</th><th className="r">Outcomes or verdicts</th><th className="r">Error, current</th>
                  <th className="r">Error, this model</th><th>Fitted by</th><th>Drift and cadence</th><th>Promotion</th><th></th>
                </tr>
              </thead>
              <tbody>
                {s.models.map((m) => (
                  <tr key={m.id} data-model={m.id}>
                    <td>
                      <b className="mono">{m.id}</b>
                      <ModelNote m={m} />
                    </td>
                    <td>{templateLabel(m.template, m.kind)}</td>
                    <td><span className={'chip ' + STATUS_CHIP[m.status]}>{m.status}</span></td>
                    <td className="r num">{m.metrics.n}</td>
                    <td className="r num" title="Mean absolute error of the active model's net on the outcomes">{m.kind === 'rated_life' ? '—' : m.kind === 'take_up' ? <span title="Log loss of the pack's prior curve on the same offers">{loss(m.metrics.baseline_log_loss)}</span> : err(m.metrics.mae_active)}</td>
                    <td className="r num" title="Mean absolute error of this model's net on the outcomes">{m.kind === 'rated_life' ? <span title="Run hours, on the last 3 months held out">{qualityLine(m)}</span> : m.kind === 'take_up' ? <span title="Log loss of the learned curve on the offers it was fitted on">{loss(m.metrics.log_loss)}</span> : err(m.metrics.mae_candidate)}</td>
                    <td className="nowrap">{m.created_by}<div className="note">{fmtDateYear(m.created_at)}</div></td>
                    <td data-testid="drift-cell">
                      {m.drift_status ? <span className={'chip ' + DRIFT_CHIP[m.drift_status]} title={m.drift?.explanation ?? m.drift?.rule}>{m.drift_status}</span> : <span className="note">Not checked yet</span>}
                      {m.drift && <div className="note">{m.drift.rule}</div>}
                      {m.drift?.explanation && <div className="note">{m.drift.explanation}</div>}
                      <div className="note" title={m.cadence ?? undefined}>Trained {m.trained_at ? fmtDateYear(m.trained_at) : '—'}; next due {m.next_due ? fmtDateYear(m.next_due) : '—'}</div>
                    </td>
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
      <RepairAccuracy />
    </section>
  ); // prettier-ignore
}

/** Repair estimate accuracy (plan 9, P9-4.5, SD-08): the estimate replayed on held-out repairs, and which families are priced instantly. */
function RepairAccuracy() {
  const { repairAccuracy: a } = useModels();
  const action = useAction();
  const compute = async () => {
    const r = await action.run(() => computeRepairAccuracy());
    if (r.ok) toast(`Repair estimate accuracy computed: ${r.output.families} families, ${r.output.below} below the bar.`);
  };
  return (
    <div className="panel" id="agRepairAccuracy" style={{ marginTop: 12 }}>
      <div className="sh" style={{ padding: '8px 12px' }}>
        <h3>Repair estimate accuracy</h3>
        {a.can.compute && <button className="btn sm" id="ag-acc-compute" disabled={action.pending} onClick={compute}>Compute now</button>}
      </div>
      <div className="pb"><p className="note" style={{ marginTop: 0 }}>{barText(a.bar)}</p></div>
      {a.rows.length ? (
        <div className="tw">
          <table className="t static">
            <thead>
              <tr><th>Family</th><th>Org unit</th><th className="r">Held out</th><th className="r">MAE</th><th className="r">Inside the range</th><th className="r">Auto-priced</th><th>Instant pricing</th></tr>
            </thead>
            <tbody>
              {a.rows.map((r) => (
                <tr key={`${r.org_unit_id}/${r.model_class}`} data-family={r.model_class}>
                  <td><b>{r.model_class}</b></td>
                  <td>{r.org_unit_id ?? 'Shared'}</td>
                  <td className="r num">{r.n}</td>
                  <td className="r num">{money(r.mae)}</td>
                  <td className="r num">{Math.round(r.coverage * 100)}%</td>
                  <td className="r num">{Math.round(r.auto_share * 100)}%</td>
                  <td><span className={'chip ' + (r.instant ? 'ok' : 'y')}>{r.instant ? 'Instant pricing on' : 'Instant pricing off'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="pb"><div className="empty"><b>Not computed yet</b>The worker computes it once a day; a person who manages market tables can compute it now.</div></div>
      )}
    </div>
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

/** A device price model's quality on the newest 20% of rows: MAE, MAPE and the share inside P10 to P90 against its target, and what it learned from. */
export function priceLine(m: ModelVersion): string {
  const x = m.metrics;
  const pct = (v?: number) => (v == null ? '—' : `${Math.round(v * 100)}%`);
  const win = x.window ? `, ${x.window.from} to ${x.window.to}` : '';
  return `MAE ${err(x.mae ?? null)}, MAPE ${x.mape == null ? '—' : `${(x.mape * 100).toFixed(1)}%`}, inside the range ${pct(x.coverage)} (target ${pct(x.target ?? 0.8)}); trained on ${x.n_train ?? '—'} rows, tested on ${x.n_test ?? '—'}${win}`;
}

const loss = (v?: number) => (v == null ? '—' : v.toFixed(3));

/** A take-up model's curve and its error against the pack's prior (log loss, Brier score), then acceptance by credit band. */
export function takeUpLine(m: ModelVersion): string {
  const x = m.metrics;
  const f = m.factors[0];
  const curve = f ? `credit share x: 1 / (1 + exp(-(${(f.a ?? 0).toFixed(2)} + ${(f.b ?? 0).toFixed(2)} x)))` : 'no curve';
  return `${curve}; log loss ${loss(x.log_loss)} (prior ${loss(x.baseline_log_loss)}), Brier ${loss(x.brier)} (prior ${loss(x.baseline_brier)}); ${x.market ?? 'all markets'}, ${x.n} offers${x.window ? `, ${x.window.from} to ${x.window.to}` : ''}`;
}

/** What a model holds: its calibration factors or steps, or, for a remaining-life model, the median hours per component. */
export function ModelNote({ m }: { m: ModelVersion }) {
  if (m.kind === 'price') return <div className="note" data-testid="price-note">{priceLine(m)}</div>;
  if (m.kind === 'take_up') {
    const pct = (v: number) => `${Math.round(v * 100)}%`;
    return (
      <div className="note" data-testid="take-up-note">
        <div>{takeUpLine(m)}</div>
        {(m.metrics.bands ?? []).map((b) => (
          <div key={b.lo}>
            Credit {pct(b.lo)} to {pct(b.hi)}: {b.offered} offered, {b.accepted} taken ({b.offered ? pct(b.accepted / b.offered) : '—'}), {b.predicted.toFixed(0)} expected
          </div>
        ))}
      </div>
    );
  }
  if (m.kind !== 'rated_life') return <div className="note">{describe(m)}</div>;
  const lines = medianLines(m);
  return (
    <div className="note" data-testid="rated-life-note">
      <div>Remaining life, per component: {lines.length ? '' : 'none fitted; every component keeps its current rating'}</div>
      {lines.map((l) => <div key={l}>{l}</div>)}
      {skippedLines(m).map((l) => <div key={l}>{l}</div>)}
    </div>
  );
}
