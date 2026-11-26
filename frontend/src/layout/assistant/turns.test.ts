import { describe, expect, it } from 'vitest';
import type { AskEvent, AskFinal } from '../../api/ask';
import { addTurn, applyAskEvent, askData, defaultMode, emptyConv, enqueue, errorText, finishTurn, patchTurn, stopTurn, takeQueued, type AskData } from './turns';
import type { AssistantContext, ModeDef } from './types';

const final = (over: Partial<AskFinal> = {}): AskEvent => ({
  type: 'final', provider: 'groq', model: 'm', by_model: true, fallback_reason: null, notice: null, text: 'Done.', case_ids: [], asset_ids: [],
  sources: [], tools: [], refused: [], next: [], cards: [], conversation_id: 'c1', ...over,
});

describe('conversation state', () => {
  it('adds a turn that is waiting, and patches it by id', () => {
    const [s1, id] = addTurn(emptyConv(), 'ask', 'Why?');
    expect(s1.turns).toHaveLength(1);
    expect(s1.turns[0]).toMatchObject({ id, mode: 'ask', text: 'Why?' });
    expect(s1.turns[0].status[0].state).toBe('waiting');
    expect(s1.running).toBe(id);
    const s2 = patchTurn(s1, id, (t) => ({ ...t, error: 'x' }));
    expect(s2.turns[0].error).toBe('x');
    expect(patchTurn(s2, 99, (t) => ({ ...t, error: 'y' }))).toBe(s2);
  });

  it('keeps one queue slot: a second message replaces the first, takeQueued empties it', () => {
    let s = emptyConv();
    s = enqueue(s, { text: 'first', mode: 'ask' });
    s = enqueue(s, { text: 'second', mode: 'ask' });
    expect(s.queue?.text).toBe('second');
    const [s2, q] = takeQueued(s);
    expect(q?.text).toBe('second');
    expect(s2.queue).toBeNull();
    expect(takeQueued(s2)[1]).toBeNull();
  });

  it('stop marks the turn stopped, says nothing was saved, and frees the run', () => {
    const [s1, id] = addTurn(emptyConv(), 'change', 'Never send grade D');
    const s2 = stopTurn(s1, id);
    const last = s2.turns[0].status.at(-1)!;
    expect(last.state).toBe('stopped');
    expect(last.limit).toMatch(/nothing was saved/i);
    expect(s2.running).toBeNull();
  });
});

describe('finishTurn', () => {
  it('frees the run and drops a status line still saying working', () => {
    const [s1, id] = addTurn(emptyConv(), 'ask', 'Why?');
    const s2 = finishTurn(s1, id);
    expect(s2.running).toBeNull();
    expect(s2.turns[0].status).toEqual([]);
  });
});

describe('applyAskEvent', () => {
  const start = () => {
    const [s, id] = addTurn(emptyConv(), 'ask', 'Why RT-1048?');
    return s.turns.find((t) => t.id === id)!;
  };

  it('start sets a working status; deltas append; a tool adds its done line', () => {
    let t = applyAskEvent(start(), { type: 'start', conversation_id: 'c1', provider: 'groq', model: 'm' });
    expect(t.status.at(-1)!.state).toBe('working');
    t = applyAskEvent(t, { type: 'tool', name: 'get_case', args: { case_id: 'RT-1048' }, ok: true });
    t = applyAskEvent(t, { type: 'delta', text: 'Because ' });
    t = applyAskEvent(t, { type: 'delta', text: 'demand.' });
    const d = askData(t);
    expect(d.text).toBe('Because demand.');
    expect(d.tools).toHaveLength(1);
    expect(t.status.some((x) => x.verb === 'Read' && x.item === 'RT-1048')).toBe(true);
    // the turn is still working until the answer arrives: the last line says so
    expect(t.status.at(-1)!.state).toBe('working');
  });

  it('a reset event clears the text and the lookups so far', () => {
    let t = applyAskEvent(start(), { type: 'tool', name: 'get_case', args: { case_id: 'RT-1048' }, ok: true });
    t = applyAskEvent(t, { type: 'delta', text: 'draft that will be redone' });
    t = applyAskEvent(t, { type: 'reset', reason: 'retry' });
    const d = askData(t);
    expect(d.text).toBe('');
    expect(d.tools).toEqual([]);
    expect(t.status.every((x) => x.state !== 'done' || x.verb !== 'Read')).toBe(true);
  });

  it('a refused tool shows as blocked', () => {
    const t = applyAskEvent(start(), { type: 'tool', name: 'get_case', args: { case_id: 'RT-2001' }, ok: false, code: 'forbidden', message: 'outside your tenants' });
    expect(t.status.some((x) => x.state === 'blocked')).toBe(true);
  });

  it('final ends the turn: text, the data and one summary line as the last status', () => {
    const t = applyAskEvent(
      applyAskEvent(start(), { type: 'tool', name: 'get_case', args: { case_id: 'RT-1048' }, ok: true }),
      final({ text: 'Final answer.' }),
    );
    const d = askData(t) as AskData;
    expect(d.text).toBe('Final answer.');
    expect(d.final?.conversation_id).toBe('c1');
    const last = t.status.at(-1)!;
    expect(last.state).toBe('done');
    expect(last.verb).toBe('Answered');
  });

  it('a fallback final says the rules answered', () => {
    const t = applyAskEvent(start(), final({ provider: 'fallback', by_model: false, fallback_reason: 'no_key', notice: 'Answered by the rules.' }));
    expect(t.status.at(-1)!.item).toBe('by the rules');
  });
});

describe('errorText', () => {
  it('a network failure keeps the text and says to retry', () => {
    expect(errorText(new TypeError('Failed to fetch'))).toBe('Could not reach Circularity. Your text is kept.');
  });
  it('anything else shows its message', () => {
    expect(errorText(new Error('quota used'))).toBe('quota used');
  });
});

describe('defaultMode (plan 10, 2.1)', () => {
  const mk = (id: ModeDef['id'], ok = true) => ({ id, unavailable: () => (ok ? null : 'no') }) as unknown as ModeDef;
  const modes = [mk('ask'), mk('change'), mk('setup')];
  const ctx = (o: Partial<AssistantContext>): AssistantContext => ({ page: 'home', role: 'planner', ...o });
  const flow = { id: 1, name: 'Industrial returns', template: 'industrial', org: 'workspace', canEdit: true, draftVer: 2 };

  it('Ask everywhere else', () => expect(defaultMode(ctx({}), modes)).toBe('ask'));
  it('Change flow on the Modeler with edit rights', () => expect(defaultMode(ctx({ page: 'modeler', flow }), modes)).toBe('change'));
  it('Ask on the Modeler without edit rights', () =>
    expect(defaultMode(ctx({ page: 'modeler', flow: { ...flow, canEdit: false } }), modes)).toBe('ask'));
  it('Set up from a compose surface', () => expect(defaultMode(ctx({ page: 'modeler', pack: 'industrial' }), modes)).toBe('setup'));
  it('falls back to Ask when the mode is not available or not registered', () => {
    expect(defaultMode(ctx({ page: 'modeler', flow }), [mk('ask'), mk('change', false)])).toBe('ask');
    expect(defaultMode(ctx({ page: 'modeler', flow }), [mk('ask')])).toBe('ask');
  });
});
