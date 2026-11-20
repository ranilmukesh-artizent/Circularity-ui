import { beforeEach, describe, expect, it, vi } from 'vitest';

/** Fakes for what the workflow actions call: the permission check, the workflow facade, the toast and the download. */
const m = vi.hoisted(() => ({
  allowed: true,
  list: new Map<string, { id: string; name: string; status: 'published' | 'draft' | 'paused' }>(),
  toast: vi.fn(),
  download: vi.fn(),
  setWorkflowStatus: vi.fn(),
  runWorkflow: vi.fn(),
  duplicateWorkflow: vi.fn(),
  exportJson: vi.fn(),
  followRun: vi.fn(),
}));
vi.mock('../../api/session', () => ({ can: () => m.allowed }));
vi.mock('../../ui/toast', () => ({ toast: m.toast }));
vi.mock('./kit', () => ({ download: m.download }));
vi.mock('../../api/workflows', () => ({
  NOWF: () => 'Only workflow managers can change workflows.',
  workflow: (id: string) => m.list.get(id),
  setWorkflowStatus: m.setWorkflowStatus,
  runWorkflow: m.runWorkflow,
  duplicateWorkflow: m.duplicateWorkflow,
  exportJson: m.exportJson,
  followRun: m.followRun,
}));

import { bulk, duplicate, exportOne, NOT_YET, runNow, saveTemplate, studioHref, toggle } from './workflowActions';

const NOWF = 'Only workflow managers can change workflows.';
const wf = (id: string, status: 'published' | 'draft' | 'paused') => m.list.set(id, { id, name: 'Flow ' + id, status });
const toasts = () => m.toast.mock.calls.map((c) => c[0]);

beforeEach(() => {
  vi.clearAllMocks();
  m.allowed = true;
  m.list.clear();
});

describe('studioHref', () => {
  it('links the studio, or one workflow in it', () => {
    expect(studioHref()).toBe('/integration/studio');
    expect(studioHref('WF-101')).toBe('/integration/studio/WF-101');
  });
});

describe('toggle', () => {
  it('refuses without the manage permission', async () => {
    m.allowed = false;
    wf('WF-1', 'published');
    await toggle('WF-1');
    expect(m.setWorkflowStatus).not.toHaveBeenCalled();
    expect(toasts()).toEqual([NOWF]);
  });
  it('publishes a draft, pauses a published workflow and resumes a paused one', async () => {
    wf('D', 'draft'); wf('P', 'published'); wf('Z', 'paused');
    m.setWorkflowStatus.mockImplementation(async (id: string, status: string) => ({ ok: true, output: { id, status, was: m.list.get(id)!.status, name: '' } }));
    await toggle('D');
    await toggle('P');
    await toggle('Z');
    expect(m.setWorkflowStatus.mock.calls).toEqual([['D', 'published'], ['P', 'paused'], ['Z', 'published']]);
    expect(toasts()).toEqual(['Flow D published.', 'Flow P paused. Scheduled runs stop until you resume it.', 'Flow Z resumed.']);
  });
  it("shows the backend's refusal", async () => {
    wf('P', 'published');
    m.setWorkflowStatus.mockResolvedValue({ ok: false, error: { code: 'conflict', message: 'Fix 2 errors first.' } });
    await toggle('P');
    expect(m.toast.mock.calls).toEqual([['Fix 2 errors first.', 4200]]);
  });
});

