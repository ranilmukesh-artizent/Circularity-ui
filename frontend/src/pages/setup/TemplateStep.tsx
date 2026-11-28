import { Suspense, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { markStep, packCards, packPrompts, startComposition, type PackCard } from '../../api/compose';
import { useAction } from '../../hooks/useAction';
import { openAssistant } from '../../utils/askBus';
import { orgName, setupPath } from './setupView';

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
 * The first stop before a setup exists: pick the template pack closest to the business (each card says what it handles and
 * its stages), then either describe what is different (the assistant beside this form reads it, asks its one question and
 * drafts) or start from the template as it is. Both make a draft composition; neither publishes anything.
 */
export function TemplateStep({ org, pack, newest, onPack }: { org: string; pack: string; newest: number; onPack: (key: string) => void }) {
  const cards = packCards();
  const cur = cards.find((p) => p.key === pack) ?? cards[0];
  const nav = useNavigate();
  const action = useAction();
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const box = useRef<HTMLTextAreaElement>(null);

  const draft = (t: string) => {
    const body = t.trim();
    if (body.split(/\s+/).filter(Boolean).length < 5) {
      setErr('Write a sentence or two first: what comes back, from whom, and what you do with it.');
      box.current?.focus();
      return;
    }
    setErr('');
    draftedFrom = newest;
    openAssistant({ mode: 'setup', question: body });
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

  return (
    <div className="sup-tpl">
      <fieldset className="sup-packs">
        <legend>1. Which is closest to your business?</legend>
        <div className="sup-packgrid" role="radiogroup" aria-label="Template">
          {cards.map((p) => <Card key={p.key} p={p} on={p.key === cur.key} onPick={() => onPack(p.key)} />)}
        </div>
      </fieldset>

      <form className="sup-start" onSubmit={submit}>
        <label htmlFor="sup-text">2. What is different about yours?</label>
        <ul className="sup-guide" id="sup-guide">
          {GUIDE.map((g) => <li key={g}>{g}</li>)}
        </ul>
        <textarea
          id="sup-text" ref={box} name="description" rows={5} maxLength={4000} value={text}
          placeholder={cur.sample ? cur.sample.slice(0, 200) + (cur.sample.length > 200 ? '…' : '') : 'Describe how returns work in your business…'}
          aria-describedby="sup-guide sup-hint" aria-invalid={!!err}
          onChange={(e) => { setText(e.target.value); if (err) setErr(''); }}
          onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') draft(text); }}
        />
        <p className="err" role="alert" hidden={!err}>{err}</p>
        <p className="note" id="sup-hint">For {orgName(org)}, starting from {cur.name}. The agent drafts configuration, never code, and nothing is published from here.</p>
        <div className="row">
          <button className="btn pri" type="submit">Draft my setup</button>
          <button className="btn" type="button" disabled={action.pending} aria-busy={action.pending} onClick={() => void asIs()}>
            {action.pending && <span className="spin" aria-hidden="true" />}Use the template as it is
          </button>
        </div>
        {action.pending && <p className="note" role="status">Starting your setup from {cur.name}… The agent reads the template first; this can take up to a minute.</p>}
        <Suspense fallback={null}>
          <Samples pack={cur.key} onPick={(p) => { setText(p); setErr(''); box.current?.focus(); }} />
        </Suspense>
      </form>
    </div>
  );
}

/** One template: a radio the size of a card. The stages are drawn as a short line of marks, one a stage. */
function Card({ p, on, onPick }: { p: PackCard; on: boolean; onPick: () => void }) {
  return (
    <label className={'sup-pack' + (on ? ' on' : '')}>
      <input type="radio" name="sup-pack" value={p.key} checked={on} onChange={onPick} />
      <span className="sup-pack-name">{p.name}</span>
      <span className="sup-pack-what">{p.classes.length ? p.classes.slice(0, 3).join(', ') + (p.classes.length > 3 ? ' and more' : '') : `One ${p.unit} at a time`}</span>
      <span className="sup-pack-stages" title={p.stages.join(', ')}>
        <span aria-hidden="true">{p.stages.map((s) => <i key={s} />)}</span>
        {p.stages.length} stages
      </span>
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
