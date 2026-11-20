/** Workflow actions shared by the list and a workflow's page: the demo's ACT.wf* adapters, each through invoke(). */
import { can } from '../../api/session';
import { fmtNumber } from '../../api/format';
import {
  duplicateWorkflow, exportJson, NOWF, runWorkflow, saveAsTemplate, setWorkflowStatus, workflow,
} from '../../api/workflows';
import { toast } from '../../ui/toast';
import { download } from './kit';

export const studioHref = (id?: string) => '/integration/studio' + (id ? '/' + id : '');

function refused(r: { ok: boolean; error?: { message: string } }): boolean {
  if (!r.ok) toast(r.error!.message, 4200);
  return !r.ok;
}

/** Pause, resume or publish from the list (ACT.wfToggle). */
export async function toggle(id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  const w = workflow(id);
  if (!w) return;
  const to = w.status === 'draft' ? 'published' : w.status === 'published' ? 'paused' : 'published';
  const r = await setWorkflowStatus(id, to);
  if (!r.ok) return toast(r.error.message, 4200);
  toast(r.output.was === 'draft' ? w.name + ' published.' : to === 'paused' ? w.name + ' paused. Scheduled runs stop until you resume it.' : w.name + ' resumed.');
}

/** Run now (ACT.wfRunNow). The backend finishes the run a few seconds later; this reports it like the demo does. */
export async function runNow(id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  const r = await runWorkflow(id);
  if (refused(r)) return;
  const t = window.setInterval(() => {
    const w = workflow(id);
    if (!w) return window.clearInterval(t);
    if (w.running) return;
    window.clearInterval(t);
    const l = w.last;
    if (l) toast(w.name + ': ' + (l.state === 'failed' ? 'run failed. ' + l.note : 'run finished, ' + fmtNumber(l.rows) + ' records.'), 4000);
  }, 250);
}

/** Duplicate (ACT.wfDup). Returns the copy's id. */
export async function duplicate(id: string): Promise<string | null> {
  if (!can('manageWorkflows')) { toast(NOWF()); return null; }
  const r = await duplicateWorkflow(id);
  if (refused(r) || !r.ok) return null;
  toast('Copy created as a draft: ' + r.output.name + '.');
  return r.output.id;
}

export function exportOne(id: string) {
  const x = exportJson(id);
  if (!x) return;
  download(x.file, x.json);
  toast(workflow(id)!.name + ' exported as JSON.');
}

export function saveTemplate(id: string) {
  if (!can('manageWorkflows')) return toast(NOWF());
  saveAsTemplate(id);
  toast('Saved as a template. It appears under New workflow.');
}

/** Bulk run, pause or export from the list (ACT.frWfBulk), each run and pause through invoke(). */
export async function bulk(a: 'run' | 'pause' | 'export', ids: string[]) {
  const L = ids.map((i) => workflow(i)).filter((w): w is NonNullable<typeof w> => !!w);
  if (a === 'export') {
    L.forEach((w) => { const x = exportJson(w.id); if (x) download(x.file, x.json); });
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

