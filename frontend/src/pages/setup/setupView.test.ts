import { describe, expect, it } from 'vitest';
import type { Composition, CompositionStatus, CompositionStep, StepState } from '../../api/compose';
import { compositionLabel, currentStep, doneCount, hasPublished, isStep, isStop, live, neighbours, nextAction, orgName, PAGE_HANDOVER, PAGE_STOPS, pageStops, pick, setupPath, stops, STEPS } from './setupView';

const ORDER: CompositionStep[] = ['describe', 'mapping', 'agents', 'approve', 'publish'];
function comp(id: number, status: CompositionStatus, states: Partial<Record<CompositionStep, StepState['state']>> = {}, org = 'customer_a'): Composition {
  const steps = {} as Record<CompositionStep, StepState>;
  for (const s of ORDER) steps[s] = { state: states[s] ?? 'todo' };
  return { id, org_unit_id: org, pack_key: 'tool_fleet', status, steps } as unknown as Composition;
}

describe('currentStep', () => {
  it('is describe without a composition', () => expect(currentStep(null)).toBe('describe'));
  it('is the first step not done', () => {
    expect(currentStep(comp(1, 'draft'))).toBe('describe');
    expect(currentStep(comp(1, 'draft', { describe: 'done' }))).toBe('mapping');
    expect(currentStep(comp(1, 'draft', { describe: 'done', mapping: 'done', agents: 'done' }))).toBe('approve');
  });
  it('is publish once all else is done, or when published', () => {
    expect(currentStep(comp(1, 'approved', { describe: 'done', mapping: 'done', agents: 'done', approve: 'done' }))).toBe('publish');
    expect(currentStep(comp(1, 'published'))).toBe('publish');
  });
  it('stops at a sent back step', () => expect(currentStep(comp(1, 'sent_back', { describe: 'done', mapping: 'sent_back' }))).toBe('mapping'));
});

describe('stops and doneCount', () => {
  it('has five stops, only Describe next, without a composition', () => {
    const s = stops(null);
    expect(s.map((x) => x.id)).toEqual(ORDER);
    expect(s.map((x) => x.state)).toEqual(['now', 'todo', 'todo', 'todo', 'todo']);
    expect(s[0].note).toBe('Next');
    expect(s[1].note).toBe('Not started');
    expect(doneCount(null)).toBe(0);
  });
  it('marks done and sent back', () => {
    const s = stops(comp(1, 'sent_back', { describe: 'done', mapping: 'sent_back' }));
    expect(s.map((x) => x.state)).toEqual(['done', 'back', 'todo', 'todo', 'todo']);
    expect(s[1].note).toBe('Sent back');
    expect(doneCount(comp(1, 'draft', { describe: 'done', mapping: 'done' }))).toBe(2);
  });
  it('marks the first step not done as now', () => {
    const s = stops(comp(1, 'draft', { describe: 'done' }));
    expect(s.map((x) => x.state)).toEqual(['done', 'now', 'todo', 'todo', 'todo']);
  });
  it('says Waiting on Approve while submitted', () => {
    const s = stops(comp(1, 'submitted', { describe: 'done', mapping: 'done', agents: 'done' }));
    expect(s[3]).toMatchObject({ state: 'now', note: 'Waiting' });
  });
  it('has every stop done when published', () => {
    expect(stops(comp(1, 'published')).every((x) => x.state === 'done')).toBe(true);
    expect(doneCount(comp(1, 'published'))).toBe(5);
  });
});

describe('nextAction', () => {
  it('starts with the template', () => expect(nextAction(null)).toEqual({ step: 'describe', label: 'Choose a template' }));
  it('names the step', () => {
    expect(nextAction(comp(1, 'draft'))).toEqual({ step: 'describe', label: 'Review the draft' });
    expect(nextAction(comp(1, 'draft', { describe: 'done' }))).toEqual({ step: 'mapping', label: 'Connect your systems' });
    expect(nextAction(comp(1, 'draft', { describe: 'done', mapping: 'done' }))).toEqual({ step: 'agents', label: 'Set your agents' });
    expect(nextAction(comp(1, 'draft', { describe: 'done', mapping: 'done', agents: 'done' }))).toEqual({ step: 'approve', label: 'Send for approval' });
    expect(nextAction(comp(1, 'submitted', { describe: 'done', mapping: 'done', agents: 'done' }))).toEqual({ step: 'approve', label: 'See the approval' });
    expect(nextAction(comp(1, 'approved', { describe: 'done', mapping: 'done', agents: 'done', approve: 'done' }))).toEqual({ step: 'publish', label: 'Publish' });
    expect(nextAction(comp(1, 'published'))).toEqual({ step: 'publish', label: 'Open the published setup' });
  });
  it('points at a sent back step first', () =>
    expect(nextAction(comp(1, 'sent_back', { describe: 'done', mapping: 'done', agents: 'sent_back' }))).toEqual({ step: 'agents', label: 'See what was sent back' }));
});

