import { describe, expect, it } from 'vitest';
import type { ChangeSet, DraftRule, OverlayOpRef, PackMatch } from '../../../api/compose';
import { assumedCount, blockedLines, changeLines, changeTitle, matchLine, packLabel, opSentence, setupHref, wordCountLine } from './changeSetView';

const op = (o: Record<string, unknown>): OverlayOpRef => ({ id: 'op-1', by: '', note: '', ...o }) as unknown as OverlayOpRef;
const rule = (over: Partial<DraftRule> = {}): DraftRule => ({
  id: 'IR-02', text: 'Exclude resale for grade D', stage: 'decide', stage_no: 5, when: [], action: 'exclude', path: 'resale',
  origin: { kind: 'answer', question: 'grade' }, assumed: false, ...over,
});
const set = (over: Partial<ChangeSet> = {}): ChangeSet => ({
  pack: 'tool_fleet', base_version: '3', ops: [], assumed: [], blocked: [], systems: [], kpis: [], question: null, answer: null, by_model: false, ...over,
});

describe('opSentence: each operation kind as one plain sentence', () => {
  it('tighten', () => {
    expect(opSentence(op({ op: 'tighten', target: 'GR-03', field: 'threshold', value: 3000, seen: 5000 }))).toBe(
      'Tighten GR-03: threshold from 5,000 to 3,000.',
    );
  });
  it('add_approver', () => {
    expect(opSentence(op({ op: 'add_approver', target: 'GR-01', role: 'Finance' }))).toBe('Add Finance as an approver on GR-01.');
  });
  it('add_step with and without a condition', () => {
    expect(opSentence(op({ op: 'add_step', stage: 'condition', step: 'Photo check', owner_role: 'Engineer', when: [{ fact: 'grade', op: 'eq', value: 'D' }] }))).toBe(
      'Add the step "Photo check" at Condition, owned by Engineer, when grade is "D".',
    );
    expect(opSentence(op({ op: 'add_step', stage: 'receive', step: 'Seal check', owner_role: '', when: [] }))).toBe('Add the step "Seal check" at Return and receive.');
  });
  it('shortcut', () => {
    expect(opSentence(op({ op: 'shortcut', stage: 'condition', to: 'decide', when: [{ fact: 'value', op: 'lte', value: 100 }] }))).toBe(
      'Skip from Condition to Decide, when value is at most 100.',
    );
    expect(opSentence(op({ op: 'shortcut', stage: 'match', to: 'wholesale', when: [] }))).toBe('Skip from Match and verify to wholesale.');
  });
  it('set_param', () => {
    expect(opSentence(op({ op: 'set_param', path: 'floor.min_margin', value: 12, seen: 8 }))).toBe('Set floor.min_margin from 8 to 12.');
  });
  it('an unknown kind falls back to its name, never JSON', () => {
    expect(opSentence(op({ op: 'frobnicate', x: 1 }))).toBe('Change: frobnicate.');
  });
});

describe('the change list, the assumed count and the title', () => {
  const cs = set({
    ops: [op({ id: 'op-1', op: 'add_approver', target: 'GR-01', role: 'Finance' }), op({ id: 'op-2', op: 'set_param', path: 'a', value: 2, seen: 1 })],
    assumed: ['op-2'],
    rules: [rule(), rule({ id: 'IR-03', assumed: true })],
  });
  it('lists operations then rules, each with its assumed flag', () => {
    const l = changeLines(cs);
    expect(l.map((x) => [x.id, x.assumed])).toEqual([['op-1', false], ['op-2', true], ['IR-02', false], ['IR-03', true]]);
    expect(l[2].text).toBe('Rule IR-02 at stage 5: Exclude resale for grade D.');
  });
  it('counts assumed lines (operations the person did not state, rules the pack defaulted)', () => {
    expect(assumedCount(cs)).toBe(2);
  });
  it('ignores assumed ids that name no operation', () => {
    expect(assumedCount(set({ assumed: ['op-9'] }))).toBe(0);
  });
  it('titles it "Drafted N changes, M assumed", singular and empty', () => {
    expect(changeTitle(cs)).toBe('Drafted 4 changes, 2 assumed');
    expect(changeTitle(set({ ops: [op({ id: 'op-1', op: 'set_param', path: 'a', value: 2, seen: 1 })] }))).toBe('Drafted 1 change');
    expect(changeTitle(set())).toBe('Drafted no changes');
  });
});

describe('blocked lines', () => {
  it('name the guardrail and give its text', () => {
    expect(blockedLines(set({ blocked: [{ guardrail: 'GR-I2', text: 'A shortcut may not skip compliance.' }] }))).toEqual([
      'Blocked by GR-I2: A shortcut may not skip compliance.',
    ]);
  });
  it('none when nothing is blocked', () => expect(blockedLines(set())).toEqual([]));
});

describe('the reading and match lines', () => {
  const names = { tool_fleet: 'Tool fleet returns', used_cars: 'Used vehicles · lease and trade-in returns', industrial: 'Industrial returns' };
  it('a matched pack shows the pack file name and its rounded score', () => {
    const m: PackMatch = { key: 'used_cars', score: 85.6, nearest_only: false };
    expect(matchLine(m, 'used_cars', names)).toEqual({ text: 'Matched: Used vehicles (86)', amber: false });
  });
  it('the pick kept over the match is said', () => {
    const m: PackMatch = { key: 'used_cars', score: 86, nearest_only: false };
    expect(matchLine(m, 'industrial', names)).toEqual({ text: 'Matched: Used vehicles (86). Drafted against Industrial returns, the one you picked.', amber: false });
  });
  it('no pack fits: amber, no match claimed, the score is only the closest', () => {
    const m: PackMatch = { key: 'industrial', score: 32, nearest_only: true };
    expect(matchLine(m, 'industrial', names)).toEqual({
      text: 'No pack fits this description yet. Closest: Industrial returns (32). Drafted against Industrial returns: check every change.', amber: true,
    });
    expect(matchLine(m).text).toBe('No pack fits this description yet. Closest: industrial (32).');
  });
  it('without a score (config.read failed) the pack alone is named', () => {
    expect(matchLine(null, 'tool_fleet', names)).toEqual({ text: 'Matched: Tool fleet returns', amber: false });
  });
  it('word count line is singular and plural aware', () => {
    expect(wordCountLine(62, 1, ['SAP'])).toBe('Read 62 words, 1 explicit control, systems: SAP');
    expect(wordCountLine(1, 0, [])).toBe('Read 1 word, 0 explicit controls');
  });
});

describe('packLabel', () => {
  it('falls back to the key when the pack has no name', () => expect(packLabel('itad')).toBe('itad'));
});

describe('setupHref', () => {
  it('opens the Set up tab on the composition', () => expect(setupHref(12)).toBe('/modeler?tab=setup&compose=12'));
  it('keeps the template and org of the composition', () =>
    expect(setupHref(12, { template: 'tool_fleet', org: 'Customer A' })).toBe('/modeler?template=tool_fleet&org=Customer+A&tab=setup&compose=12'));
});
