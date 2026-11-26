/**
 * The one conversation (plan 10, 2.2): a module-level store that both hosts of AssistantPanel (the Ctrl+J dock and the
 * Modeler's pinned column) read, so a question asked on Home is still in the transcript on the Modeler, and a turn keeps
 * running when the dock closes. Pure reducers are in turns.ts; this file runs a turn, stops it and holds the queue slot.
 */
import { useSyncExternalStore } from 'react';
import { resetAskConversation } from './modes/ask';
import { MODES } from './modes';
import {
  addTurn, defaultMode, emptyConv, enqueue, errorText, failTurn, finishTurn, patchTurn, stopTurn, takeQueued, type Conv,
} from './turns';
import type { AssistantContext, AssistantMode, Turn } from './types';

/** open: the dock; picked: the person's mode; hint: the mode a pinned host asks for (the Modeler's tab); pinned: hosts mounted */
export interface Ui { open: boolean; picked: AssistantMode | null; hint: AssistantMode | null; pinned: number }

let conv: Conv = emptyConv();
let ui: Ui = { open: false, picked: null, hint: null, pinned: 0 };
let queuedCtx: AssistantContext | null = null;
let abort: AbortController | null = null;
let pinnedFocus: (() => void) | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());
const setConv = (c: Conv) => {
  conv = c;
  emit();
};
const setUi = (patch: Partial<Ui>) => {
  ui = { ...ui, ...patch };
  emit();
};
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

export const useConv = (): Conv => useSyncExternalStore(subscribe, () => conv, () => conv);
export const useUi = (): Ui => useSyncExternalStore(subscribe, () => ui, () => ui);

/**
 * The mode shown: the person's pick while it is available here, else the pinned host's hint (the Modeler's tab), else
 * the context's default. A visible radio shows it; no model routes silently.
 */
export function effectiveMode(ctx: AssistantContext, u: Pick<Ui, 'picked' | 'hint'> = ui): AssistantMode {
  for (const want of [u.picked, u.hint]) {
    const def = want && MODES.find((m) => m.id === want);
    if (def && !def.unavailable(ctx)) return def.id;
  }
  return defaultMode(ctx, MODES);
}

export const setHint = (hint: AssistantMode | null) => {
  // a new tab sets the mode again; the person can still pick another one after that
  if (ui.hint !== hint) setUi({ hint, picked: hint ? null : ui.picked });
};
export const pickMode = (m: AssistantMode) => setUi({ picked: m });
export const setOpen = (open: boolean) => setUi({ open });
export const isOpen = () => ui.open;
export const hasPinned = () => ui.pinned > 0;

/** A pinned host (the Modeler's column) mounts: the dock steps aside, and Ctrl+J focuses this composer instead. */
export function registerPinned(focus: () => void): () => void {
  pinnedFocus = focus;
  setUi({ pinned: ui.pinned + 1 });
  return () => {
    if (pinnedFocus === focus) pinnedFocus = null;
    setUi({ pinned: Math.max(0, ui.pinned - 1) });
  };
}
export const focusPinned = () => pinnedFocus?.();

/** Send now, or hold in the one queue slot while a turn runs (a later message replaces the one waiting). */
export function send(text: string, mode: AssistantMode, ctx: AssistantContext): void {
  const t = text.trim();
  if (!t) return;
  if (conv.running !== null) {
    queuedCtx = ctx;
    setConv(enqueue(conv, { text: t, mode }));
    return;
  }
  void run(t, mode, ctx);
}

async function run(text: string, mode: AssistantMode, ctx: AssistantContext): Promise<void> {
  const def = MODES.find((m) => m.id === mode);
  if (!def) return;
  const [s, id] = addTurn(conv, mode, text);
  setConv(s);
  const ctrl = new AbortController();
  abort = ctrl;
  // a stopped turn drops what arrives late: these calls only read or make drafts
  const live = () => conv.running === id && !ctrl.signal.aborted;
  try {
    const patch = (f: (t: Turn) => Turn) => {
      if (live()) setConv(patchTurn(conv, id, f));
    };
    await def.send(text, ctx, { signal: ctrl.signal, patch });
    if (live()) setConv(finishTurn(conv, id));
  } catch (err) {
    if (live()) setConv(failTurn(conv, id, errorText(err)));
  } finally {
    if (abort === ctrl) abort = null;
    next();
  }
}

/** After a turn ends or is stopped, send the queued message, if any. */
function next(): void {
  if (conv.running !== null || !conv.queue) return;
  const [s, q] = takeQueued(conv);
  setConv(s);
  const c = queuedCtx;
  queuedCtx = null;
  if (q && c) void run(q.text, q.mode, c);
}

export function stop(): void {
  if (conv.running === null) return;
  const id = conv.running;
  abort?.abort();
  setConv(stopTurn(conv, id));
  next();
}

export const dropQueued = () => setConv({ ...conv, queue: null });

/** New conversation: forget the transcript and the server's conversation id. A running turn is stopped first. */
export function newConversation(): void {
  queuedCtx = null;
  conv = { ...conv, queue: null };
  stop();
  resetAskConversation();
  setConv(emptyConv());
}
