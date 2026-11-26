import type { HomeProposal } from '../../../api/home';
import type { ModelerScreen } from '../../../api/types';
import { watchingRows } from '../../../pages/modeler/flowBrief';
import { flowSurface, loadSuggestions, pendingOfSuggestion, setPending, useChange } from './changeStore';
import { Row, Sec } from './Sec';

/**
 * "Watching" (plan 10, 3.3): one row per signal that exists (shadow run, a draft waiting for approval, suggestions from
 * overrides, proposals held for a person). Suggestions are read once when the column opens and on Refresh.
 */
export function Watching({ s, held }: { s: ModelerScreen; held: HomeProposal[] }) {
  const st = useChange();
  const sg = st.suggestions?.flowId === s.flow.id ? st.suggestions : null;
  const rows = watchingRows(s, { suggestions: sg?.data ?? null, held });
  const canRead = s.can.edit || s.can.approve;
  const open = () => {
    const sf = flowSurface();
    const first = sg?.data?.suggestions[0];
    if (sf && first) setPending(pendingOfSuggestion(first, sf));
  };
  return (
    <Sec icon="eye" title="Watching"
         right={canRead && <button type="button" className="as-link" disabled={sg?.busy} aria-label="Find suggestions from overrides again" onClick={() => void loadSuggestions(s.flow.id)}>{sg?.busy ? 'Reading overrides' : 'Refresh'}</button>}>
      {rows.map((r) => (
        <Row key={r.id} icon={r.icon} tag={r.tag} go={r.action === 'suggestions' ? 'Review' : undefined} onGo={open}>{r.text}</Row>
      ))}
      {!rows.length && <p className="as-empty">{sg?.error || 'Nothing to watch yet: no shadow run, no overrides, nothing held.'}</p>}
    </Sec>
  );
}
