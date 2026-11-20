/**
 * Opening Ask Circularity from anywhere: openAsk() opens the panel, optionally with a question to ask at once.
 * Pages call this instead of showing their own panel; AskPanel (src/app/AskPanel.tsx) listens.
 */
type Listener = (req: { question?: string; nonce: number }) => void;
const listeners = new Set<Listener>();
let nonce = 0;

export function openAsk(question?: string): void {
  nonce++;
  listeners.forEach((l) => l({ question, nonce }));
}

export function onOpenAsk(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
