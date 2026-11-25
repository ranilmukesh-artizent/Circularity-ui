import type { GateView } from '../../../api/toolFleet';

/** GR-13, the stale telematics gate: it holds re-issue and pool, never the whole case. */
const TELEMATICS_GATE = 'G-TOOL-TEL';

/** "GR-07 Contract right: passed", "GR-07 Contract right: Theft recovered: claim CLM-7781 is open", or for the telematics gate its freshness line (P9-3.8, TF-05): "Telematics 3 days old" or "Telematics last seen 8 days ago: re-issue and pool need a person". */
export const gateLine = (g: GateView): string =>
  g.id === TELEMATICS_GATE
    ? g.passed ? g.reason : `${g.reason}: re-issue and pool need a person`
    : `${g.guardrail ? g.guardrail + ' ' : ''}${g.name}: ${g.passed ? 'passed' : g.reason}`;

/** The gates that apply to the case, each with a pass or the term it is blocked on (plan 9, P9-3.6, TF-02). */
export function GatesSection({ gates }: { gates: GateView[] }) {
  if (!gates.length) return null;
  return (
    <ul style={{ margin: '8px 0 0', paddingLeft: 18 }} data-testid="tf-gates">
      {gates.map((g) => (
        <li key={g.id} data-testid={`tf-gate-${g.id}`}>
          <span className={`chip ${g.passed ? 'ok' : 'bad'}`}>{g.passed ? 'Passed' : g.id === TELEMATICS_GATE ? 'Needs a person' : 'Blocked'}</span> {gateLine(g)}
        </li>
      ))}
    </ul>
  );
}
