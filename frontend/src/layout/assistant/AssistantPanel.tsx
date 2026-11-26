/**
 * The one assistant (plan 10, 2.2): Ask Circularity as one panel with two hosts. host="dock" is the Ctrl+J dock
 * (AssistantDock); host="pinned" is the Modeler's agent column, which suppresses the dock while it is mounted. Both read
 * one conversation (store.ts), so nothing is lost when the host changes.
 *
 * The panel is generic: the person's words, a status line, the mode's own Turn body, the mode radio, the limits line,
 * the composer with Stop, queue and the "wrong mode" hint. What a mode says and does is in modes/.
 */
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import { Icon } from '../../components/Icon';
import { AgentsOnThis } from './AgentsOnThis';
import { contextParts } from './context';
import { modeHint } from './intent';
import { MODES } from './modes';
import {
  dropQueued, effectiveMode, newConversation, pickMode, registerPinned, send, setHint, stop, takeDraft, useConv, useUi,
} from './store';
import { statusText } from './status';
import type { AssistantMode } from './types';
import { useAssistantContext } from './useAssistantContext';
import { WaitingStrip } from './WaitingStrip';
import './panel.css';

const SEND_LABEL: Record<AssistantMode, string> = { ask: 'Ask', change: 'Propose', setup: 'Draft' };

export interface AssistantPanelProps {
  host: 'dock' | 'pinned';
  /** dock only: the close button */
  onClose?: () => void;
  /** pinned only: the mode this host opens in (the Modeler's tab); the person can still pick another */
  mode?: AssistantMode;
  /** pinned only: the section sent as the page section (the Modeler's tab) */
  section?: string;
  /**
   * pinned only: what the host shows above the transcript, scrolling with it (the Modeler's Flow tab: What I see,
   * Watching, Proposals, Last simulation; plan 10, 3.3). Its held proposals are left out of "Waiting for you".
   */
  sections?: ReactNode;
}

