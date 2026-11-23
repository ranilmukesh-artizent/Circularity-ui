import { useState } from 'react';
import { proposeChange, type Proposal } from '../../api/modeler';
import type { ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { formatImpact, tradeOff } from './impact';
import { openingLine, proposalChecks } from './proposal';

interface Msg {
  who: 'ai' | 'user';
  text: string;
  blk?: boolean;
}

interface Props {
  s: ModelerScreen;
  proposal: Proposal | null;
  onProposal: (p: Proposal | null) => void;
  /** apply the proposal: the person's own saveDraft with the assistant's note */
  onApply: (p: Proposal) => Promise<boolean>;
}

/**
 * The Modeler's assistant (plan 8, MVP-5.4; the prototype's chat and aiAssist): a plain-language change becomes a
 * checked, simulated proposal (flow.propose). Nothing changes until the person applies it; it is drawn dashed on the
 * canvas meanwhile. A change to a guardrail is refused, in red.
 */
export function AssistantPanel({ s, proposal, onProposal, onApply }: Props) {
  const [chat, setChat] = useState<Msg[]>([{ who: 'ai', text: openingLine(s.template.key) }]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const say = (m: Msg) => setChat((c) => [...c, m]);

  const send = async () => {
    const t = text.trim();
    if (!t || busy) return;
    setText('');
    if (proposal) say({ who: 'ai', text: 'Earlier proposal set aside so I can check this one.' });
    onProposal(null);
    say({ who: 'user', text: t });
    setBusy(true);
    try {
      const p = await proposeChange(s.flow.id, t);
      if (p.kind === 'rule' || p.kind === 'step') {
        onProposal(p);
        say({ who: 'ai', text: 'Here is what I would change. It is shown dashed on the canvas; nothing changes until you approve.' });
      } else if (p.kind === 'blocked' && p.graph) {
        onProposal(p);
        say({ who: 'ai', text: p.msg, blk: true });
      } else {
        say({ who: 'ai', text: p.msg, blk: p.kind === 'blocked' });
      }
    } catch (e) {
      say({ who: 'ai', text: (e as Error).message, blk: true });
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (proposal && (await onApply(proposal))) {
      say({ who: 'ai', text: 'Applied to the draft: ' + (proposal.label ?? '') + '. Submit it for approval when you are ready.' });
      onProposal(null);
    }
  };

  const p = proposal && proposal.kind !== 'blocked' ? proposal : null;
  const note = p?.sim ? tradeOff(p.sim) : null;
  return (
    <Panel title="Assistant" sub={s.can.edit ? 'Describe a change in plain words' : 'Read only'} cls="mdl-assist">
      <div className="mdl-chat" aria-live="polite">
        {chat.map((m, i) => <div key={i} className={'mdl-msg ' + m.who + (m.blk ? ' blk' : '')}>{m.text}</div>)}
        {busy && <div className="mdl-msg ai note">Checking…</div>}
      </div>
      {p && (
        <div className="mdl-prop">
          <span className="label">Proposed change</span>
          <b>{p.label}</b>
          <ul className="mdl-checks">
            {(p.kind === 'rule' ? proposalChecks(p, s.template.guardrails.length) : []).map((c, i) => (
              <li key={i} className={c.level}><span className="ic">{c.level === 'ok' ? '✓' : '!'}</span><span>{c.text}</span></li>
            ))}
          </ul>
          {p.sim && <p className="note">Impact vs current draft: <b className={p.sim.dv >= 0 ? 'good' : 'bad'}>{formatImpact(p.sim)}</b></p>}
          {note && <p className="note">{note}</p>}
          <div className="mdl-row">
            {s.can.edit && <button className="btn sm pri" onClick={apply}>Approve · AI applies it</button>}
            <button className="btn sm" onClick={() => onProposal(null)}>Dismiss</button>
          </div>
        </div>
      )}
      {proposal?.kind === 'blocked' && <button className="btn sm" onClick={() => onProposal(null)}>Dismiss</button>}
      {s.can.edit && (
        <div className="mdl-row">
          <label className="sr" htmlFor="mdl-ask">Describe a change</label>
          <input id="mdl-ask" value={text} placeholder="e.g. Never send grade D motors to resale" style={{ flex: 1 }}
                 onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void send()} />
          <button className="btn sm" disabled={busy || !text.trim()} onClick={send}>Send</button>
        </div>
      )}
    </Panel>
  ); // prettier-ignore
}