describe('live, hasPublished, pick', () => {
  const all = [comp(1, 'draft'), comp(5, 'discarded'), comp(3, 'published', {}, 'customer_b'), comp(2, 'draft', {}, 'customer_b')];
  it('drops discarded and sorts newest first', () => expect(live(all).map((c) => c.id)).toEqual([3, 2, 1]));
  it('knows whether one is published', () => {
    expect(hasPublished(all)).toBe(true);
    expect(hasPublished([comp(1, 'draft')])).toBe(false);
    expect(hasPublished([])).toBe(false);
  });
  it('picks the one asked for, else the newest, else the newest of the org', () => {
    expect(pick(all, 1)?.id).toBe(1);
    expect(pick(all, 5)).toBeNull();
    expect(pick(all, 99)).toBeNull();
    expect(pick(all, null)?.id).toBe(3);
    expect(pick(all, null, 'customer_a')?.id).toBe(1);
    expect(pick(all, null, 'nowhere')).toBeNull();
    expect(pick([], null)).toBeNull();
  });
});

describe('setupPath, isStep, compositionLabel', () => {
  it('builds the path', () => {
    expect(setupPath()).toBe('/setup');
    expect(setupPath({ compose: 12, step: 'mapping' })).toBe('/setup?compose=12&step=mapping');
    expect(setupPath({ fresh: true })).toBe('/setup?new=1');
    expect(setupPath({ compose: 0 })).toBe('/setup?compose=0');
    expect(setupPath({ org: 'customer_a', compose: null, step: null })).toBe('/setup?org=customer_a');
  });
  it('knows the steps', () => {
    for (const s of STEPS) expect(isStep(s.id)).toBe(true);
    expect(isStep('nope')).toBe(false);
    expect(isStep(null)).toBe(false);
    expect(isStep('')).toBe(false);
  });
  it('labels a composition', () => {
    expect(compositionLabel(comp(12, 'sent_back'))).toBe('Setup 12, tool fleet for Customer a, sent back');
    expect(compositionLabel(comp(12, 'draft'), 'Tool fleet')).toBe('Setup 12, Tool fleet for Customer a, draft');
  });
});

describe('orgName', () => {
  it('capitalises and spaces an org id', () => {
    expect(orgName('workspace')).toBe('Workspace');
    expect(orgName('customer_a')).toBe('Customer a');
    expect(orgName('Customer A')).toBe('Customer A');
    expect(orgName('north-east__depot')).toBe('North east depot');
    expect(orgName('')).toBe('');
  });
});

describe('the page line (seven stops)', () => {
  it('has the five stops of the maker, then approve and publish', () => {
    expect(PAGE_STOPS.map((s) => s.id)).toEqual(['describe', 'flow', 'mapping', 'agents', 'access', 'approve', 'publish']);
    expect(PAGE_STOPS[PAGE_HANDOVER].id).toBe('approve');
    expect(isStop('flow')).toBe(true);
    expect(isStop('nope')).toBe(false);
    expect(isStop(null)).toBe(false);
  });
  it('without a setup only the template is next', () => {
    expect(pageStops(null).map((s) => s.state)).toEqual(['now', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo']);
  });
  it('the flow stop says whether the flow was changed', () => {
    const c = comp(1, 'draft', { describe: 'done' });
    const flow = (st?: string) => pageStops(c, st)[1];
    expect(flow()).toMatchObject({ state: 'todo', note: 'As the template' });
    expect(flow('pub')).toMatchObject({ state: 'todo', note: 'As the template' });
    expect(flow('draft')).toMatchObject({ state: 'done', note: 'Changed' });
    expect(flow('review')).toMatchObject({ state: 'done', note: 'In review' });
    expect(flow('shadow')).toMatchObject({ state: 'done', note: 'In shadow' });
  });
  it('keeps the states of the five steps under the names of the page', () => {
    const line = pageStops(comp(1, 'sent_back', { describe: 'done', mapping: 'sent_back' }), 'pub');
    expect(line.map((s) => [s.label, s.state])).toEqual([
      ['Template', 'done'], ['Shape the flow', 'todo'], ['Connect systems', 'back'], ['Set agents', 'todo'], ['Access', 'todo'], ['Approve', 'todo'], ['Publish', 'todo'],
    ]);
  });
  it('a published setup has every stop done', () => {
    expect(pageStops(comp(1, 'published'), 'pub').every((s) => s.state === 'done')).toBe(true);
  });
  it('walks the line both ways', () => {
    expect(neighbours('describe')).toEqual({ prev: null, next: 'flow' });
    expect(neighbours('access')).toEqual({ prev: 'agents', next: 'approve' });
    expect(neighbours('publish')).toEqual({ prev: 'approve', next: null });
  });
  it('builds the path of a stop', () => {
    expect(setupPath({ compose: 12, step: 'flow' })).toBe('/setup?compose=12&step=flow');
    expect(setupPath({ pack: 'tool_fleet', fresh: true })).toBe('/setup?new=1&pack=tool_fleet');
  });
});
