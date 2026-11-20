/** Workflow actions shared by the list and a workflow's page: the demo's ACT.wf* adapters, each through invoke(). */
import { can } from '../../api/session';
import { fmtNumber } from '../../api/format';
import {
  duplicateWorkflow, exportJson, followRun, NOWF, runWorkflow, setWorkflowStatus, workflow,
} from '../../api/workflows';
import { toast } from '../../ui/toast';
import { refused } from '../../ui/useAction';
import { download } from '../../lib/download';

export const studioHref = (id?: string) => '/integration/studio' + (id ? '/' + id : '');
/** A change the backend has no action for yet. */
export const NOT_YET = 'Not available yet.';

/** Pause, resume or publish from the list (ACT.wfToggle). */
export async function toggle(id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  const w = workflow(id);
  if (!w) return;
  const to = w.status === 'draft' ? 'published' : w.status === 'published' ? 'paused' : 'published';
  const r = await setWorkflowStatus(id, to);
  if (refused(r, 4200)) return;
  toast(r.output.was === 'draft' ? w.name + ' published.' : to === 'paused' ? w.name + ' paused. Scheduled runs stop until you resume it.' : w.name + ' resumed.');
}

const finished = (name: string, l: { state: string; note: string; rows: number }) =>
  toast(name + ': ' + (l.state === 'failed' ? 'run failed. ' + l.note : 'run finished, ' + fmtNumber(l.rows) + ' records.'), 4000);

/** Run now (ACT.wfRunNow). The backend finishes the run a few seconds later; this reports it like the demo does. */
export async function runNow(id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  const r = await runWorkflow(id);
  if (refused(r, 4200)) return;
  // the run is a worker job; its record (by the run key) reports progress on the stream
  if (r.output.run) followRun(r.output.run, (x) => finished(r.output.name, x));
}

/** Duplicate (ACT.wfDup). Returns the copy's id. */
export async function duplicate(id: string): Promise<string | null> {
  if (!can('manageWorkflows')) { toast(NOWF()); return null; }
  const r = await duplicateWorkflow(id);
  if (refused(r, 4200)) return null;
  toast('Copy created as a draft: ' + r.output.name + '.');
  return r.output.id;
}

export async function exportOne(id: string) {
  const x = await exportJson(id).catch((err: Error) => void toast(err.message, 4200));
  if (!x) return;
  download(x.file, x.json);
  toast(workflow(id)!.name + ' exported as JSON.');
}

export function saveTemplate(_id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  toast(NOT_YET); // no backend action saves a template yet
}

/** Bulk run, pause or export from the list (ACT.frWfBulk), each run and pause through invoke(). */
export async function bulk(a: 'run' | 'pause' | 'export', ids: string[]) {
  const L = ids.map((i) => workflow(i)).filter((w): w is NonNullable<typeof w> => !!w);
  if (a === 'export') {
    for (const w of L) { const x = await exportJson(w.id).catch(() => null); if (x) download(x.file, x.json); }
    return toast(L.length + ' workflow' + (L.length > 1 ? 's' : '') + ' exported as JSON.');
  }
  if (!can('manageWorkflows')) return toast(NOWF());
  if (a === 'run') {
    let n = 0;
    for (const w of L) if (w.status !== 'draft' && (await runWorkflow(w.id)).ok) n++;
    toast('Started ' + n + ' run' + (L.length > 1 ? 's' : '') + '. Drafts are skipped.');
  } else {
    L.filter((w) => w.status === 'published').forEach((w) => setWorkflowStatus(w.id, 'paused'));
    toast('Paused ' + L.length + ' workflow' + (L.length > 1 ? 's' : '') + '.');
  }
}
