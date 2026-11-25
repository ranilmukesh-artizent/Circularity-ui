import type { GateView } from '../../../api/toolFleet';

/** "GR-07 Contract right: passed" or "GR-07 Contract right: Theft recovered: claim CLM-7781 is open". */
export const gateLine = (g: GateView): string => `${g.guardrail ? g.guardrail + ' ' : ''}${g.name}: ${g.passed ? 'passed' : g.reason}`;

/** The gates that apply to the case, each with a pass or the term it is blocked on (plan 9, P9-3.6, TF-02). */
export function GatesSection({ gates }: { gates: GateView[] }) {
  if (!gates.length) return null;
  return (
    <ul style={{ margin: '8px 0 0', paddingLeft: 18 }} data-testid="tf-gates">
      {gates.map((g) => (
        <li key={g.id} data-testid={`tf-gate-${g.id}`}>
          <span className={`chip ${g.passed ? 'ok' : 'bad'}`}>{g.passed ? 'Passed' : 'Blocked'}</span> {gateLine(g)}
        </li>
      ))}
    </ul>
  );
}
