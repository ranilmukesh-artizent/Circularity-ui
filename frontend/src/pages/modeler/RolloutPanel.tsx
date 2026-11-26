import { useCallback, useEffect, useState } from 'react';
import {
  ROLLOUT_STEPS,
  bandLine,
  canaryLine,
  getRollout,
  goFull,
  pauseRollout,
  reportRows,
  rollbackRollout,
  rolloutReport,
  startCanary,
  widenRollout,
  type Rollout,
  type RolloutDone,
  type RolloutReport,
} from '../../api/rollout';
import { can } from '../../api/session';
import type { ActionResult, ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { STEP_MEANING, currentStep, stepStates } from './rolloutSteps';

const STEP_LABEL: Record<(typeof ROLLOUT_STEPS)[number], string> = { replay: 'Replay', shadow: 'Shadow', canary: 'Canary', full: 'Full' };
const MIN_REASON = 15;
export { currentStep };

/** Show the panel to the people who manage or approve flows, while the flow is not simply published. */
export const showRollout = (s: ModelerScreen): boolean => (can('approve.flows') || can('manageFlows')) && s.flow.status !== 'pub';

/**
 * Rollout (plan 9, P9-7.3, story X-06), beside the lifecycle bar: the steps Replay, Shadow, Canary, Full with the current one,
 * "Canary: FR at 20 % of volume", the cases in each arm, and the buttons with the reason when one is refused (no replay of
 * the candidate yet, or maker-checker: the person who made the changes cannot start, widen or publish them). `Publish` in the
 * lifecycle bar stays the direct path for a person with approve.flows.
 */
export function RolloutPanel({ s }: { s: ModelerScreen }) {
  const flowId = s.flow.id;
  const action = useAction();
  const [r, setR] = useState<Rollout | null>(null);
  const [rep, setRep] = useState<RolloutReport | null>(null);
  const [err, setErr] = useState('');
  const [region, setRegion] = useState('');
  const [share, setShare] = useState('20');
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    const got = await getRollout(flowId);
    if (got.ok) setR(got.output);
    const report = await rolloutReport(flowId);
    setRep(report.ok ? report.output : null);
  }, [flowId]);
  useEffect(() => {
    void load();
  }, [load, s.flow.status, s.flow.ver]);

  const go = async (call: () => Promise<ActionResult<RolloutDone>>) => {
    setErr('');
    const done = await action.run(call, { inline: setErr, ms: 4200 });
    if (done.ok) {
      if (done.output.log) toast(done.output.log + '.');
      setReason('');
      await load();
    }
  };

  if (!r || r.stage === null) return null;
  const step = currentStep(r.stage);
  const pct = Number(share);
  const reasonOk = reason.trim().length >= MIN_REASON;
  const why = (k: keyof Rollout['can']) => r.can[k] ?? undefined;
  const running = r.rollouts.length > 0;

  return (
    <Panel title="Rollout" sub={`${r.name}: v${r.base_ver} is live${r.candidate_ver ? `, v${r.candidate_ver} is the candidate` : ''}`} cls="mdl-rollout">
      <ol className="mdl-row" data-rollout-steps aria-label="Publish steps">
        {stepStates(r).map((v) => (
          <li key={v.step} className={'mdl-step ' + v.state} data-step={v.step} data-state={v.state} aria-current={v.step === step ? 'step' : undefined}>
            <b>{STEP_LABEL[v.step]}</b>
            <span className="s">{STEP_MEANING[v.step]}</span>
            <span className="st">{v.state === 'done' ? '✓ ' : v.state === 'unavailable' ? 'Not yet: ' : ''}{v.note}</span>
          </li>
        ))}
        {r.stage === 'paused' && <li className="pill" data-rollout-paused>Paused</li>}
        {r.stage === 'rolled_back' && <li className="pill" data-rollout-rolled-back>Rolled back</li>}
      </ol>
      {running && <p data-rollout-line><b>{canaryLine(r.rollouts)}</b></p>}
      {running && (
        <p className="note" data-rollout-counts>
          {r.counts.canary} cases on v{r.candidate_ver}, {r.counts.control} on v{r.base_ver}
        </p>
      )}
      {r.stage === 'paused' && rep?.paused && (
        <p className="mdl-msg blk" role="status" data-rollout-paused-banner>
          {rep.paused.automatic ? 'Paused automatically: ' : 'Paused: '}
          {rep.paused.reason}
        </p>
      )}
      {running && rep && (
        <table className="tbl" data-rollout-report aria-label="Canary against control">
          <thead>
            <tr><th scope="col" /><th scope="col">Canary</th><th scope="col">Control</th></tr>
          </thead>
          <tbody>
            {reportRows(rep).map(([label, a, b]) => (
              <tr key={label}><th scope="row">{label}</th><td>{a}</td><td>{b}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {running && rep && bandLine(rep) && <p className="note" data-rollout-band>{bandLine(rep)}</p>}
      {running && rep?.note && <p className="note" data-rollout-sample-note>{rep.note}.</p>}
      {!running && !r.replay_done && r.stage === 'shadow' && <p className="note" data-rollout-needs-replay>{r.can.startCanary}</p>}
      {err && <p className="mdl-msg blk" role="alert" data-rollout-refusal>{err}</p>}
      {(r.stage === 'shadow' || r.stage === 'rolled_back') && (
        <div className="mdl-row" data-rollout-start>
          <label className="sr" htmlFor="mdl-ro-region">Region</label>
          <input id="mdl-ro-region" value={region} placeholder="Region, e.g. FR" style={{ width: 140 }} onChange={(e) => setRegion(e.target.value)} />
          <label className="sr" htmlFor="mdl-ro-share">Share of volume, percent</label>
          <input id="mdl-ro-share" type="number" min={1} max={99} value={share} style={{ width: 80 }} onChange={(e) => setShare(e.target.value)} />
          <button type="button" className="btn sm pri" title={why('startCanary')} disabled={action.pending || !!r.can.startCanary || !region.trim()}
                  onClick={() => void go(() => startCanary(flowId, region.trim(), pct))}>
            Start canary
          </button>
        </div>
      )}
      {(r.stage === 'canary' || r.stage === 'paused') && (
        <>
          <div className="mdl-row" data-rollout-run>
            <label className="sr" htmlFor="mdl-ro-widen">New share, percent</label>
            <input id="mdl-ro-widen" type="number" min={1} max={99} value={share} style={{ width: 80 }} onChange={(e) => setShare(e.target.value)} />
            <button type="button" className="btn sm pri" title={why('widen')} disabled={action.pending || !!r.can.widen} onClick={() => void go(() => widenRollout(flowId, pct))}>
              {r.stage === 'paused' ? 'Resume at this share' : 'Widen'}
            </button>
            {r.stage === 'paused' && (
              <button type="button" className="btn sm pri" title={why('widen')} disabled={action.pending || !!r.can.widen}
                      onClick={() => void go(() => widenRollout(flowId, r.rollouts[0]?.share))}>
                Resume canary
              </button>
            )}
            <button type="button" className="btn sm pri" title={why('full')} disabled={action.pending || !!r.can.full} onClick={() => void go(() => goFull(flowId))}>
              Publish in full
            </button>
          </div>
          <div className="mdl-row" data-rollout-stop>
            <label className="sr" htmlFor="mdl-ro-reason">Reason</label>
            <input id="mdl-ro-reason" value={reason} placeholder="Why (15 characters or more)" style={{ width: 280 }} onChange={(e) => setReason(e.target.value)} />
            <button type="button" className="btn sm" title={why('pause')} disabled={action.pending || !!r.can.pause || !reasonOk} onClick={() => void go(() => pauseRollout(flowId, reason.trim()))}>
              Pause
            </button>
            <button type="button" className="btn sm" title={why('rollback')} disabled={action.pending || !!r.can.rollback || !reasonOk} onClick={() => void go(() => rollbackRollout(flowId, reason.trim()))}>
              Roll back
            </button>
          </div>
        </>
      )}
      {(r.can.widen || r.can.full) && running && <p className="note" data-rollout-why>{r.can.widen ?? r.can.full}</p>}
    </Panel>
  );
}
