/**
 * "Agents on this" (plan 10, sections 2.6 and 2.8): the latest agent run for the case in context, read with
 * `agent.runTrace {case_id}`: who ran, what it is doing now (the journey stage's status), and View the run. A person with
 * `manageAgents` can Pause the agent (`agent.setEnabled`, the existing kill switch). Shown only on a case.
 */
import { Suspense } from 'react';
import { runTrace, setAgentEnabled, type JourneyStatus, type RunTrace } from '../../api/agents';
import { can } from '../../api/session';
import { ErrorBoundary } from '../../components/Boundary';
import { Icon } from '../../components/Icon';
import { runHref } from '../../components/ProposalRow';
import { useAction } from '../../hooks/useAction';

const STATUS_CHIP: Partial<Record<JourneyStatus, string>> = { Completed: 'ok', Running: 'line', 'Waiting for approval': 'y', Warning: 'warn', Failed: 'bad' };

/** The journey stage the run is at: the running one, else one waiting for approval, else the last one reached. */
export function currentStage(t: Pick<RunTrace, 'journey'>): { name: string; status: JourneyStatus } | null {
  const j = t.journey;
  const hit = j.find((s) => s.status === 'Running') ?? j.find((s) => s.status === 'Waiting for approval') ?? [...j].reverse().find((s) => s.status !== 'Queued');
  return hit ? { name: hit.name, status: hit.status } : null;
}

function Row({ caseId }: { caseId: string }) {
  const t = runTrace({ caseId });
  const act = useAction();
  const run = t.run;
  if (!run) return null;
  const stage = currentStage(t);
  const paused = t.pauses.length ? !t.pauses[t.pauses.length - 1].on : false;
  return (
    <section className="as-sec as-agents" aria-label="Agents on this">
      <h3 className="as-sec-t">Agents on this</h3>
      <div className="as-row">
        <Icon name="bot" />
        <span>
          <b>{run.agentName}</b> <span className="note">on {caseId}</span>
          <span className="note">
            {stage ? <>{stage.name} · <span className={'chip ' + (STATUS_CHIP[stage.status] ?? 'line')}>{stage.status}</span></> : <>Run {run.status}</>}
            {paused && ' · paused'}
          </span>
          <span className="row">
            <a className="btn sm ghost" href={runHref(run.id)}>View the run</a>
            {can('manageAgents') && (
              <button type="button" className="btn sm" disabled={act.pending || paused || run.status === 'done'} onClick={() => act.run(() => setAgentEnabled(run.agent, false))}>
                Pause agent
              </button>
            )}
          </span>
        </span>
      </div>
    </section>
  );
}

export function AgentsOnThis({ caseId }: { caseId?: string }) {
  if (!caseId) return null;
  return (
    <ErrorBoundary resetKey={caseId}>
      <Suspense fallback={null}>
        <Row caseId={caseId} />
      </Suspense>
    </ErrorBoundary>
  );
}