export function AssistantPanel({ host, onClose, mode: hint, section, sections }: AssistantPanelProps) {
  const conv = useConv();
  const ui = useUi();
  const ctx = useAssistantContext(section);
  const mode = effectiveMode(ctx, { picked: ui.picked, hint: host === 'pinned' ? hint ?? null : ui.hint });
  const def = MODES.find((m) => m.id === mode) ?? MODES[0];
  const [q, setQ] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLElement>(null);
  const running = conv.running !== null;
  const last = conv.turns.at(-1);
  const hintFor = modeHint(mode, q);
  const hintTarget = hintFor && MODES.find((m) => m.id === hintFor.to && !m.unavailable(ctx));

  // a pinned host tells the store, so the dock steps aside and Ctrl+J / openAssistant focus this composer
  useEffect(() => {
    if (host !== 'pinned') return;
    return registerPinned(() => input.current?.focus());
  }, [host]);
  useEffect(() => {
    if (host === 'pinned') setHint(hint ?? null);
  }, [host, hint]);
  // the dock opens on its composer
  useEffect(() => {
    if (host === 'dock') input.current?.focus();
  }, [host]);
  // Rephrase puts a sentence back in the composer: the visible host takes it, once, and the person sends it
  useEffect(() => {
    if (!ui.draft) return;
    const text = takeDraft();
    if (text == null) return;
    setQ(text);
    requestAnimationFrame(() => {
      const el = input.current;
      el?.focus();
      el?.setSelectionRange(text.length, text.length);
    });
  }, [ui.draft]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [conv.turns]);
  // the composer grows from 2 rows to 6
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 6 * 21 + 18) + 'px';
  }, [q]);

  const ask = (text: string, m: AssistantMode = mode) => send(text, m, ctx);
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!q.trim()) return;
    send(q, mode, ctx);
    setQ('');
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape' && running) {
      // Esc stops a running turn first; the overlay stack (which closes the dock) never sees it
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      stop();
    }
  };
  // Alt+1/2/3 picks the mode while focus is anywhere in the panel
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      const m = MODES[['Digit1', 'Digit2', 'Digit3'].indexOf(e.code)];
      if (m && !m.unavailable(ctx)) {
        e.preventDefault();
        pickMode(m.id);
      }
    };
    el.addEventListener('keydown', onKeyDown);
    return () => el.removeEventListener('keydown', onKeyDown);
  }, [ctx]);
  const onRadioKey = (e: KeyboardEvent) => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const ok = MODES.filter((m) => !m.unavailable(ctx));
    const next = ok[(ok.findIndex((m) => m.id === mode) + step + ok.length) % ok.length];
    pickMode(next.id);
    queueMicrotask(() => document.getElementById('as-mode-' + next.id)?.focus());
  };

  return (
    <aside
      className={'as-panel ' + (host === 'pinned' ? 'pinned' : 'as-dock')}
      aria-label="Ask Circularity"
      data-host={host}
      ref={root}
    >
      <header className="as-head">
        <h2>
          <Icon name="spark" /> Ask Circularity
        </h2>
        {host === 'dock' && (
          <button type="button" className="iconbtn" aria-label="Close Ask Circularity (Esc)" title="Close (Esc)" onClick={onClose}>
            <Icon name="close" />
          </button>
        )}
      </header>
      <p className="as-ctx" aria-label="Context">
        Looking at: {contextParts(ctx).join(' · ')}
      </p>
      <div className="as-log" ref={log}>
        <WaitingStrip caseId={ctx.caseId} flow={!!ctx.flow} skipFlow={sections && ctx.flow ? ctx.flow.id : undefined} />
        <AgentsOnThis caseId={ctx.caseId} />
        {sections}
        {conv.turns.length === 0 && <def.Empty ctx={ctx} ask={ask} />}
        {conv.turns.map((t) => {
          const tdef = MODES.find((m) => m.id === t.mode);
          const s = t.status.at(-1);
          return (
            <section key={t.id} className="as-turn" aria-label={'Turn: ' + t.text.slice(0, 40)}>
              <p className="as-user">{t.text}</p>
              {s && <p className={'as-status ' + s.state}>{statusText(s)}</p>}
              {tdef && <tdef.Turn turn={t} ctx={ctx} ask={ask} />}
              {t.error && s?.state === 'failed' && (
                <p className="as-error" role="alert">
                  {t.error}{' '}
                  <button type="button" className="btn sm" onClick={() => send(t.text, t.mode, ctx)}>
                    Retry
                  </button>
                </p>
              )}
            </section>
          );
        })}
      </div>
      {/* announced once, when a turn is done: never on every streamed delta */}
      <div className="sr" aria-live="polite" role="status">
        {!running && last?.status.at(-1) ? statusText(last.status.at(-1)!) : ''}
      </div>
      <form className="as-comp" onSubmit={submit}>
        <div className="as-modes" role="radiogroup" aria-label="Mode">
          {MODES.map((m, i) => {
            const why = m.unavailable(ctx);
            return (
              <button
                key={m.id}
                id={'as-mode-' + m.id}
                type="button"
                role="radio"
                aria-checked={m.id === mode}
                aria-disabled={!!why}
                tabIndex={m.id === mode ? 0 : -1}
                title={(why ?? m.label) + ` (Alt+${i + 1})`}
                className={'as-mode' + (m.id === mode ? ' on' : '') + (why ? ' off' : '')}
                onClick={() => !why && pickMode(m.id)}
                onKeyDown={onRadioKey}
              >
                {m.label}
              </button>
            );
          })}
          <span className="as-limits">{def.limits(ctx)}</span>
        </div>
        <label className="sr" htmlFor={'as-q-' + host}>
          {def.label}
        </label>
        <textarea
          id={'as-q-' + host}
          ref={input}
          rows={2}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          placeholder={def.placeholder}
          maxLength={2000}
          autoComplete="off"
          spellCheck
        />
        {hintFor && hintTarget && (
          <p className="as-hint">
            {hintFor.text}{' '}
            <button
              type="button"
              className="lnk"
              onClick={() => {
                pickMode(hintFor.to);
                send(q, hintFor.to, ctx);
                setQ('');
              }}
            >
              {hintFor.action}
            </button>
          </p>
        )}
        {conv.queue && (
          <p className="as-queue">
            Queued: sends when this answer finishes
            <button type="button" className="iconbtn" aria-label="Drop the queued message" onClick={dropQueued}>
              <Icon name="close" />
            </button>
          </p>
        )}
        <div className="as-comp-b">
          {conv.turns.length > 0 && !running && (
            <button type="button" className="btn sm" onClick={newConversation}>
              New conversation
            </button>
          )}
          {running ? (
            <button type="button" className="btn sm" onClick={stop}>
              Stop
            </button>
          ) : (
            <button type="submit" className="btn pri sm" disabled={!q.trim()}>
              {SEND_LABEL[mode]}
            </button>
          )}
        </div>
      </form>
    </aside>
  );
}
