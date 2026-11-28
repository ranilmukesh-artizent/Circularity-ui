import { describe, expect, it } from 'vitest';
import { ageText, KIND_ONE, MINE, parseShow, summary, tasksPath } from './tasksView';

describe('parseShow', () => {
  it('accepts every kind, fraud and handed', () => {
    for (const v of ['approval', 'proposal', 'needs_info', 'task', 'exception', 'conflict', 'fraud', 'handed']) expect(parseShow(v)).toBe(v);
  });
  it('treats anything else as the whole list', () => {
    expect(parseShow(null)).toBeNull();
    expect(parseShow('')).toBeNull();
    expect(parseShow('nope')).toBeNull();
    expect(parseShow('Approval')).toBeNull();
  });
});

describe('tasksPath', () => {
  it('is the whole list or one filter', () => {
    expect(tasksPath(null)).toBe('/tasks');
    expect(tasksPath('approval')).toBe('/tasks?show=approval');
    expect(tasksPath('handed')).toBe('/tasks?show=handed');
  });
});

describe('MINE and KIND_ONE', () => {
  it('lists the five kinds only this person does, without conflicts', () => {
    expect(MINE).toEqual(['approval', 'proposal', 'needs_info', 'task', 'exception']);
    expect(MINE).not.toContain('conflict');
  });
  it('names every kind', () => {
    expect(KIND_ONE).toEqual({ approval: 'Approval', proposal: 'Proposal', needs_info: 'Question', task: 'Task', exception: 'Exception', conflict: 'Data conflict' });
  });
});

describe('summary', () => {
  it('says nothing waits', () => expect(summary(0, 0, 0)).toBe('Nothing waits on you.'));
  it('counts, singular and plural', () => {
    expect(summary(1, 0, 0)).toBe('1 thing waits on you.');
    expect(summary(12, 3, 4)).toBe('12 things wait on you. 3 are late. 4 more wait on others.');
    expect(summary(2, 1, 1)).toBe('2 things wait on you. 1 is late. 1 more waits on others.');
  });
  it('can have only handed-on work', () => expect(summary(0, 0, 2)).toBe('Nothing waits on you. 2 more wait on others.'));
});

describe('ageText', () => {
  it('words the days', () => {
    expect(ageText(0)).toBe('today');
    expect(ageText(0.9)).toBe('today');
    expect(ageText(1)).toBe('1 day');
    expect(ageText(1.8)).toBe('1 day');
    expect(ageText(3)).toBe('3 days');
  });
});
