/**
 * The conversation as plain data and pure reducers (plan 10, 2.8 and 2.10): the turns, one queue slot ("steer"),
 * stop, and how the events of an Ask stream fold into a turn. The store (store.ts) holds one of these for both hosts.
 */
import type { AskCreated, AskEvent, AskFinal, AskTool } from '../../api/ask';
import { statusLine } from './status';
import type { AssistantContext, AssistantMode, ModeDef, Status, Turn } from './types';

export interface Queued { text: string; mode: AssistantMode }
export interface Conv { turns: Turn[]; queue: Queued | null; running: number | null; nextId: number }
/** What an Ask turn keeps in Turn.data. */
export interface AskData { text: string; tools: AskTool[]; final: AskFinal | null; created?: AskCreated[] }

export const NETWORK_MSG = 'Could not reach Circularity. Your text is kept.';

export const emptyConv = (): Conv => ({ turns: [], queue: null, running: null, nextId: 1 });

export const askData = (t: Turn): AskData => (t.data as AskData | null) ?? { text: '', tools: [], final: null };

/** Add a turn for the person's words; it is the running one until finished or stopped. */
export function addTurn(s: Conv, mode: AssistantMode, text: string): [Conv, number] {
  const id = s.nextId;
  const turn: Turn = { id, mode, text, status: [{ verb: 'Sending', item: 'your message', state: 'waiting' }], data: null };
  return [{ ...s, turns: [...s.turns, turn], running: id, nextId: id + 1 }, id];
}

/** Change one turn; the state is returned as it was when there is no such turn (a stopped or cleared one). */
export function patchTurn(s: Conv, id: number, f: (t: Turn) => Turn): Conv {
  if (!s.turns.some((t) => t.id === id)) return s;
  return { ...s, turns: s.turns.map((t) => (t.id === id ? f(t) : t)) };
}

/** One slot: a newer message replaces the one waiting. */
export const enqueue = (s: Conv, q: Queued): Conv => ({ ...s, queue: q });
export const takeQueued = (s: Conv): [Conv, Queued | null] => [{ ...s, queue: null }, s.queue];

/** Stop: these calls only read or make drafts, so nothing was saved. */
export function stopTurn(s: Conv, id: number): Conv {
  const stopped: Status = { verb: 'Stopped', item: '', limit: 'nothing was saved', state: 'stopped' };
  const next = patchTurn(s, id, (t) => ({ ...t, error: undefined, status: [...t.status.filter((x) => x.state === 'done' || x.state === 'blocked'), stopped] }));
  return { ...next, running: s.running === id ? null : s.running };
}

/** Ends a turn; a line still saying "waiting" or "working" when the call returned is dropped, not left running. */
export function finishTurn(s: Conv, id: number): Conv {
  const open = (x: Status) => x.state === 'waiting' || x.state === 'working';
  const next = patchTurn(s, id, (t) => ({ ...t, status: t.status.filter((x) => !open(x)) }));
  return { ...next, running: s.running === id ? null : s.running };
}

export function failTurn(s: Conv, id: number, message: string): Conv {
  const failed: Status = { verb: 'Could not finish', item: '', limit: message, state: 'failed' };
  return finishTurn(patchTurn(s, id, (t) => ({ ...t, error: message, status: [...t.status, failed] })), id);
}

/** A network failure names the way out; any other failure shows its own message. */
export function errorText(err: unknown): string {
  if (err instanceof TypeError) return NETWORK_MSG;
  return err instanceof Error && err.message ? err.message : 'Something went wrong.';
}

const POLICY = /^(forbidden|not_permitted|tenant|refused|denied|policy|permission)/i;

/** Fold one event of the Ask stream into the turn (the reset event clears the text and the lookups so far). */
export function applyAskEvent(t: Turn, e: AskEvent): Turn {
  const d = askData(t);
  switch (e.type) {
    case 'start':
      return { ...t, status: [{ verb: 'Looking up', item: 'what your role may see', limit: 'read-only', state: 'working' }] };
    case 'tool': {
      const refused = !e.ok && (e.skipped || POLICY.test(e.code ?? ''));
      const line = statusLine({ name: e.name, phase: e.ok ? 'done' : refused ? 'refused' : 'failed', args: e.args, message: e.message });
      // the line of what was read, then a working line: the turn is not done until the answer arrives
      const wait: Status = { verb: 'Writing', item: `the answer from ${d.tools.length + 1} lookup${d.tools.length ? 's' : ''}`, limit: 'read-only', state: 'working' };
      return { ...t, data: { ...d, tools: [...d.tools, e] }, status: [...t.status.filter((x) => x.state !== 'waiting' && x.state !== 'working'), line, wait] };
    }
    case 'created': {
      const { type: _t, ...c } = e;
      const have = d.created ?? [];
      return have.some((x) => x.kind === c.kind && x.id === c.id) ? t : { ...t, data: { ...d, created: [...have, c] } };
    }
    case 'delta':
      return { ...t, data: { ...d, text: d.text + e.text } };
    case 'reset':
      return { ...t, data: { ...d, text: '', tools: [], created: [] }, status: [{ verb: 'Looking up', item: 'what your role may see', limit: 'read-only', state: 'working' }] };
    case 'final': {
      const byRules = !e.by_model && e.provider === 'fallback';
      const n = e.tools?.length ?? d.tools.length;
      const summary: Status = byRules
        ? statusLine({ name: 'ask.fallback', phase: 'done', result: { reason: reasonOf(e) } })
        : { verb: 'Answered', item: n ? `from ${n} lookup${n === 1 ? '' : 's'}` : 'from your data', limit: 'read-only', state: 'done' };
      const blocked = t.status.filter((x) => x.state === 'blocked');
      return { ...t, data: { ...d, text: e.text, tools: e.tools?.length ? e.tools : d.tools, final: e, created: mergeCreated(d.created, e.created) }, status: [...blocked, summary] };
    }
  }
}

function mergeCreated(a: AskCreated[] = [], b: AskCreated[] = []): AskCreated[] {
  return [...a, ...b.filter((y) => !a.some((x) => x.kind === y.kind && x.id === y.id))];
}

function reasonOf(e: AskFinal): string {
  return e.fallback_reason ? e.fallback_reason.replace(/_/g, ' ') : 'the model was unavailable';
}

/**
 * The mode a panel opens in when the person has not picked one (plan 10, 2.1): the Modeler with edit rights opens in
 * Change flow, a compose surface in Set up, everywhere else Ask. A mode that is not registered or not available gives
 * way to Ask. No model decides it.
 */
export function defaultMode(ctx: AssistantContext, modes: readonly ModeDef[]): AssistantMode {
  const want: AssistantMode = ctx.flow?.canEdit ? 'change' : !ctx.flow && ctx.pack ? 'setup' : 'ask';
  const def = modes.find((m) => m.id === want);
  return def && !def.unavailable(ctx) ? want : 'ask';
}
