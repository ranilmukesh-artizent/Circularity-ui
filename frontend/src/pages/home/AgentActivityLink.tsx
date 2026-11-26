import { canPage } from '../../api/session';
import { Panel } from '../../components/kit/Panel';

/** Home's link to the read-only Agent activity page (UI audit gap 12), for every role that may open it. */
export function AgentActivityLink() {
  if (!canPage('agent-activity')) return null;
  return (
    <Panel title="Agent activity" id="frAgentActivity" sub="What the agents did on your cases">
      <a className="btn sm" href="#/agent-activity">Open agent activity</a>
    </Panel>
  );
}
