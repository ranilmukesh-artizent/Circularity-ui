import { useEffect, useState } from 'react';
import { answerQuestion, markStep, packPrompts, readDescription, startComposition, type Composition, type PackMatch } from '../../../api/compose';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';

const MAX = 4000;

/** The pack's sample descriptions as buttons (a pack that has none shows none). */
function Prompts({ pack, onPick }: { pack: string; onPick: (t: string) => void }) {
  const list = packPrompts(pack);
  return (
    <div className="cmp-prompts" aria-label="Sample descriptions">
      {list.map((p) => (
        <button key={p} className="btn sm" onClick={() => onPick(p)} title={p}>{p.length > 56 ? p.slice(0, 56) + '…' : p}</button>
      ))}
    </div>
  );
}

/**
 * Step 1 of Compose (plan 9, P9-8.18, story X-10): describe the business. Before a composition exists: a text box and the pack's
 * sample prompts. After `startComposition`: the reading log, the matched pack with its score, the one question (answer or Skip),
 * then the drafted changes, systems and KPIs. Operations the person did not state carry an "assumed" badge. Nothing here approves
 * anything: "Mark done" only says this step is finished, and a different person approves the composition as a whole.
 */
export function DescribeStep({ org, pack, composition, onStarted }: {
  org: string;
  /** the pack whose sample prompts are offered, and the pack the draft starts from */
  pack: string;
  composition: Composition | null;
  onStarted: (id: number) => void;
}) {
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const action = useAction();

  const start = async () => {
    setErr('');
    const r = await action.run(() => startComposition(org, text.trim(), pack), { all: setErr });
    if (!r.ok) return;
    toast(r.output.log ?? 'Drafted the changes.');
    onStarted(r.output.id);
  };

  if (!composition) {
    return (
      <div className="cmp-step">
        <p className="note">Say how your returns work in a few sentences. The agent drafts configuration, never code; a person approves it.</p>
        <Prompts pack={pack} onPick={setText} />
        <textarea aria-label="Describe your business" rows={5} maxLength={MAX} value={text} onChange={(e) => setText(e.target.value)} className="cmp-text" />
        <div className="row">
          <button className="btn sm pri" disabled={action.pending || !text.trim()} onClick={() => void start()}>Draft the changes</button>
          <span className="note">{text.length}/{MAX}</span>
        </div>
        {err && <p className="err" role="alert">{err}</p>}
      </div>
    );
  }
  return <Drafted c={composition} />;
}

function Drafted({ c }: { c: Composition }) {
  const action = useAction();
  const [match, setMatch] = useState<PackMatch | null>(null);
  const [err, setErr] = useState('');
  const cs = c.change_set;
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const done = c.steps.describe.state === 'done';

  // the score of the match is the reading's, not stored with the composition
  useEffect(() => {
    let live = true;
    void readDescription(c.text, c.org_unit_id).then((r) => live && r.ok && setMatch(r.output.match));
    return () => { live = false; };
  }, [c.text, c.org_unit_id]);

  const answer = async (id: string) => {
    setErr('');
    await action.run(() => answerQuestion(c.id, id), { all: setErr });
  };
  const mark = async () => {
    const r = await action.run(() => markStep(c.id, 'describe'), { all: setErr });
    if (r.ok) toast('The describe step is done.');
  };

  return (
    <div className="cmp-step">
      <h4>What the agent read{c.reading.by_model ? ' (drafted by a model, checked by the rules)' : ''}</h4>
      <p>
        {c.reading.word_count} words · {c.reading.controls.length} explicit control{c.reading.controls.length === 1 ? '' : 's'}
        {c.reading.systems.length > 0 && ` · systems: ${c.reading.systems.join(', ')}`}
      </p>
      <p>
        <b>{match?.nearest_only ? 'Nearest pack' : 'Matched pack'}:</b> {c.pack_key}
        {match && ` (${Math.round(match.score)})`}
      </p>
      {cs.question && editable && (
        <div className="cmp-question">
          <b>{cs.question.text}</b>
          <div className="row">
            {cs.question.options.map((o) => (
              <button key={o.id} className="btn sm" disabled={action.pending} onClick={() => void answer(o.id)}>{o.label}</button>
            ))}
            <button className="btn sm" disabled={action.pending} onClick={() => void answer('skip')}>Skip</button>
          </div>
        </div>
      )}
      <h4>Drafted for {cs.pack} v{cs.base_version}{cs.by_model ? ' (by a model)' : ''}</h4>
      <ul className="cmp-ops">
        {cs.ops.map((o) => (
          <li key={o.id}>
            {o.op}: {JSON.stringify(Object.fromEntries(Object.entries(o).filter(([k]) => !['id', 'op', 'by', 'note'].includes(k))))}
            {cs.assumed.includes(o.id) && <span className="chip line" title="You did not state this; check it">assumed</span>}
          </li>
        ))}
        {cs.ops.length === 0 && <li className="note">No changes to the pack.</li>}
      </ul>
      {cs.blocked.map((b, i) => <p key={i} className="err">Blocked ({b.guardrail}): {b.text}</p>)}
      <p><b>Systems:</b> {cs.systems.map((s) => s.name).join(', ') || 'none named'}</p>
      <p><b>KPIs:</b> {cs.kpis.join(', ') || 'none'}</p>
      {err && <p className="err" role="alert">{err}</p>}
      {editable && <button className="btn sm pri" disabled={action.pending || done || !!cs.question} onClick={() => void mark()}>{done ? 'Done' : 'Mark done'}</button>}
      {editable && cs.question && !done && <span className="note"> Answer or skip the question first.</span>}
    </div>
  );
}
