import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  invoke: vi.fn(),
  http: vi.fn(),
}));
vi.mock('./actions', () => ({ invoke: m.invoke }));
vi.mock('./client', () => ({
  http: m.http,
  ApiError: class ApiError extends Error {
    constructor(readonly status: number, readonly code: string, message: string) {
      super(message);
    }
  },
}));

import {
  builderReducer, createFromPlan, current, formComplete, formFor, initialBuilder, nextAnswers, planWorkflow, toggled,
  type Plan, type PlanReply, type Question,
} from './workflowBuilder';

const Q = (id: string, kind: Question['kind'], def: Question['default'], choices: (string | number)[] = []): Question => ({
  id, text: id, kind, multi: kind === 'multi', default: def, choices: choices.map((v) => ({ value: v, label: String(v), hint: '' })),
});
const reply = (questions: Question[], answers = {}, status: PlanReply['status'] = 'questions'): PlanReply => ({
  status, questions, notes: [], understood: [], answers, plan: null,
});

beforeEach(() => {
  m.invoke.mockReset();
  m.http.mockReset();
});

describe('the planner call', () => {
  it('posts the prompt and answers to workflow.plan and returns its output', async () => {
    m.http.mockResolvedValue({ ok: true, output: reply([Q('type', 'choice', 'ingest')]) });
    const r = await planWorkflow('make a workflow', { a: 1 });
    expect(m.http).toHaveBeenCalledWith('/api/actions/workflow.plan', { method: 'POST', body: { prompt: 'make a workflow', answers: { a: 1 } } });
    expect(r.questions[0].id).toBe('type');
  });

  it('throws the refusal message', async () => {
    m.http.mockResolvedValue({ ok: false, error: { code: 'validation_error', message: 'Keep it short.' } });
    await expect(planWorkflow('x')).rejects.toThrow('Keep it short.');
  });
});

describe('creating the plan (the person clicks Create workflow)', () => {
  const plan = { create: { type: 'ingest', src: 'crm', graph: { nodes: [], edges: [] } }, save: { name: 'N', owner: 'O', retries: 1 } } as unknown as Plan;

  it('runs workflow.create, then workflow.save on the new id', async () => {
    m.invoke.mockResolvedValueOnce({ ok: true, output: { id: 'WF-130', name: 'N' } }).mockResolvedValueOnce({ ok: true, output: { id: 'WF-130', ver: '0.2', name: 'N' } });
    const r = await createFromPlan(plan);
    expect(m.invoke.mock.calls).toEqual([
      ['workflow.create', plan.create],
      ['workflow.save', { id: 'WF-130', name: 'N', owner: 'O', retries: 1 }],
    ]);
    expect(r).toEqual({ ok: true, output: { id: 'WF-130', name: 'N' } });
  });

  it('a refused create saves nothing; a refused save says the draft exists', async () => {
    m.invoke.mockResolvedValueOnce({ ok: false, error: { code: 'out_of_scope', message: 'No.' } });
    expect((await createFromPlan(plan)).ok).toBe(false);
    expect(m.invoke).toHaveBeenCalledTimes(1);
    m.invoke.mockReset();
    m.invoke.mockResolvedValueOnce({ ok: true, output: { id: 'WF-131', name: 'N' } }).mockResolvedValueOnce({ ok: false, error: { code: 'validation_error', message: 'Bad.' } });
    const r = await createFromPlan(plan);
    expect(r.ok === false && r.error.message).toBe('N was created as a draft, but its settings were not saved: Bad.');
  });
});

describe('the conversation state', () => {
  it('fills each question with its default, keeps earlier answers and toggles multi-selects', () => {
    const qs = [Q('trigger', 'choice', 'schedule:15'), Q('steps', 'multi', null, ['x_fx', 'x_late']), Q('name', 'text', 'My flow')];
    expect(formFor(qs)).toEqual({ trigger: 'schedule:15', steps: [], name: 'My flow' });
    expect(formFor(qs, { trigger: 'event' }).trigger).toBe('event');
    expect(toggled(['x_fx'], 'x_late', true)).toEqual(['x_fx', 'x_late']);
    expect(toggled(['x_fx', 'x_late'], 'x_fx', false)).toEqual(['x_late']);
    expect(toggled(undefined, 'x_fx', true)).toEqual(['x_fx']);
    expect(formComplete([Q('type', 'choice', null)], {})).toBe(false);
    expect(formComplete([Q('type', 'choice', null), Q('name', 'text', null)], { type: 'out' })).toBe(true);
  });

  it('rounds accumulate answers; Back returns to the previous questions with what was answered', () => {
    let s = initialBuilder('make a workflow');
    s = builderReducer(s, { t: 'start' });
    expect(s.busy).toBe(true);
    s = builderReducer(s, { t: 'reply', sent: {}, reply: reply([Q('type', 'choice', 'ingest', ['ingest', 'out'])]) });
    expect(s.form).toEqual({ type: 'ingest' });
    s = builderReducer(s, { t: 'set', id: 'type', value: 'out' });
    const sent = nextAnswers(s);
    expect(sent).toEqual({ type: 'out' });
    s = builderReducer(s, { t: 'reply', sent, reply: reply([Q('system', 'choice', 'erp', ['erp', 'oms'])], { type: 'out' }) });
    expect(s.rounds).toHaveLength(2);
    expect(nextAnswers(s)).toEqual({ type: 'out', system: 'erp' });
    s = builderReducer(s, { t: 'back' });
    expect(s.rounds).toHaveLength(1);
    expect(s.form).toEqual({ type: 'out' }); // the answer given, not the default
    expect(current(s)?.questions[0].id).toBe('type');
    s = builderReducer(s, { t: 'back' });
    expect(s.rounds).toHaveLength(0);
    expect(s.prompt).toBe('make a workflow');
  });

  it('Change reopens the round that asked a slot; a failure keeps the rounds', () => {
    let s = initialBuilder('x');
    s = builderReducer(s, { t: 'reply', sent: {}, reply: reply([Q('type', 'choice', 'ingest')]) });
    s = builderReducer(s, { t: 'reply', sent: { type: 'dec' }, reply: reply([Q('decision', 'choice', 'standard')], { type: 'dec' }) });
    s = builderReducer(s, { t: 'reply', sent: { type: 'dec', decision: 'pool' }, reply: reply([], { type: 'dec', decision: 'pool' }, 'ready') });
    s = builderReducer(s, { t: 'edit', slot: 'type' });
    expect(s.rounds).toHaveLength(1);
    expect(s.form).toEqual({ type: 'dec' });
    s = builderReducer(s, { t: 'fail', message: 'Could not reach the server.' });
    expect(s.rounds).toHaveLength(1);
    expect(s.error).toBe('Could not reach the server.');
    expect(builderReducer(s, { t: 'restart' })).toEqual(initialBuilder('x'));
  });
});
