import { describe, expect, it } from 'vitest';
import { liveShare, OPENED, publishChecks } from './publishView';

const states = (...a: Parameters<typeof publishChecks>) => publishChecks(...a).map((c) => c.state);

describe('publishChecks', () => {
  it('the approval and the flow can move from the start; the replay waits for a draft', () => {
    expect(states('draft', 'pub', false)).toEqual(['now', 'now', 'todo', 'todo']);
    expect(states('submitted', 'draft', false)).toEqual(['now', 'now', 'now', 'todo']);
  });
  it('an approved setup waits for its flow to reach shadow', () => {
    expect(states('approved', 'pub', false)).toEqual(['done', 'now', 'todo', 'todo']);
    expect(states('approved', 'review', false)).toEqual(['done', 'now', 'now', 'todo']);
  });
  it('a replay run early is done as soon as it has a report', () => {
    expect(states('approved', 'draft', true)).toEqual(['done', 'now', 'done', 'todo']);
    expect(states('draft', 'draft', true)).toEqual(['now', 'now', 'done', 'todo']);
  });
  it('publishing is next only when the three before it are done', () => {
    expect(states('approved', 'shadow', false)).toEqual(['done', 'done', 'now', 'todo']);
    expect(states('approved', 'shadow', true)).toEqual(['done', 'done', 'done', 'now']);
  });
  it('a published setup has nothing left', () => {
    expect(states('published', 'pub', false)).toEqual(['done', 'done', 'done', 'done']);
  });
});

describe('the published moment', () => {
  it('names what opens, by area', () => expect(OPENED.map((o) => o.area)).toEqual(['Decide', 'Understand']));
  it('says the share that is live and leaves out a paused canary', () => {
    expect(liveShare([{ stage: 'canary', region: 'North', share: 20 }])).toBe('20 % of cases in North');
    expect(liveShare([{ stage: 'paused', region: 'North', share: 20 }])).toBeNull();
    expect(liveShare([])).toBeNull();
  });
});
