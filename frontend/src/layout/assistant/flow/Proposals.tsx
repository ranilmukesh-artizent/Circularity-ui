import type { HomeProposal } from '../../../api/home';
import type { ModelerScreen } from '../../../api/types';
import { AppliedLine } from './AppliedLine';
import { flowSurface, pendingOfSuggestion, setPending, useChange } from './changeStore';
import { PendingCard } from './PendingCard';
import { Row, Sec } from './Sec';

/**
 * "Proposals" (plan 10, 3.3): the pending flow proposal as the preview card, at most one expanded; the other suggestions
 * from overrides and the proposals held for a person are one line each. Accepting a held proposal is done under
 * "Waiting for you", where it goes through the same card as every other write.
 */
export function Proposals({ s, held }: { s: ModelerScreen; held: HomeProposal[] }) {
  const st = useChange();
  const pd = st.pending;
  const others = (st.suggestions?.flowId === s.flow.id ? st.suggestions.data?.suggestions : [])?.filter((g) => !pd || g.text !== pd.text) ?? [];
  const open = (i: number) => {
    const sf = flowSurface();
    if (sf) setPending(pendingOfSuggestion(others[i], sf));
  };
  const n = (pd ? 1 : 0) + others.length + held.length;
  return (
    <Sec icon="edit" title={n ? `Proposals (${n})` : 'Proposals'}>
      {pd && <PendingCard s={s} />}
      {st.applied && st.applied.key == null && <AppliedLine />}
      {others.map((g, i) => (
        <Row key={g.dim + g.value + g.path} icon="users" tag="Retrieved" go="Review" onGo={() => open(i)}>{g.text}</Row>
      ))}
      {held.map((p) => (
        <Row key={p.id} icon="bot" tag="Prepared by agent">{p.agentName}: {p.title}. Accept or reject it under Waiting for you.</Row>
      ))}
      {!n && !st.applied && <p className="as-empty">No proposals. Describe a change below and it is checked and simulated before anything is saved.</p>}
    </Sec>
  );
}
