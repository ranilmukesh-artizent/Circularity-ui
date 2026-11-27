/* eslint-disable check-file/filename-naming-convention -- plan 10 names the mode files modes/ask.tsx, change.tsx, setup.tsx */
/**
 * Ask mode (plan 10): POST /api/ask as a stream, read only. The answer turn, its cards, the basis line (2.5), the
 * suggested next steps through a preview card (2.3) and the audit line (2.9), moved from the old AskPanel. Ask never
 * acts: a next step runs only on the person's own "Run it", through invoke() like any other click.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { invoke } from '../../../api/actions';
import { ask as askApi, askStartersFor, type AskCard, type AskNext, type AskStarters } from '../../../api/ask';
import { ref } from '../../../api/client';
import { can, canPage, currentAccount } from '../../../api/session';
import { toast } from '../../../components/toast';
import { refused } from '../../../hooks/useAction';
import { askContext } from '../context';
import { PreviewCard } from '../PreviewCard';
import { argsText, selectStarters, startersQuery, toolWords, usedLine } from './starters';
import { applyAskEvent, askData } from '../turns';
import type { AssistantContext, AssistantMode, ModeDef, Turn } from '../types';

let conversation: string | null = null;
/** New conversation: the server's conversation id is forgotten with the transcript. */
export const resetAskConversation = (): void => {
  conversation = null;
};

/** Where a created draft opens. */
/** The server's label says what was made ("Draft WF-131 · name", "Held for you · the flow change"); the link says where. */
const createdLink = (kind: string): string =>
  kind === 'workflow' ? 'Open in Workflow Studio' : kind === 'proposal' ? 'Review under Waiting for you' : 'Open in Modeler';

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function starters(): string[] {
  const role = currentAccount()?.role ?? '';
  try {
    return ref('AF_STARTERS')[role] ?? [];
  } catch {
    return [];
  }
}

export const askMode: ModeDef = {
  id: 'ask',
  label: 'Ask',
  placeholder: 'Ask about a case, a source, a figure…',
  limits: (ctx) => `answers from your data · drafts only, never publishes · role: ${cap(ctx.role || 'unknown')}`,
  unavailable: () => null,
  async send(text, ctx, io) {
    await askApi(text, {
      context: askContext(ctx),
      conversationId: conversation,
      signal: io.signal,
      onEvent: (e) => {
        if (e.type === 'start' || e.type === 'final') conversation = e.conversation_id;
        io.patch((t) => applyAskEvent(t, e));
      },
    });
  },
  Turn: AskTurn,
  Empty: AskEmpty,
};

