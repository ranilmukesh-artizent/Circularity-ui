import { useState } from 'react';
import { draftChangeSet, readDescription, type ChangeSet, type DescriptionRead, type Drafted } from '../../api/compose';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const MAX = 4000;

/**
 * "Describe your business" (plan 9, P9-2.7, story X-02): type a description, read the configuration agent's reading log (word
 * count, controls, systems), the matched pack with its score ("Nearest pack" below the bar), answer its one question or skip,
 * then see the change set with "assumed" badges and the blocked items with the guardrail named. "Send for approval" holds the
 * overlay draft as one proposal for a person; nothing is published (a person approves through the overlay's maker-checker).
 */
export function DescribeDialog({ org, prompts, onClose }: { org: string; prompts: string[]; onClose: () => void }) {
  const [text, setText] = useState('');
  const [read, setRead] = useState<DescriptionRead | null>(null);
  const [set, setSet] = useState<ChangeSet | null>(null);
  const [sent, setSent] = useState<Drafted | null>(null);
  const [err, setErr] = useState('');
  const action = useAction();

  const readIt = async () => {
    setErr('');
    setSet(null);
    setSent(null);
    const r = await action.run(() => readDescription(text, org), { all: setErr });
    if (r.ok) setRead(r.output);
  };
  const draft = async (answer?: string) => {
    setErr('');
    const r = await action.run(() => draftChangeSet(text, org, answer), { all: setErr });
    if (!r.ok) return;
    setSet(r.output.change_set);
    setSent(r.output);
    toast(r.output.log ?? 'Held for approval.');
  };

  const q = read?.question ?? null;
  return (
    <Modal title="Describe your business" wide onClose={onClose}>
      <p className="note">Say how your returns work in a few sentences. The agent drafts configuration, never code; a person approves it.</p>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {prompts.map((p) => (
          <button key={p} className="btn sm" onClick={() => setText(p)}>{p.length > 48 ? p.slice(0, 48) + '…' : p}</button>
        ))}
      </div>
      <textarea
        aria-label="Describe your business"
        rows={5}
        maxLength={MAX}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setRead(null);
        }}
        style={{ width: '100%', marginTop: 8 }}
      />
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn sm pri" disabled={action.pending || !text.trim()} onClick={readIt}>Read it</button>
        <span className="note">{text.length}/{MAX}</span>
      </div>
      {err && <p className="err" role="alert">{err}</p>}
      {read && (
        <div className="stack" style={{ marginTop: 10 }}>
          <h4>What the agent read{read.reading.by_model ? ' (drafted by a model, checked by the rules)' : ''}</h4>
          <p>{read.reading.word_count} words · {read.reading.controls.length} explicit control{read.reading.controls.length === 1 ? '' : 's'}
            {read.reading.systems.length > 0 && ` · systems: ${read.reading.systems.join(', ')}`}</p>
          <ul>{read.reading.controls.map((c, i) => <li key={i}>{c.kind}: {c.text}</li>)}</ul>
          <p>
            <b>{read.match.nearest_only ? 'Nearest pack' : 'Matched pack'}:</b> {read.match.key} ({Math.round(read.match.score)})
          </p>
          {q && !set && (
            <div>
              <b>{q.text}</b>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                {q.options.map((o) => (
                  <button key={o.id} className="btn sm" disabled={action.pending} onClick={() => draft(o.id)}>{o.label}</button>
                ))}
                <button className="btn sm" disabled={action.pending} onClick={() => draft('skip')}>Skip</button>
              </div>
            </div>
          )}
          {!q && !set && <button className="btn sm pri" disabled={action.pending} onClick={() => draft()}>Draft the change set</button>}
        </div>
      )}
      {set && (
        <div className="stack" style={{ marginTop: 10 }}>
          <h4>Change set for {set.pack} v{set.base_version}</h4>
          <ul>
            {set.ops.map((o) => (
              <li key={o.id}>
                {o.op}: {JSON.stringify(Object.fromEntries(Object.entries(o).filter(([k]) => !['id', 'op', 'by', 'note'].includes(k))))}
                {set.assumed.includes(o.id) && <span className="chip line" style={{ marginLeft: 6 }}>assumed</span>}
              </li>
            ))}
            {set.ops.length === 0 && <li className="note">No changes.</li>}
          </ul>
          {set.blocked.map((b, i) => (
            <p key={i} className="err">Blocked ({b.guardrail}): {b.text}</p>
          ))}
          {sent && (
            <p className="ok">
              {sent.proposal_id != null ? `Sent for approval as proposal ${sent.proposal_id}; it appears under Proposals on Home.` : 'Saved as a draft.'}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
