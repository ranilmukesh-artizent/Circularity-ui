import { Suspense, useState, useSyncExternalStore } from 'react';
import { answerQuestion, packPrompts, readDescription, startComposition, type Composition, type PackMatch } from '../../../api/compose';
import { can } from '../../../api/session';
import { useAction } from '../../../hooks/useAction';
import { ChangeSetList } from '../../../pages/modeler/compose/ChangeSetList';
import { changeTitle, matchLine, setupHref, wordCountLine } from '../../../pages/modeler/compose/changeSetView';
import type { AssistantContext, ModeDef, Status, Turn } from '../types';
import './SetupMode.css';

/**
 * Set up mode of the one assistant (plan 10, section 2.1, task T3): describe a business, `compose.start` reads it and drafts the
 * changes, `config.read` gives the match score, the pack's one question is answered (or skipped) with `compose.answer`, and the
 * drafted changes are listed as plain sentences with assumed and blocked lines. "Open in Set up" then goes to the Modeler's Set up
 * tab, where mapping, agents, approval and publishing stay a work surface. Nothing here approves or publishes anything: it makes a
 * draft composition, and a different person approves it.
 */

/** What a Set up turn keeps in `Turn.data`: the composition it made (the latest copy is in the store below). */
export interface SetupData { id: number; org: string; pack: string }

interface Entry { comp: Composition; match: PackMatch | null }

// the latest composition and match of each turn, outside React so a turn keeps them when the panel moves between hosts
const entries = new Map<number, Entry>();
const subs = new Set<() => void>();
const put = (comp: Composition, match?: PackMatch | null) => {
  entries.set(comp.id, { comp, match: match === undefined ? (entries.get(comp.id)?.match ?? null) : match });
  subs.forEach((f) => f());
};
const useEntry = (id: number | undefined): Entry | undefined =>
  useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => void subs.delete(f);
    },
    () => (id === undefined ? undefined : entries.get(id)),
  );

const wordCount = (t: string): number => t.trim().split(/\s+/).filter(Boolean).length;

const failed = (msg: string, code?: string) => (code === 'network' ? 'Could not reach Circularity. Your text is kept.' : msg);

async function send(text: string, ctx: AssistantContext, io: { signal: AbortSignal; patch(f: (t: Turn) => Turn): void }): Promise<void> {
  const { org, pack } = ctx;
  const set = (status: Status[], error?: string) => io.patch((t) => ({ ...t, status, ...(error !== undefined ? { error } : {}) }));
  if (!org || !pack) {
    set([{ verb: 'Could not start', item: 'the description', limit: 'no template chosen', state: 'failed' }], 'Open the Modeler and pick a template and organisation first. Set up drafts for that pair.');
    return;
  }
  const words = wordCount(text);
  set([{ verb: 'Reading', item: `${words} word${words === 1 ? '' : 's'} for ${org}`, limit: 'drafts only', state: 'working' }]);
  const r = await startComposition(org, text.trim(), pack);
  if (!r.ok) {
    set([{ verb: 'Could not read', item: `${words} words`, limit: 'nothing saved', state: 'failed' }], failed(r.error.message, r.error.code));
    return;
  }
  const comp = r.output;
  put(comp);
  io.patch((t) => ({ ...t, data: { id: comp.id, org, pack } satisfies SetupData }));
  if (io.signal.aborted) {
    // compose.start has made a draft composition: say so (it is never published, and a person can discard it in Set up)
    set([{ verb: 'Stopped', item: `after composition ${comp.id} was drafted`, limit: 'nothing is published', state: 'stopped' }]);
    return;
  }
  const read = await readDescription(text.trim(), org); // the match score is the reading's, not stored with the composition
  const match = read.ok ? read.output.match : null;
  put(comp, match);
  const found = matchLine(match, comp.pack_key);
  set([{ verb: 'Read', item: `${words} word${words === 1 ? '' : 's'}`, limit: found.text.replace(/\. .*$/, ''), state: 'done' }]);
}