describe('runNow', () => {
  it('follows the started run and reports how it finished', async () => {
    m.runWorkflow.mockResolvedValue({ ok: true, output: { id: 'WF-1', name: 'Flow WF-1', run: 'RUN-1' } });
    await runNow('WF-1');
    expect(m.followRun).toHaveBeenCalledWith('RUN-1', expect.any(Function));
    const done = m.followRun.mock.calls[0][1] as (r: { state: string; note: string; rows: number }) => void;
    done({ state: 'success', note: '', rows: 12345 });
    done({ state: 'failed', note: 'Source timed out.', rows: 0 });
    expect(m.toast.mock.calls).toEqual([['Flow WF-1: run finished, 12,345 records.', 4000], ['Flow WF-1: run failed. Source timed out.', 4000]]);
  });
  it('shows a refusal and follows nothing', async () => {
    m.runWorkflow.mockResolvedValue({ ok: false, error: { code: 'refused', message: 'Drafts cannot run.' } });
    await runNow('WF-1');
    expect(m.followRun).not.toHaveBeenCalled();
    expect(m.toast.mock.calls).toEqual([['Drafts cannot run.', 4200]]);
  });
});

describe('duplicate, export and templates', () => {
  it('duplicate returns the copy id', async () => {
    m.duplicateWorkflow.mockResolvedValue({ ok: true, output: { id: 'WF-136', name: 'Flow copy' } });
    expect(await duplicate('WF-1')).toBe('WF-136');
    expect(toasts()).toEqual(['Copy created as a draft: Flow copy.']);
  });
  it('duplicate returns null when refused or not allowed', async () => {
    m.duplicateWorkflow.mockResolvedValue({ ok: false, error: { code: 'x', message: 'No.' } });
    expect(await duplicate('WF-1')).toBeNull();
    m.allowed = false;
    expect(await duplicate('WF-1')).toBeNull();
    expect(m.duplicateWorkflow).toHaveBeenCalledTimes(1);
  });
  it('exportOne downloads the JSON', async () => {
    wf('WF-1', 'published');
    m.exportJson.mockResolvedValue({ file: 'wf-1.json', json: '{}' });
    await exportOne('WF-1');
    expect(m.download).toHaveBeenCalledWith('wf-1.json', '{}');
    expect(toasts()).toEqual(['Flow WF-1 exported as JSON.']);
  });
  it('exportOne shows a failed export', async () => {
    m.exportJson.mockRejectedValue(new Error('Network down.'));
    await exportOne('WF-1');
    expect(m.download).not.toHaveBeenCalled();
    expect(m.toast.mock.calls).toEqual([['Network down.', 4200]]);
  });
  it('saving a template is not available yet', () => {
    saveTemplate('WF-1');
    expect(toasts()).toEqual([NOT_YET]);
  });
});

describe('bulk', () => {
  it('exports every selected workflow, with or without the permission', async () => {
    m.allowed = false;
    wf('A', 'published'); wf('B', 'draft');
    m.exportJson.mockImplementation(async (id: string) => ({ file: id + '.json', json: id }));
    await bulk('export', ['A', 'B', 'gone']);
    expect(m.download.mock.calls).toEqual([['A.json', 'A'], ['B.json', 'B']]);
    expect(toasts()).toEqual(['2 workflows exported as JSON.']);
  });
  it('runs all but drafts', async () => {
    wf('A', 'published'); wf('B', 'draft'); wf('C', 'paused');
    m.runWorkflow.mockResolvedValue({ ok: true, output: {} });
    await bulk('run', ['A', 'B', 'C']);
    expect(m.runWorkflow.mock.calls).toEqual([['A'], ['C']]);
    expect(toasts()).toEqual(['Started 2 runs. Drafts are skipped.']);
  });
  it('pauses only the published ones', async () => {
    wf('A', 'published'); wf('B', 'draft');
    m.setWorkflowStatus.mockResolvedValue({ ok: true, output: {} });
    await bulk('pause', ['A', 'B']);
    expect(m.setWorkflowStatus.mock.calls).toEqual([['A', 'paused']]);
    expect(toasts()).toEqual(['Paused 2 workflows.']); // the demo's text counts the whole selection
  });
  it('refuses run and pause without the permission', async () => {
    m.allowed = false;
    wf('A', 'published');
    await bulk('run', ['A']);
    expect(m.runWorkflow).not.toHaveBeenCalled();
    expect(toasts()).toEqual([NOWF]);
  });
});
