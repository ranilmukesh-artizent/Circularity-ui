import { Suspense, useEffect } from 'react';
import { useModeler } from '../../../api/modeler';
import { ErrorBoundary } from '../../../components/Boundary';
import { looksLikeQuestion } from '../../../pages/modeler/proposal';
import { useSurface } from '../../../utils/workSurface';
import { prefill } from '../store';
import type { AssistantContext, AssistantMode, Turn } from '../types';
import { AppliedLine } from '../flow/AppliedLine';
import { loadSuggestions, pendingOfSuggestion, setPending, useChange } from '../flow/changeStore';
import { PendingCard } from '../flow/PendingCard';
import type { ChangeData } from './change';
import '../flow/flow.css';

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;

export function ChangeTurn({ turn, ask }: { turn: Turn; ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }) {
  const st = useChange();
  const sf = useSurface();
  const d = turn.data as ChangeData | null;
  if (turn.error) return <p className="as-err" role="alert">{turn.error} Your text is kept.</p>;
  if (!d) return null;
  const p = d.proposal;
  const basis = p.read_by === 'rules+model' ? 'Read by a language model, checked by the rules' : 'Read by the rules';
  const outcome = st.outcomes[d.key];
  const mine = st.pending?.key === d.key;
  return (
    <div className="as-turn-body">
      <p className="as-basis">{basis}</p>
      {p.kind === 'unclear' && (
        // a question back (2.5): the parser names what it needs; the person rephrases, nothing proceeds on its own
        <div role="group" aria-label="A question from Ask Circularity">
          <p>{p.msg}</p>
          <p className="as-turn-acts">
            <button type="button" className="btn sm" onClick={() => prefill(d.text, 'change')}>Rephrase</button>
            {looksLikeQuestion(d.text) && <button type="button" className="as-link" onClick={() => ask(d.text, 'ask')}>This reads like a question. Ask it instead</button>}
          </p>
        </div>
      )}
      {p.kind === 'blocked' && !mine && <p className="as-blocked">{p.msg}</p>}
      {mine && st.sections > 0 && <p>{p.kind === 'blocked' ? `Blocked by ${p.guard ?? 'a guardrail'}.` : `Proposed: ${p.label ?? p.text}.`} Review it under Proposals.</p>}
      {mine && st.sections === 0 && sf?.kind === 'flow' && (
        <ErrorBoundary resetKey={String(sf.flowId)}>
          <Suspense fallback={null}>
            <TurnCard template={sf.template} org={sf.org} />
          </Suspense>
        </ErrorBoundary>
      )}
      {outcome === 'dismissed' && <p>Dismissed. Nothing was saved.</p>}
      {outcome === 'undone' && <p>Undone. The draft is as it was before.</p>}
      {st.applied?.key === d.key && <AppliedLine />}
    </div>
  );
}

function TurnCard({ template, org }: { template: string; org: string }) {
  return <PendingCard s={useModeler(template, org)} />;
}

export function ChangeEmpty({ ctx }: { ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }) {
  const st = useChange();
  const sf = useSurface();
  const sg = ctx.flow && st.suggestions?.flowId === ctx.flow.id ? st.suggestions : null;
  const list = sg?.data?.suggestions ?? [];
  const flowId = ctx.flow?.id;
  const none = !st.suggestions;
  useEffect(() => {
    if (flowId != null && none) void loadSuggestions(flowId);
  }, [flowId, none]);
  return (
    <div className="as-empty-state">
      <p>Describe a change to {ctx.flow?.name ?? 'this flow'}. It is checked and simulated before anything is saved.</p>
      {list.length > 0 && (
        <>
          <p className="as-sub">{plural(list.length, 'change')} suggested by approver overrides</p>
          {list.map((g) => (
            <button key={g.dim + g.value + g.path} type="button" className="as-starter"
                    onClick={() => sf?.kind === 'flow' && setPending(pendingOfSuggestion(g, sf))}>{g.text}</button>
          ))}
        </>
      )}
    </div>
  );
}
