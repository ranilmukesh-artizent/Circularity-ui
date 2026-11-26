/**
 * Ask Circularity (B16b): POST /api/ask, read as a stream of Server-Sent Events with fetch (EventSource cannot POST).
 * Events: start, tool, delta, reset, final (backend/di/services/ask/service.py). Ask only reads; a suggested next step is
 * offered to the person and runs only when they confirm it.
 */
import { accessToken, http, withQuery } from './client';

export interface AskContext { page?: string; section?: string; case_id?: string; object?: { kind: string; id: string } }

export interface AskTool { name: string; args: Record<string, unknown>; ok: boolean; code?: string | null; message?: string | null; skipped?: boolean }

/** A suggested next step: ask again, open the approval card, or an action the person may confirm. */
export interface AskNext { label: string; ask?: string; approve?: string; go?: string; action?: string; input?: Record<string, unknown>; case_id?: string }

export interface AskCard { type: string; data: Record<string, unknown> }

export interface AskFinal {
  provider: 'groq' | 'fallback' | string;
  model: string | null;
  /** true when a language model wrote the answer; false when the rules did (the server sends it, service.py) */
  by_model: boolean;
  fallback_reason: string | null;
  notice: string | null;
  text: string;
  case_ids: string[];
  asset_ids: string[];
  sources: string[];
  tools: AskTool[];
  refused: { tool: string | null; code: string; message: string | null }[];
  next: AskNext[];
  cards: AskCard[];
  conversation_id: string;
}

export type AskEvent =
  | { type: 'start'; conversation_id: string; provider: string; model: string | null }
  | ({ type: 'tool' } & AskTool)
  | { type: 'delta'; text: string }
  | { type: 'reset'; reason: string }
  | ({ type: 'final' } & AskFinal);


/** Split an SSE byte stream into events and hand each parsed one to onEvent. */
export async function readSse(body: ReadableStream<Uint8Array>, onEvent: (e: AskEvent) => void): Promise<void> {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).replace(/^ /, ''))
        .join('\n');
      if (!data) continue;
      try {
        onEvent(JSON.parse(data) as AskEvent);
      } catch {
        /* ignore a malformed event */
      }
    }
    if (done) return;
  }
}

/** Ask one question; events arrive through onEvent. Resolves when the answer is complete. */
export async function ask(
  question: string,
  opts: { context?: AskContext; conversationId?: string | null; signal?: AbortSignal; onEvent: (e: AskEvent) => void },
): Promise<void> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(accessToken() ? { Authorization: 'Bearer ' + accessToken() } : {}),
    },
    body: JSON.stringify({ question, context: opts.context ?? {}, conversation_id: opts.conversationId ?? undefined }),
    signal: opts.signal,
  });
  if (!res.ok || !res.body) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      msg = b?.error?.message ?? b?.detail?.message ?? b?.detail?.[0]?.msg ?? msg;
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  await readSse(res.body, opts.onEvent);
}

/** Starter questions for what the person is looking at, by pack and page, already filtered by their role (E17). */
export interface AskStarters { pack: string | null; starters: { text: string }[] }
export const askStartersFor = (q: { page: string; section?: string; case_id?: string }): Promise<AskStarters> =>
  http<AskStarters>(withQuery('/api/ask/starters', q));
