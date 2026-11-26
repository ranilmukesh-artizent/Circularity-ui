import { runAutopilot } from '../../api/agentActivity';
import { can } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/**
 * "Run the agent on this case" (UI audit gap 15), for a Planner or Approver (permission runAgent). Propose only: the run
 * prepares work and the server holds every write of it for a person; it never approves or declines. The result is found
 * under Agent activity, in My work and in the assistant's "Waiting for you".
 */
export function RunAgentPanel({ caseId }: { caseId: string }) {
  const action = useAction();
  if (!can('runAgent')) return null;
  const run = async () => {
    const r = await action.run(() => runAutopilot(caseId));
    if (r.ok) toast('The agent is on it. Anything it prepares waits for a person.');
  };
  return (
    <section className="panel frp" aria-label="Run the agent">
      <div className="ph"><h3>Run the agent</h3></div>
      <div className="pb">
        <p className="note" style={{ marginTop: 0 }}>The agent reads {caseId} and prepares what comes next. It only proposes: nothing is approved or sent until a person accepts it.</p>
        <button type="button" className="btn sm" disabled={action.pending} onClick={run}>Run the agent on this case</button>
        {' '}<a className="btn sm ghost" href="#/agent-activity">Agent activity</a>
      </div>
    </section>
  );
}