function AskEmpty({ ctx, ask }: { ctx: AssistantContext; ask: (text: string) => void }) {
  const [server, setServer] = useState<AskStarters>({ pack: null, starters: [] });
  const { page, section, case_id } = startersQuery(ctx);
  useEffect(() => {
    let live = true;
    askStartersFor({ page, section, case_id }).then((r) => live && setServer(r), () => live && setServer({ pack: null, starters: [] }));
    return () => {
      live = false;
    };
  }, [page, section, case_id]);
  const list = selectStarters(starters(), server, ctx);
  return (
    <div className="as-empty">
      <p className="as-note">Answers from your data, within what your role may see. Drafts only, never publishes.</p>
      <div className="as-starters">
        {list.map((s) => (
          <button key={s} type="button" className="btn sm" onClick={() => ask(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function AskTurn({ turn, ask }: { turn: Turn; ask: (text: string, mode?: AssistantMode) => void }) {
  const nav = useNavigate();
  const [step, setStep] = useState<AskNext | null>(null);
  const [ran, setRan] = useState<string | null>(null);
  const d = askData(turn);
  const f = d.final;

  function onNext(n: AskNext) {
    if (n.ask) return ask(n.ask, 'ask');
    if (n.approve) return nav('/product/' + n.approve);
    if (n.go) return nav('/' + n.go.replace(/^#\//, ''));
    if (n.action) setStep(n);
  }

  async function run(n: AskNext) {
    setStep(null);
    if (!n.action) return;
    const r = await invoke(n.action, n.input ?? {});
    if (refused(r)) return;
    setRan(n.label);
    toast(n.label + ': done.');
  }

  return (
    <div className="as-ans">
      {d.text && <div className="as-text">{d.text}</div>}
      {d.created?.map((c) => (
        <p key={c.kind + c.id} className="as-note as-created">
          {c.label || `Draft ${c.id}`} —{' '}
          <a href={'#' + c.href} onClick={(e) => { e.preventDefault(); nav(c.href); }}>{createdLink(c.kind)}</a>
        </p>
      ))}
      {f?.cards.map((c, i) => <Card key={i} c={c} q={turn.text} onNext={onNext} />)}
      {f && (f.case_ids.length > 0 || f.sources.length > 0) && (
        <p className="as-note">
          {f.case_ids.length > 0 && (
            <>
              Cases:{' '}
              {f.case_ids.map((c, i) => (
                <span key={c}>
                  {i > 0 && ', '}
                  <a className="mono" href={'#/product/' + c}>{c}</a>
                </span>
              ))}
              .{' '}
            </>
          )}
          {f.sources.length > 0 && <>Sources: {f.sources.join(', ')}.</>}
        </p>
      )}
      {f?.notice && <p className="as-basis">{f.notice}</p>}
      {f && f.by_model && f.model && <p className="as-basis">Answered by a language model ({f.model}) from the lookups above.</p>}
      {step && <NextStepCard n={step} onRun={() => void run(step)} onDismiss={() => setStep(null)} />}
      {ran && <p className="as-status">Ran "{ran}" as you · see History</p>}
      {f && f.next.length > 0 && !step && (
        <div className="as-next">
          {f.next.map((n, i) => (
            <button key={i} type="button" className="btn sm" onClick={() => onNext(n)}>
              {n.label}
            </button>
          ))}
        </div>
      )}
      {d.tools.length > 0 && (
        <details className="as-audit">
          <summary>{usedLine(d.tools)}</summary>
          <ul aria-label="Lookups">
            {d.tools.map((x, i) => (
              <li key={i} title={x.message ?? ''}>
                {cap(toolWords(x.name))}
                {argsText(x.args ?? {}) && <> · <span className="mono">{argsText(x.args ?? {})}</span></>}
                {!x.ok && <> · refused{x.message ? ': ' + x.message : ''}</>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {f && (
        <p className="as-note">{canPage('mcp') ? <a href="#/mcp/calls">Call log</a> : 'Logged as Ask Circularity'}</p>
      )}
    </div>
  );
}

/**
 * The intent preview (2.3) for a suggested step that runs an action: the shared PreviewCard, titled with the step's
 * label; what changes is the action's verb from the catalogue; the limits say it runs as the person. Run it / Not now.
 */
function NextStepCard({ n, onRun, onDismiss }: { n: AskNext; onRun: () => void; onDismiss: () => void }) {
  return (
    <PreviewCard
      title={'Proposed: ' + n.label}
      basis="Suggested by Ask Circularity"
      sections={[{ heading: 'What changes', lines: [{ text: 'Runs ' + n.action + '.', sign: '~' }] }]}
      limits="Runs as you, with your role's checks and approvals. Undo it from the case if the action allows."
      actions={[
        { label: 'Run it', primary: true, onClick: onRun },
        { label: 'Not now', onClick: onDismiss },
      ]}
    />
  );
}

/** The fallback's cards: the common ones drawn, the rest as a compact summary. */
function Card({ c, q, onNext }: { c: AskCard; q: string; onNext: (n: AskNext) => void }) {
  const d = c.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (c.type === 'wfdiff' && Array.isArray(d.steps)) {
    // the demo's workflow draft card; the draft is created only on the person's confirmed click, or refined in the
    // Workflow Studio builder with the same description
    const steps = d.steps as { id: string; label: string; kind: string; fixed: boolean }[];
    const errors: string[] = d.errors ?? [], warnings: string[] = d.warnings ?? [];
    return (
      <div className="as-sub">
        <b>{String(d.title ?? 'Workflow draft')} · {String(d.name ?? '')}</b>
        <p className="as-note">{steps.filter((s) => !s.fixed).length} new steps shown as ghosts · checks: {errors.length} errors, {warnings.length} warnings</p>
        <ol className="afplan afwf">
          {steps.map((s) => (
            <li key={s.id} className={s.fixed ? 'fx' : 'ghost'}><b>{s.label}</b>
              <span className="note">{s.fixed ? 'Fixed step (Circularity owns it; never moved or removed)' : 'New step · ' + s.kind}</span></li>
          ))}
        </ol>
        {errors.length ? <p className="callout bad"><b>Checks:</b> {errors.join(' ')}</p> : <p className="as-note">Checks: no errors. The draft is never published by the agent.</p>}
        {can('manageWorkflows') && (
          <div className="as-next">
            <button type="button" className="btn sm" onClick={() => onNext({ label: 'Accept all as a new draft', action: 'workflow.create',
              input: { type: 'ingest', src: d.src, name: d.name, graph: d.graph, desc: 'AI-suggested draft. ' } })}>Accept all as a new draft</button>
            <button type="button" className="btn sm" onClick={() => onNext({ label: 'Refine in Workflow Studio', go: 'integration/studio?build=' + encodeURIComponent(q) })}>
              Refine in Workflow Studio</button>
          </div>
        )}
      </div>
    );
  }
  if (c.type === 'cantdo') return <p className="as-note" role="note">{String(d.what ?? '')}</p>;
  if (c.type === 'clarify')
    return (
      <div className="as-sub">
        <p>{String(d.q ?? '')}</p>
        <div className="as-next">
          {(d.options ?? []).map((o: { label: string; ask?: string }, i: number) => (
            <button key={i} type="button" className="btn sm" onClick={() => onNext({ label: o.label, ask: o.ask ?? o.label })}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
    );
  if (c.type === 'table' && Array.isArray(d.cols))
    // the dock is 400px: the table scrolls sideways inside its own box (focusable, so the keyboard scrolls it too), and
    // a line under it says so when it has more columns than fit (QA B-33)
    return (
      <div className="as-sub as-tablecard">
        {d.title && <b>{String(d.title)}</b>}
        {/* a scrollable region is focusable so a keyboard can scroll it (WCAG 2.1.1) */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
        <div className="as-table" role="region" aria-label={String(d.title ?? 'Answer table')} tabIndex={0}>
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
        {d.cols.length > 3 && <p className="as-note">{d.cols.length} columns · scroll sideways to see them all</p>}
      </div>
    );
  if (c.type === 'briefing' && Array.isArray(d.lines))
    return (
      <ul className="aflines">
        {d.lines.map((l: unknown, i: number) => <li key={i}>{typeof l === 'string' ? l : String((l as { text?: string; t?: string }).text ?? (l as { t?: string }).t ?? JSON.stringify(l))}</li>)}
      </ul>
    );
  const title = d.title ?? d.label ?? d.case_id ?? d.id;
  return (
    <p className="as-note as-sub">
      <span className="as-prov">{c.type}</span> {title ? String(title) : ''}
      {d.case_id && <> · <a href={'#/product/' + d.case_id}>Open {String(d.case_id)}</a></>}
    </p>
  );
}
