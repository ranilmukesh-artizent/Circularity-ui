import { useState } from 'react';
import { ruleSuggestions, type RuleSuggestion, type RuleSuggestions } from '../../api/modeler';
import type { ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { formatImpact } from './impact';
import { shareLine } from './learning';

interface Props {
  s: ModelerScreen;
  /** apply the suggestion to the draft (the person's own flow.saveDraft); true when it was saved */
  onApply: (sg: RuleSuggestion) => Promise<boolean>;
}

/**
 * Rule suggestions from Approver overrides (plan 8, MVP-12.3; audit U8): flow.suggestions, read on demand. Each is a
 * checked, simulated proposal; "Apply as draft" saves it into the draft only. Submitting, approving and publishing stay
 * the lifecycle's own steps.
 */
export function SuggestionsPanel({ s, onApply }: Props) {
  const [out, setOut] = useState<RuleSuggestions | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const name = (k: string) => s.template.paths.find((p) => p.id === k)?.name ?? k;
  const find = async () => {
    setBusy(true);
    setMsg('');
    try {
      setOut(await ruleSuggestions(s.flow.id));
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const apply = async (sg: RuleSuggestion) => {
    setBusy(true);
    try {
      if (await onApply(sg)) {
        setOut(null);
        setMsg(`Applied to the draft: ${sg.proposal.label ?? sg.text}. Submit it for approval when you are ready.`);
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Suggestions from overrides" sub="Rules that repeated overrides point to" cls="mdl-impact"
           right={<button className="btn sm" disabled={busy} onClick={find}>{out ? 'Check again' : 'Find suggestions'}</button>}>
      {msg && <p className="note" role="status">{msg}</p>}
      {!out && !msg && <p className="note">Reads the approvals and overrides of the decisions this flow made. Nothing changes until you apply one.</p>}
      {out && (
        <>
          <p className="note">{out.decisions} decisions read · {out.groups.reduce((n, g) => n + g.n, 0)} overrides</p>
          {!out.suggestions.length && <p className="note">No rule suggested: no asset group is overridden to one path often enough.</p>}
          {out.suggestions.map((sg) => {
            const p = sg.proposal;
            return (
              <div key={sg.dim + sg.value + sg.path} className="mdl-prop" style={{ marginBottom: 8 }}>
                <b>{sg.text}</b>
                <span className="note">{shareLine(sg, name)}</span>
                {p.kind === 'blocked' ? (
                  <p className="mdl-msg blk" style={{ margin: 0 }}>{p.msg}</p>
                ) : (
                  <>
                    {p.checks.filter((c) => c.level !== 'ok').map((c, i) => <span key={i} className="note">! {c.msg}</span>)}
                    {p.sim && <span className="note">Impact vs current draft: <b className={p.sim.dv >= 0 ? 'good' : 'bad'}>{formatImpact(p.sim)}</b></span>}
                    {s.can.edit && (
                      <div className="mdl-row">
                        <button className="btn sm pri" disabled={busy || !p.graph} onClick={() => apply(sg)}>Apply as draft</button>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </>
      )}
    </Panel>
  ); // prettier-ignore
}
