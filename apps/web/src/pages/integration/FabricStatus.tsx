/** A status pill on the Connection Fabric pages, from the demo's FR_ST table (frSt). */
import { KeyedStatus, type StatusTable } from '../../ui/kit/StatusPill';

const FR_ST: StatusTable = {
  completed: ['Completed', 'ok'], success: ['Success', 'ok'], published: ['Published', 'ok'], connected: ['Connected', 'ok'], live: ['Live', 'ok'], healthy: ['Healthy', 'ok'],
  progress: ['In progress', 'info'], running: ['Running', 'info'], syncing: ['Syncing', 'info'], investigating: ['Investigating', 'warn'], action: ['Action required', 'warn'],
  attention: ['Needs attention', 'warn'], stale: ['Stale', 'warn'], paused: ['Paused', 'warn'], warning: ['Warning', 'warn'], expiring: ['Expiring', 'warn'],
  failed: ['Failed', 'bad'], failing: ['Failing', 'bad'], unavailable: ['Not connected', 'bad'], escalated: ['Escalated', 'bad'], draft: ['Draft', 'line'],
  available: ['Available', 'line'], disconnected: ['Disconnected', 'line'], manual: ['Manual import', 'line'], ack: ['Acknowledged', 'line'], open: ['Open', 'warn'],
};

export const FabricStatus = ({ k, t }: { k: string; t?: string | null }) => <KeyedStatus k={k} t={t} table={FR_ST} />;
