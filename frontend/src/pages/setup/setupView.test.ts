import { describe, expect, it } from 'vitest';
import type { Composition, CompositionStatus, CompositionStep, StepState } from '../../api/compose';
import { filterPacks, suggestPack, compositionLabel, currentStep, doneCount, hasPublished, isStep, isStop, lineOf, live, neighbours, nextAction, orgName, PAGE_HANDOVER, PAGE_STOPS, pageStops, partLine, pick, screenFor, screenOf, setupPath, stops, stopStates, STEPS } from './setupView';

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

describe('the seven stops', () => {
  it('stay in the data, with access and flow among them', () => {
    expect(PAGE_STOPS.map((s) => s.id)).toEqual(['describe', 'flow', 'mapping', 'agents', 'access', 'approve', 'publish']);
    expect(isStop('flow')).toBe(true);
    expect(isStop('access')).toBe(true);
    expect(isStop('nope')).toBe(false);
    expect(isStop(null)).toBe(false);
  });
  it('without a setup only the template is next', () => {
    expect(stopStates(null).map((s) => s.state)).toEqual(['now', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo']);
  });
  it('the flow stop says whether the flow was changed', () => {
    const c = comp(1, 'draft', { describe: 'done' });
    const flow = (st?: string) => stopStates(c, st)[1];
    expect(flow()).toMatchObject({ state: 'todo', note: 'As the template' });
    expect(flow('pub')).toMatchObject({ state: 'todo', note: 'As the template' });
    expect(flow('draft')).toMatchObject({ state: 'done', note: 'Changed' });
    expect(flow('review')).toMatchObject({ state: 'done', note: 'In review' });
    expect(flow('shadow')).toMatchObject({ state: 'done', note: 'In shadow' });
  });
  it('the flow stop is done once the person went on past it', () =>
    expect(stopStates(comp(1, 'draft', { describe: 'done', mapping: 'done' }), 'pub')[1].state).toBe('done'));
  it('the access stop is done once the setup went to its approver', () => {
    expect(stopStates(comp(1, 'draft'))[4].state).toBe('todo');
    expect(stopStates(comp(1, 'submitted'))[4].state).toBe('done');
  });
});

describe('the route line (five stops)', () => {
  it('has Business flow, Systems, Agents, Approve, Publish; the maker hands over after the third', () => {
    expect(pageStops(null).map((s) => s.label)).toEqual(['Business flow', 'Systems', 'Agents', 'Approve', 'Publish']);
    expect(pageStops(null).map((s) => s.id)).toEqual(['describe', 'mapping', 'agents', 'approve', 'publish']);
    expect(PAGE_HANDOVER).toBe(3);
  });
  it('without a setup only Business flow is next', () => expect(pageStops(null).map((s) => s.state)).toEqual(['now', 'todo', 'todo', 'todo', 'todo']));
  it('Business flow is done only when the template and the flow both are', () => {
    const c = comp(1, 'draft', { describe: 'done' });
    expect(pageStops(c, 'pub')[0]).toMatchObject({ state: 'todo' });
    expect(pageStops(c, 'pub')[1].state).toBe('now');
    expect(pageStops(c, 'draft')[0]).toMatchObject({ state: 'done', note: 'Done' });
    expect(pageStops(comp(1, 'draft', { describe: 'done', mapping: 'done' }), 'pub')[0].state).toBe('done');
  });
  it('Business flow is now while the template is the next step', () => expect(pageStops(comp(1, 'draft'), 'pub')[0].state).toBe('now'));
  it('Approve is done when the access check and the approval both are', () => {
    const approved = comp(1, 'approved', { describe: 'done', mapping: 'done', agents: 'done', approve: 'done' });
    expect(pageStops(approved, 'shadow')[3].state).toBe('done');
    expect(pageStops(comp(1, 'draft', { describe: 'done', mapping: 'done', agents: 'done' }), 'draft')[3].state).toBe('now');
    expect(pageStops(comp(1, 'submitted', { describe: 'done', mapping: 'done', agents: 'done' }), 'draft')[3]).toMatchObject({ state: 'now', note: 'Waiting' });
  });
  it('a stop sent back shows as sent back', () => {
    const line = pageStops(comp(1, 'sent_back', { describe: 'done', mapping: 'sent_back' }), 'pub');
    expect(line.map((s) => [s.label, s.state])).toEqual([['Business flow', 'todo'], ['Systems', 'back'], ['Agents', 'todo'], ['Approve', 'todo'], ['Publish', 'todo']]);
  });
  it('a published setup has every stop done', () => expect(pageStops(comp(1, 'published'), 'pub').every((s) => s.state === 'done')).toBe(true));
  it('doneCount counts the five of the line', () => {
    expect(doneCount(comp(1, 'published'))).toBe(5);
    expect(doneCount(null)).toBe(0);
  });
});

describe('old links and the screen in view', () => {
  it('step=access opens Approve, where Access is the first section', () => {
    expect(screenOf('access')).toBe('approve');
    expect(screenFor(comp(1, 'draft'), 'access')).toBe('approve');
  });
  it('step=describe and step=flow open their own screens', () => {
    expect(screenFor(comp(1, 'draft', { describe: 'done' }), 'describe')).toBe('describe');
    expect(screenFor(comp(1, 'draft'), 'flow')).toBe('flow');
  });
  it('no step, or one that is not a step, opens the next step; without a setup, the template', () => {
    expect(screenFor(comp(1, 'draft', { describe: 'done' }), null)).toBe('mapping');
    expect(screenFor(comp(1, 'draft', { describe: 'done' }), 'nope')).toBe('mapping');
    expect(screenFor(null, 'publish')).toBe('describe');
  });
  it('every stop sits under a stop of the line', () => {
    expect(PAGE_STOPS.map((s) => lineOf(s.id))).toEqual(['describe', 'describe', 'mapping', 'agents', 'approve', 'approve', 'publish']);
  });
  it('Business flow has two parts; the others have none', () => {
    expect(partLine('describe')).toBe('Part 1 of 2');
    expect(partLine('flow')).toBe('Part 2 of 2');
    expect(partLine('approve')).toBeNull();
    expect(partLine('access')).toBeNull();
  });
});

describe('Back and Next', () => {
  it('walk the six screens, the two of Business flow first', () => {
    expect(neighbours('describe')).toEqual({ prev: null, next: 'flow' });
    expect(neighbours('flow')).toEqual({ prev: 'describe', next: 'mapping' });
    expect(neighbours('mapping')).toEqual({ prev: 'flow', next: 'agents' });
    expect(neighbours('agents')).toEqual({ prev: 'mapping', next: 'approve' });
    expect(neighbours('publish')).toEqual({ prev: 'approve', next: null });
  });
  it('an old access link has the neighbours of Approve', () => expect(neighbours('access')).toEqual({ prev: 'agents', next: 'publish' }));
  it('builds the path of a stop', () => {
    expect(setupPath({ compose: 12, step: 'flow' })).toBe('/setup?compose=12&step=flow');
    expect(setupPath({ pack: 'tool_fleet', fresh: true })).toBe('/setup?new=1&pack=tool_fleet');
  });
});

describe('the template picker', () => {
  const cards = [
    { key: 'industrial', name: 'Industrial returns', industry: 'Industrial', unit: 'asset', classes: ['Motor', 'Pump', 'Drill'] },
    { key: 'tool_fleet', name: 'Tool fleet returns', industry: 'Tools', unit: 'tool', classes: ['Combihammer, 12 kg class', 'Demolition breaker, 30 kg'] },
    { key: 'device', name: 'Device recommerce', industry: 'Devices', unit: 'device', classes: ['Phone', 'Tablet'] },
  ];
  it('a search keeps the templates that hold every word typed', () => {
    expect(filterPacks(cards, '').map((p) => p.key)).toEqual(['industrial', 'tool_fleet', 'device']);
    expect(filterPacks(cards, 'phone').map((p) => p.key)).toEqual(['device']);
    expect(filterPacks(cards, 'fleet tool').map((p) => p.key)).toEqual(['tool_fleet']);
    expect(filterPacks(cards, 'submarine')).toEqual([]);
  });
  it('offers another template when the words read like it', () => {
    expect(suggestPack('We lease a fleet of cordless tools and breakers to building sites', cards, 'industrial')?.key).toBe('tool_fleet');
    expect(suggestPack('We buy back used phones and tablets in store', cards, 'industrial')?.key).toBe('device');
  });
  it('offers nothing for the chosen template, a short text or shared words only', () => {
    expect(suggestPack('We lease a fleet of cordless tools and breakers to building sites', cards, 'tool_fleet')).toBeNull();
    expect(suggestPack('tools', cards, 'industrial')).toBeNull();
    expect(suggestPack('Our returns come back from many customers every week', cards, 'industrial')).toBeNull();
  });
});
