import { useEffect, useState } from 'react';
import { answerQuestion, markStep, readDescription, type Composition, type PackMatch } from '../../../api/compose';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { openAssistant } from '../../../utils/askBus';
import { ChangeSetList } from './ChangeSetList';
import { matchLine, wordCountLine } from './changeSetView';

/**
 * Step 1 of Compose (plan 9, P9-8.18, story X-10; plan 10, T3). Before a composition exists this is a launcher: the conversation
 * (describe, read, one question, draft) happens in Ask Circularity's Set up mode, so there is one place to describe a business.
 * After it, this is the review of what was drafted: the reading line, the matched pack with its score, the one question (answer or
 * Skip), the changes as plain sentences with "assumed" tags and the blocked lines. Nothing here approves anything: "Mark done" only
 * says this step is finished, and a different person approves the composition as a whole.
 */
export function DescribeStep({ composition }: {
  /** the pack's org and key are read from the page by the assistant; kept in the props so Compose passes one set to every step */
  org?: string;
  pack?: string;
  composition: Composition | null;
  onStarted?: (id: number) => void;
}) {
  if (!composition) {
    return (
      <div className="cmp-step">
        <p className="note">Describe how your returns work in a few sentences. Ask Circularity drafts configuration, never code; a person approves it.</p>
        <div className="row">
          <button className="btn sm pri" onClick={() => openAssistant({ mode: 'setup' })}>Describe the business in Ask Circularity</button>
        </div>
      </div>
    );
  }
  return <Drafted c={composition} />;
}

function Drafted({ c }: { c: Composition }) {
  const action = useAction();
  const [match, setMatch] = useState<PackMatch | null>(null);
  const [names, setNames] = useState<Record<string, string> | undefined>();
  const [err, setErr] = useState('');
  const cs = c.change_set;
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const done = c.steps.describe.state === 'done';
  const explicit = c.reading.explicit_controls ?? c.reading.controls.length;
  const m = matchLine(match, c.pack_key, names);

  // the score of the match is the reading's, not stored with the composition
  useEffect(() => {
    let live = true;
    void readDescription(c.text, c.org_unit_id).then((r) => {
      if (!live || !r.ok) return;
      setMatch(r.output.match);
      setNames(r.output.pack_names);
    });
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
      <p>{wordCountLine(c.reading.word_count, explicit, c.reading.systems)}</p>
      <p className={m.amber ? 'cmp-amber' : undefined}>{m.text}</p>
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
      <ChangeSetList cs={cs} />
      {cs.outline && (
        <p className="note">
          Guardrails you stated: {cs.outline.stated.join(', ') || 'none'}. From the pack: {cs.outline.from_pack.join(', ') || 'none'}.
          Research additions: {cs.outline.research_additions.join(', ') || 'none'}. Asset fields: {cs.outline.asset_fields.join(', ')}.
        </p>
      )}
      <p><b>Systems:</b> {cs.systems.map((s) => s.name).join(', ') || 'none named'}</p>
      <p><b>KPIs:</b> {cs.kpis.join(', ') || 'none'}</p>
      {err && <p className="err" role="alert">{err}</p>}
      {editable && <button className="btn sm pri" disabled={action.pending || done || !!cs.question} onClick={() => void mark()}>{done ? 'Done' : 'Mark done'}</button>}
      {editable && cs.question && !done && <span className="note"> Answer or skip the question first.</span>}
    </div>
  );
}