function Question({ c, onError }: { c: Composition; onError: (m: string) => void }) {
  const action = useAction();
  const q = c.change_set.question;
  if (!q) return null;
  const answer = async (id: string) => {
    onError('');
    const r = await action.run(() => answerQuestion(c.id, id), { all: (m, code) => onError(failed(m, code)) });
    if (r.ok) put(r.output);
  };
  return (
    <div className="st-question" role="group" aria-label="A question from Ask Circularity">
      <p className="st-q">{q.text}</p>
      <div className="st-opts">
        {q.options.map((o) => (
          <button key={o.id} className="btn sm" disabled={action.pending} onClick={() => void answer(o.id)}>{o.label}</button>
        ))}
        <button className="btn sm" disabled={action.pending} onClick={() => void answer('skip')}>Skip</button>
      </div>
    </div>
  );
}

function SetupTurn({ turn }: { turn: Turn }) {
  const d = turn.data as SetupData | null;
  const e = useEntry(d?.id);
  const [err, setErr] = useState('');
  if (!d || !e) return null;
  const { comp, match } = e;
  const cs = comp.change_set;
  const explicit = comp.reading.explicit_controls ?? comp.reading.controls.length;
  const m = matchLine(match, comp.pack_key);
  const pending = !!cs.question && (comp.status === 'draft' || comp.status === 'sent_back');
  return (
    <div className="st-turn">
      <p className="st-line">{wordCountLine(comp.reading.word_count, explicit, comp.reading.systems)}</p>
      <p className={m.amber ? 'st-line st-amber' : 'st-line'}>{m.text}</p>
      <p className="st-basis">{comp.reading.by_model ? "Drafted by a language model, checked by the pack's rules" : 'Read by the rules'}</p>
      {pending && <Question c={comp} onError={setErr} />}
      {err && <p className="err" role="alert">{err}</p>}
      <h4 className="st-title">{changeTitle(cs)}</h4>
      <ChangeSetList cs={cs} />
      {pending && <p className="st-basis">Answer or skip the question to finish drafting.</p>}
      <p className="st-foot">
        <a className="btn sm pri" href={'#' + setupHref(comp.id, { template: d.pack, org: d.org })}>Open in Set up</a>
        <span className="st-basis">Composition {comp.id} {'·'} nothing is published; a different person approves it.</span>
      </p>
    </div>
  );
}

function Starters({ ctx, ask }: { ctx: AssistantContext; ask: (text: string, mode?: 'setup') => void }) {
  const list = ctx.pack ? packPrompts(ctx.pack) : [];
  return (
    <div className="st-starters" aria-label="Sample descriptions">
      {list.map((p) => (
        <button key={p} className="btn sm st-start" onClick={() => ask(p, 'setup')} title={p}>{p}</button>
      ))}
    </div>
  );
}

function SetupEmpty({ ctx, ask }: { ctx: AssistantContext; ask: (text: string, mode?: 'setup') => void }) {
  return (
    <div className="st-empty">
      <p>{ctx.org ? `Describe how returns work for ${ctx.org} in a few sentences. Drafts only: nothing is published; a different person approves it.` : 'Open the Modeler and pick a template and organisation, then describe how returns work.'}</p>
      {ctx.composeId != null && (
        <p className="st-basis">
          Composition {ctx.composeId} is open in Set up. A new description drafts a new composition beside it.
          {ctx.page !== 'modeler' && (
            <>
              {' '}
              <a href={'#' + setupHref(ctx.composeId, { template: ctx.pack, org: ctx.org })}>Open composition {ctx.composeId}</a>
            </>
          )}
        </p>
      )}
      {ctx.org && ctx.pack && (
        <Suspense fallback={<p className="note">Loading sample descriptions{'…'}</p>}>
          <Starters ctx={ctx} ask={ask} />
        </Suspense>
      )}
    </div>
  );
}

export const setupMode: ModeDef = {
  id: 'setup',
  label: 'Set up',
  placeholder: 'Describe how your returns work…',
  limits: (ctx) => `Drafts a composition for ${ctx.org ?? 'this organisation'}. Nothing is published; a different person approves.`,
  unavailable: () => (can('managePacks') ? null : 'Your role cannot manage packs.'),
  send,
  Turn: SetupTurn,
  Empty: SetupEmpty,
};
