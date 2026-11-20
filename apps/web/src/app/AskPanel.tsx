/**
 * Ask Circularity (Ctrl+J): a side panel that asks di-api's /api/ask and shows the answer as it streams, with each
 * lookup it made, the cases and source systems it used, and suggested next steps. Ask never acts: a suggested action
 * runs only after the person confirms it, through invoke() like any other click.
 */
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { invoke } from '../api/actions';
import { ask, type AskCard, type AskEvent, type AskFinal, type AskNext, type AskTool } from '../api/ask';
import { ref } from '../api/client';
import { currentAccount } from '../api/session';
import type { RouteRef } from '../api/types';
import { onOpenAsk } from '../ui/askBus';
import { Icon } from '../ui/Icon';
import { toast } from '../ui/toast';

interface Turn {
  q: string;
  tools: AskTool[];
  text: string;
  final: AskFinal | null;
  error: string | null;
  busy: boolean;
}

const CASE_RX = /^RT-\d{4}$/;

/** What the person is looking at, sent with the question. */
function contextOf(route: RouteRef) {
  const caseId = [route.a, route.b].find((x) => x && CASE_RX.test(x)) ?? undefined;
  return { page: route.page || 'home', section: route.a && !CASE_RX.test(route.a) ? route.a : undefined, case_id: caseId };
}

function starters(): string[] {
  const role = currentAccount()?.role ?? '';
  try {
    return (ref<Record<string, string[]>>('AF_STARTERS')[role] ?? []).slice(0, 4);
  } catch {
    return [];
  }
}

