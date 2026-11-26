/**
 * Opening Ask Circularity from anywhere: openAssistant({ mode, question }) opens the one assistant (plan 10), in the
 * Ctrl+J dock or, on the Modeler, in the pinned column. Pages call this instead of showing their own panel;
 * AssistantDock (src/layout/assistant/AssistantDock.tsx) listens. openAsk(q) stays as the Ask-mode alias.
 */
import type { OpenRequest } from '../layout/assistant/types';

let nonce = 0;

export function openAsk(question?: string): void {
  openAssistant({ mode: 'ask', question });
}

/** openAsk for an onClick: a click passes an event, not a question, so only a string is asked. */
export const askSoon = (q?: unknown): void => openAsk(typeof q === 'string' ? q : undefined);

/** Open the one assistant in a mode, with a question or a compose draft. */
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
