import { Suspense, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from 'react';
import { useNavigate } from 'react-router';
import { markStep, packCards, packPrompts, startComposition, type PackCard } from '../../api/compose';
import { useAction } from '../../hooks/useAction';
import { AssistantPanel } from '../../layout/assistant/AssistantPanel';
import { newConversation, send, useConv } from '../../layout/assistant/store';
import { useAssistantContext } from '../../layout/assistant/useAssistantContext';
import { filterPacks, orgName, setupPath, suggestPack } from './setupView';

/** The newest composition when a draft was asked for, until a newer one shows. Outside the component: the list of compositions
 *  is a Suspense read, and a remount while it refetches must not forget that a draft is on its way. */
let draftedFrom: number | null = null;

/** The composition to move to, once: the newest one, when it is newer than the one a draft was asked from. */
export function takeDrafted(newest: number): number | null {
  if (draftedFrom === null || newest <= draftedFrom) return null;
  draftedFrom = null;
  return newest;
}

/** What a good description covers. A sentence on each is enough; the agent asks about what is missing. */
const GUIDE = [
  'What comes back, and from whom?',
  'How do you judge its condition?',
  'Where can it go next: back into use, resale, parts, recycling?',
  'Who signs off, and above what value?',
];

/**
 * The first stop before a setup exists, as one conversation (28 Nov 2026): the description box comes first and is the only
 * place to type. The template it starts from sits in the box's footer and is changed in a picker (a dialog with a search),
 * and the page offers another template when the words read like one. "Draft my setup" hands the text to the assistant,
 * whose transcript then takes the form's place (it asks its one question there and drafts); "Use the template as it is"
 * skips the conversation. Both make a draft composition; neither publishes anything.
 */
export function TemplateStep({ org, pack, newest, onPack }: { org: string; pack: string; newest: number; onPack: (key: string) => void }) {
  const cards = packCards();
  const cur = cards.find((p) => p.key === pack) ?? cards[0];
  const nav = useNavigate();
  const action = useAction();
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const box = useRef<HTMLTextAreaElement>(null);

  const ctx = useAssistantContext();
  const talking = useConv().turns.some((t) => t.mode === 'setup');
  const dlg = useRef<HTMLDialogElement>(null);
  const other = useMemo(() => suggestPack(text, cards, cur.key), [text, cards, cur.key]);

  const draft = (t: string) => {
    const body = t.trim();
    if (body.split(/\s+/).filter(Boolean).length < 5) {
      setErr('Write a sentence or two first: what comes back, from whom, and what you do with it.');
      box.current?.focus();
      return;
    }
    setErr('');
    draftedFrom = newest;
    send(body, 'setup', ctx); // the transcript takes the form's place
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    draft(text);
  };
  const asIs = async () => {
    setErr('');
    const r = await action.run(() => startComposition(org, `Use the ${cur.name} template as it is, with no changes.`, cur.key), { all: setErr });
    if (!r.ok) return;
    await markStep(r.output.id, 'describe'); // nothing was described, so there is nothing to check: the template stop is done
    nav(setupPath({ compose: r.output.id, step: 'flow' }), { replace: true });
  };
  const again = () => {
    draftedFrom = null;
    newConversation();
  };

  if (talking) {
    return (
      <div className="sup-tpl">
        <div className="sup-talk-h">
          <p className="note">For {orgName(org)}, starting from {cur.name}. The assistant asks at most one question, then drafts. Nothing is published from here.</p>
          <button type="button" className="btn sm" onClick={again}>Start again</button>
        </div>
        <div className="sup-talk">
          <AssistantPanel host="pinned" mode="setup" />
        </div>
      </div>
    );
  }

  return (
    <div className="sup-tpl">
      <form className="sup-start" onSubmit={submit}>
        <label htmlFor="sup-text">Tell the assistant how returns work in your business</label>
        <div className={'sup-box' + (err ? ' bad' : '')}>
          <textarea
            id="sup-text" ref={box} name="description" rows={4} maxLength={4000} value={text}
            placeholder={cur.sample ? cur.sample.slice(0, 200) + (cur.sample.length > 200 ? '…' : '') : 'Describe how returns work in your business…'}
            aria-describedby="sup-guide sup-hint" aria-invalid={!!err}
            onChange={(e) => { setText(e.target.value); if (err) setErr(''); }}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') draft(text); }}
          />
          <div className="sup-box-f">
            <button type="button" className="sup-from" aria-haspopup="dialog" onClick={() => dlg.current?.showModal()}>
              <span className="sup-from-k">Starting from</span>
              <span className="sup-from-v">{cur.name}</span>
              <Marks p={cur} />
              <span className="sup-from-c">Change</span>
            </button>
            <button className="btn pri" type="submit">Draft my setup</button>
          </div>
        </div>
        <p className="err" role="alert" hidden={!err}>{err}</p>
        {other && (
          <p className="sup-other" role="status">
            This reads like {other.name}.{' '}
            <button type="button" className="lnk" onClick={() => onPack(other.key)}>Start from that template</button>
          </p>
        )}
        <ul className="sup-guide" id="sup-guide">
          {GUIDE.map((g) => <li key={g}>{g}</li>)}
        </ul>
        <Suspense fallback={null}>
          <Samples pack={cur.key} onPick={(p) => { setText(p); setErr(''); box.current?.focus(); }} />
        </Suspense>
        <p className="note sup-asis" id="sup-hint">
          <span>For {orgName(org)}. The agent drafts configuration, never code, and nothing is published from here. Nothing to change?</span>
          <button className="btn sm" type="button" disabled={action.pending} aria-busy={action.pending} onClick={() => void asIs()}>
            {action.pending && <span className="spin" aria-hidden="true" />}Use the template as it is
          </button>
        </p>
        {action.pending && <p className="note" role="status">Starting your setup from {cur.name}… The agent reads the template first; this can take up to a minute.</p>}
      </form>
      <PackDialog dlg={dlg} cards={cards} cur={cur.key} onPick={(k) => { dlg.current?.close(); if (k !== cur.key) onPack(k); }} />
    </div>
  );
}

/** The stages of a template as a short line of marks, one a stage. */
function Marks({ p }: { p: PackCard }) {
  return (
    <span className="sup-pack-stages" title={p.stages.join(', ')}>
      <span aria-hidden="true">{p.stages.map((x) => <i key={x} />)}</span>
      {p.stages.length} stages
    </span>
  );
}

/** The template picker: a native dialog (focus stays inside, Esc closes) with a search over names, industries and classes. */
function PackDialog({ dlg, cards, cur, onPick }: { dlg: RefObject<HTMLDialogElement>; cards: PackCard[]; cur: string; onPick: (key: string) => void }) {
  const [q, setQ] = useState('');
  // the arrow keys move between the cards without choosing; a click, Enter or Space chooses and closes
  const [sel, setSel] = useState(cur);
  useEffect(() => setSel(cur), [cur]);
  const shown = filterPacks(cards, q);
  return (
    // a click on the backdrop (the dialog element itself) closes it; Esc is the keyboard way
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events
    <dialog ref={dlg} className="sup-dlg" aria-labelledby="sup-dlg-h" onClick={(e) => { if (e.target === e.currentTarget) dlg.current?.close(); }} onClose={() => { setQ(''); setSel(cur); }}>
      <div className="sup-dlg-in">
        <header className="sup-dlg-h">
          <h3 id="sup-dlg-h">Choose the template closest to your business</h3>
          <button type="button" className="btn sm" onClick={() => dlg.current?.close()}>Close</button>
        </header>
        <input
          type="search" className="sup-dlg-q" name="template-search" autoComplete="off" spellCheck={false} value={q}
          placeholder="Phones, tools, vehicles…" aria-label="Search templates"
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="sup-packgrid" role="radiogroup" aria-label="Template">
          {shown.map((p) => <Card key={p.key} p={p} on={p.key === sel} onMove={() => setSel(p.key)} onPick={() => onPick(p.key)} />)}
        </div>
        {!shown.length && <p className="note" role="status">No template matches "{q}". Pick the closest one; you say what is different in your own words.</p>}
        <p className="note">Each template is a starting point: its stages, routes and guardrails. You change it by describing your business.</p>
      </div>
    </dialog>
  );
}

/** One template: a radio the size of a card. The stages are drawn as a short line of marks, one a stage. */
function Card({ p, on, onMove, onPick }: { p: PackCard; on: boolean; onMove: () => void; onPick: () => void }) {
  // a mouse click has detail > 0; the click a browser fires for an arrow key or Space has none, so the keys are read directly
  const key = (e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(); } };
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events
    <label className={'sup-pack' + (on ? ' on' : '')} onClick={(e) => { if (e.detail > 0) onPick(); }}>
      <input type="radio" name="sup-pack" value={p.key} checked={on} onChange={onMove} onKeyDown={key} />
      <span className="sup-pack-name">{p.name}</span>
      <span className="sup-pack-what">{p.classes.length ? p.classes.slice(0, 3).join(', ') + (p.classes.length > 3 ? ' and more' : '') : `One ${p.unit} at a time`}</span>
      <Marks p={p} />
    </label>
  );
}

function Samples({ pack, onPick }: { pack: string; onPick: (text: string) => void }) {
  const list = packPrompts(pack);
  if (!list.length) return null;
  return (
    <div className="sup-samples">
      <p className="note">Or start from a sample and change it:</p>
      <ul>
        {list.slice(0, 3).map((p) => (
          <li key={p}><button type="button" className="sup-sample" onClick={() => onPick(p)}>{p}</button></li>
        ))}
      </ul>
    </div>
  );
}