export function AskPanel({ route }: { route: RouteRef }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState('');
  const [conv, setConv] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<AskNext | null>(null);
  const abort = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const ctx = contextOf(route);
  const busy = turns.some((t) => t.busy);

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setQ('');
    setOpen(true);
    const i = turns.length;
    setTurns((ts) => [...ts, { q: text, tools: [], text: '', final: null, error: null, busy: true }]);
    const patch = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, k) => (k === i ? f(t) : t)));
    abort.current = new AbortController();
    try {
      await ask(text, {
        context: ctx,
        conversationId: conv,
        signal: abort.current.signal,
        onEvent: (e: AskEvent) => {
          if (e.type === 'start') setConv(e.conversation_id);
          else if (e.type === 'tool') patch((t) => ({ ...t, tools: [...t.tools, e] }));
          else if (e.type === 'delta') patch((t) => ({ ...t, text: t.text + e.text }));
          else if (e.type === 'reset') patch((t) => ({ ...t, text: '', tools: [] }));
          else if (e.type === 'final') {
            setConv(e.conversation_id);
            patch((t) => ({ ...t, text: e.text, final: e, busy: false }));
          }
        },
      });
      patch((t) => ({ ...t, busy: false }));
    } catch (err) {
      const aborted = (err as Error).name === 'AbortError';
      patch((t) => ({ ...t, busy: false, error: aborted ? 'Stopped.' : 'Ask could not answer: ' + (err as Error).message }));
    }
  }

  // open with Ctrl+J, from the top bar, or from a page (openAsk)
  useEffect(() => {
    const key = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);
  // subscribe once; the listener calls the latest send (which closes over this render's turns, conversation and busy)
  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  });
  useEffect(
    () =>
      onOpenAsk(({ question }) => {
        setOpen(true);
        if (question) void sendRef.current(question);
      }),
    [],
  );
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [turns]);

  async function runNext(n: AskNext) {
    if (n.ask) return void send(n.ask);
    if (n.approve) return nav('/product/' + n.approve);
    if (n.go) return nav('/' + n.go.replace(/^#\//, ''));
    if (n.action) setConfirm(n);
  }

  async function confirmNext() {
    const n = confirm;
    setConfirm(null);
    if (!n?.action) return;
    const r = await invoke(n.action, n.input ?? {});
    toast(r.ok ? n.label + ': done.' : r.error.message);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send(q);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(q);
  };

  return (
    <>
      <aside className="afp" hidden={!open} aria-label="Ask Circularity" role="complementary">
        <header className="afph">
          <div>
            <h2>
              <Icon name="spark" /> Ask Circularity
            </h2>
            <span className="note">Answers from your data, within what your role may see. Ask never changes anything.</span>
          </div>
          <button className="iconbtn" aria-label="Close Ask Circularity" onClick={() => setOpen(false)}>
            <Icon name="close" />
          </button>
        </header>
        <div className="afctx" aria-label="Context">
          <span className="chip line">Page: {ctx.page}</span>
          {ctx.section && <span className="chip line">Section: {ctx.section}</span>}
          {ctx.case_id && <span className="chip line">Case: {ctx.case_id}</span>}
        </div>
        <div ref={log} style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }} aria-live="polite">
          {turns.length === 0 && (
            <div className="afm">
              <p className="note">Try one of these:</p>
              <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                {starters().map((s) => (
                  <button key={s} className="btn sm" onClick={() => void send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <AnswerTurn key={i} t={t} onNext={runNext} />
          ))}
        </div>
        {confirm && (
          <div className="afc" role="alertdialog" aria-label="Confirm the suggested step" style={{ margin: '0 16px 8px' }}>
            <b>{confirm.label}?</b>
            <p className="note">This runs {confirm.action} as you, with the usual checks and approvals.</p>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn pri sm" onClick={() => void confirmNext()}>
                Confirm
              </button>
              <button className="btn sm" onClick={() => setConfirm(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
        <form className="afcomp" onSubmit={submit}>
          <label className="sr" htmlFor="afq">
            Ask a question
          </label>
          <textarea id="afq" ref={input} rows={2} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Ask about a case, a source, a figure…" maxLength={2000} />
          <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
            {turns.length > 0 && !busy && (
              <button type="button" className="btn sm" onClick={() => (setTurns([]), setConv(null))}>
                New conversation
              </button>
            )}
            {busy ? (
              <button type="button" className="btn sm" onClick={() => abort.current?.abort()}>
                Stop
              </button>
            ) : (
              <button className="btn pri sm" type="submit" disabled={!q.trim()}>
                Ask
              </button>
            )}
          </div>
        </form>
      </aside>
    </>
  );
}

function AnswerTurn({ t, onNext }: { t: Turn; onNext: (n: AskNext) => void }) {
  const f = t.final;
  return (
    <div className="afm">
      <p style={{ margin: '0 0 6px' }}>
        <b>You:</b> {t.q}
      </p>
      {t.tools.length > 0 && (
        <div className="afmeta" aria-label="Lookups">
          {t.tools.map((x, i) => (
            <span key={i} className={'chip' + (x.ok ? '' : ' warn')} title={x.message ?? ''}>
              {x.ok ? '✓' : '✕'} {x.name}
              {typeof x.args?.case_id === 'string' ? ' · ' + x.args.case_id : ''}
            </span>
          ))}
        </div>
      )}
      <div className="afc">
        {t.text ? <div style={{ whiteSpace: 'pre-wrap' }}>{t.text}</div> : t.busy ? <span className="afdots note">Thinking…</span> : null}
        {t.error && <p className="note">{t.error}</p>}
        {f?.cards.map((c, i) => <Card key={i} c={c} onNext={onNext} />)}
        {f && (f.case_ids.length > 0 || f.sources.length > 0) && (
          <p className="note" style={{ marginTop: 8 }}>
            {f.case_ids.length > 0 && (
              <>
                Cases:{' '}
                {f.case_ids.map((c, i) => (
                  <span key={c}>
                    {i > 0 && ', '}
                    <a href={'#/product/' + c}>{c}</a>
                  </span>
                ))}
                .{' '}
              </>
            )}
            {f.sources.length > 0 && <>Sources: {f.sources.join(', ')}.</>}
          </p>
        )}
        {f?.notice && <p className="note">{f.notice}</p>}
        {f && f.provider !== 'fallback' && f.model && <p className="note">Answered by a language model ({f.model}) from the lookups above.</p>}
      </div>
      {f && f.next.length > 0 && (
        <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
          {f.next.map((n, i) => (
            <button key={i} className={'btn sm' + (n.action ? ' pri' : '')} onClick={() => onNext(n)}>
              {n.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The fallback's cards: the common ones drawn, the rest as a compact summary. */
function Card({ c, onNext }: { c: AskCard; onNext: (n: AskNext) => void }) {
  const d = c.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (c.type === 'cantdo') return <p className="note" role="note">{String(d.what ?? '')}</p>;
  if (c.type === 'clarify')
    return (
      <div style={{ marginTop: 8 }}>
        <p>{String(d.q ?? '')}</p>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {(d.options ?? []).map((o: { label: string; ask?: string }, i: number) => (
            <button key={i} className="btn sm" onClick={() => onNext({ label: o.label, ask: o.ask ?? o.label })}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
    );
  if (c.type === 'table' && Array.isArray(d.cols))
    return (
      <div className="tw" style={{ marginTop: 8 }}>
        {d.title && <b>{String(d.title)}</b>}
        <table>
          <thead>
            <tr>{d.cols.map((h: string) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {(d.rows ?? []).slice(0, 12).map((r: { cells: unknown[] }, i: number) => (
              <tr key={i}>{r.cells.map((x, k) => <td key={k}>{typeof x === 'object' ? JSON.stringify(x) : String(x ?? '')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  if (c.type === 'briefing' && Array.isArray(d.lines))
    return (
      <ul className="aflines">
        {d.lines.map((l: unknown, i: number) => <li key={i}>{typeof l === 'string' ? l : String((l as { t?: string }).t ?? JSON.stringify(l))}</li>)}
      </ul>
    );
  const title = d.title ?? d.label ?? d.case_id ?? d.id;
  return (
    <p className="note" style={{ marginTop: 8 }}>
      <span className="afb">{c.type}</span> {title ? String(title) : ''}
      {d.case_id && <> · <a href={'#/product/' + d.case_id}>Open {String(d.case_id)}</a></>}
    </p>
  );
}
