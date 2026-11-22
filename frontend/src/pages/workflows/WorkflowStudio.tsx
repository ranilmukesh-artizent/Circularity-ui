/**
 * Workflow Studio (#/integration/studio, #/integration/studio/WF-101): the workflow list and a workflow's own page
 * with its canvas. Rendered by the `integration` page dispatcher (src/pages/integration/) inside the Connection
 * Fabric frame. CONTRACT: keep this export name and props; the workflows area owns everything behind it.
 */
import { useBackend } from '../../api/useBackend';
import { canPage } from '../../api/session';
import { WorkflowList } from './WorkflowList';
import { WorkflowPage } from './WorkflowPage';

export function WorkflowStudio({ workflowId, query }: { workflowId: string | null; query: URLSearchParams }) {
  useBackend();
  if (!canPage('integration', 'studio')) return <p className="note">Workflow Studio is not available for your role.</p>;
  return workflowId ? <WorkflowPage id={workflowId} query={query} /> : <WorkflowList query={query} />;
}
