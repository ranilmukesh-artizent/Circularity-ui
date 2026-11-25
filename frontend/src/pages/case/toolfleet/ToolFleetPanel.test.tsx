// @vitest-environment jsdom
// Plan 9, P9-3.5 (TF-03): the tool fleet panel's grade line, workbench and estimate.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ToolFleetView } from '../../../api/toolFleet';
import { GradeSection, gradeLine } from './GradeSection';
import { ToolFleetPanel } from './ToolFleetPanel';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const m = vi.hoisted(() => ({ view: null as unknown }));
vi.mock('../../../api/toolFleet', () => ({ toolFleetView: () => m.view }));

const view = (grade: ToolFleetView['grade']): ToolFleetView => ({
  case_id: 'RT-1', pack_version: '3.2.0', flow: 'returns', grade, gates: [], quarantine: null, life: null, paths: [], plan: null, approval: null,
  followThrough: null,
});
const WORKBENCH = { grade: 'B', source: 'workbench', ref: 'DR-50412', at: '2026-10-07T03:00:00+00:00', age_hours: 6 } as const;
const ESTIMATE = { grade: 'C', source: 'estimate', ref: null, at: null, age_hours: null } as const;

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const text = (ui: React.ReactNode) => {
  act(() => root.render(ui));
  return host.textContent ?? '';
};

describe('grade line', () => {
  it('names the workbench reference and how long ago it was graded', () => {
    expect(gradeLine(WORKBENCH)).toBe('Grade B · workbench DR-50412 · graded 6 h ago');
    expect(gradeLine({ ...WORKBENCH, age_hours: 0.4 })).toBe('Grade B · workbench DR-50412 · graded just now');
    expect(gradeLine({ ...WORKBENCH, age_hours: 50 })).toBe('Grade B · workbench DR-50412 · graded 2 d ago');
  });
  it('says an estimate is an estimate', () => {
    expect(gradeLine(ESTIMATE)).toBe('Grade C · estimate (workbench grade not in yet)');
  });
});

describe('ToolFleetPanel', () => {
  it('shows the Estimate chip for an estimate view', () => {
    m.view = view(ESTIMATE);
    const t = text(<ToolFleetPanel caseId="RT-1" />);
    expect(t).toContain('estimate (workbench grade not in yet)');
    expect(host.querySelector('.chip')?.textContent).toBe('Estimate');
  });
  it('shows the reference for a workbench view, with no chip', () => {
    m.view = view(WORKBENCH);
    const t = text(<ToolFleetPanel caseId="RT-1" />);
    expect(t).toContain('workbench DR-50412');
    expect(host.querySelector('.chip')).toBeNull();
  });
  it('the section alone draws the same line', () => {
    expect(text(<GradeSection grade={WORKBENCH} />)).toContain('Grade B · workbench DR-50412 · graded 6 h ago');
  });
});
