import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { exportJson } from './workflows';

beforeEach(() => m.invoke.mockReset());

describe('exportJson (P9-0.8)', () => {
  it('maps the action result to the same file name and JSON text as before', async () => {
    const out = { id: 'WF-3', name: 'ERP ingest (v2)', version: '1.0', steps: [], links: [] };
    m.invoke.mockResolvedValue({ ok: true, output: out, key: null, action: 'workflow.export' });
    const x = await exportJson('WF-3');
    expect(m.invoke).toHaveBeenCalledWith('workflow.export', { workflow_id: 'WF-3' });
    expect(x).toEqual({ file: 'WF-3-erp-ingest-v2-.json', json: JSON.stringify(out, null, 2) });
  });

  it('gives null for a workflow the server does not know', async () => {
    m.invoke.mockResolvedValue({ ok: false, error: { code: 'not_found', message: 'No workflow WF-9.' } });
    expect(await exportJson('WF-9')).toBeNull();
  });
});
