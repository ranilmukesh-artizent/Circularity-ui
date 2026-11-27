import { describe, expect, it } from 'vitest';
import { askContext, contextOf, contextParts } from './context';
import type { FlowSurface } from '../../utils/workSurface';

const flowSurface = { kind: 'flow', flowId: 7, name: 'Industrial returns', template: 'industrial', org: 'workspace', canEdit: true, draftVer: 2 } as FlowSurface;

describe('contextOf', () => {
  it('reads a case id from the route', () => {
    const c = contextOf({ page: 'product', a: 'asset', b: 'RT-1048' }, null, 'planner');
    expect(c).toMatchObject({ page: 'product', section: 'asset', caseId: 'RT-1048', role: 'planner' });
    expect(contextParts(c)).toContain('Case: RT-1048');
  });
  it('is home when the route is empty', () => {
    expect(contextOf({ page: '', a: null, b: null }, null, 'admin').page).toBe('home');
  });
  it('takes the flow from the registered surface, and sends the template as the Ask section', () => {
    const c = contextOf({ page: 'modeler', a: null, b: null }, flowSurface, 'admin');
    expect(c.flow).toEqual({ id: 7, name: 'Industrial returns', template: 'industrial', org: 'workspace', canEdit: true, draftVer: 2 });
    expect(askContext(c)).toEqual({ page: 'modeler', section: 'industrial', case_id: undefined, object: { kind: 'flow', id: '7', label: 'Industrial returns' }, org: 'workspace' });
    expect(contextParts(c)).toEqual(['Modeler', 'Flow: Industrial returns', 'Org: workspace', 'Draft v2']);
  });
  it('takes the pack and org from a compose surface', () => {
    const c = contextOf({ page: 'modeler', a: null, b: null }, { kind: 'compose', id: 3, org: 'workspace', pack: 'industrial' }, 'admin');
    expect(c).toMatchObject({ pack: 'industrial', org: 'workspace', composeId: 3 });
    expect(c.flow).toBeUndefined();
    expect(contextParts(c)).toEqual(['Modeler', 'Pack: industrial', 'Org: workspace', 'Composition 3']);
    expect(askContext(c)).toMatchObject({ object: { kind: 'composition', id: '3' }, org: 'workspace' });
  });
  it('sends a case as the page object', () => {
    const c = contextOf({ page: 'product', a: 'asset', b: 'RT-1048' }, null, 'planner');
    expect(askContext(c)).toEqual({ page: 'product', section: 'asset', case_id: 'RT-1048', object: { kind: 'case', id: 'RT-1048' } });
  });
  it('sends a workflow from /integration/studio/WF-nnn', () => {
    const c = contextOf({ page: 'integration', a: 'studio', b: 'WF-103' }, null, 'admin');
    expect(c.workflowId).toBe('WF-103');
    expect(askContext(c).object).toEqual({ kind: 'workflow', id: 'WF-103' });
    expect(contextParts(c)).toContain('Workflow: WF-103');
  });
  it('sends a run id from the route', () => {
    const c = contextOf({ page: 'integration', a: 'runs', b: 'RUN-AB12Z' }, null, 'admin');
    expect(askContext(c).object).toEqual({ kind: 'run', id: 'RUN-AB12Z' });
  });
});
