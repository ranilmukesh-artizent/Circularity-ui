/**
 * Opening Ask Circularity from anywhere: openAsk() opens the panel, optionally with a question to ask at once.
 * Pages call this instead of showing their own panel; AskPanel (src/layout/AskPanel.tsx) listens.
 */
import type { OpenRequest } from '../layout/assistant/types';

type Listener =(req: { question?: string; nonce: number }) => void;
const listeners = new Set<Listener>();
let nonce = 0;

export function openAsk(question?: string): void {
  nonce++;
  listeners.forEach((l) => l({ question, nonce }));
}

/** openAsk for an onClick: a click passes an event, not a question, so only a string is asked. */
export const askSoon = (q?: unknown): void => openAsk(typeof q === 'string' ? q : undefined);

/** Plan 10 contract: open the one assistant in a mode, with a question or a compose draft. T1 wires the dock to it. */
type AssistantListener = (req: OpenRequest & { nonce: number }) => void;
const assistantListeners = new Set<AssistantListener>();

export function openAssistant(req: OpenRequest = {}): void {
  nonce++;
  assistantListeners.forEach((l) => l({ ...req, nonce }));
}

export function onOpenAssistant(l: AssistantListener): () => void {
  assistantListeners.add(l);
  return () => {
    assistantListeners.delete(l);
  };
}

export function onOpenAsk(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
