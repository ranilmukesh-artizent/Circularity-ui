import type { DisagreementView, LifeView } from '../../../api/toolFleet';

/** "WTI 65": the wear index of the tool, 0 (new) to 100 (worn out). */
export const wtiLine = (l: LifeView): string => `WTI ${l.wti}`;

/** "RUL 21% (Motor armature), 223.5 h": the remaining life of the weakest critical component, in percent and hours. */
export const rulLine = (l: LifeView): string => `RUL ${l.rul_tool}% (${l.weakest}), ${l.rul_tool_hours} h`;

/** "Low: 0% to 53% without telematics" for a Low confidence with a range, else "High", "Medium" or "Low". */
export const confidenceLine = (l: LifeView): string =>
  l.range ? `${l.confidence}: ${l.range[0]}% to ${l.range[1]}% without telematics` : l.confidence;

const CHIP: Record<LifeView['confidence'], string> = { High: 'ok', Medium: 'warn', Low: 'bad' };

/** The wear and remaining life of a tool (plan 9, P9-3.9, TF-06): the wear index, the remaining life, a row per component and
 * the confidence. The numbers are computed on the server (rated life from PLM, else the pack's table); nothing is worded by a model. */
export function LifeSection({ life, disagreement = null }: { life: LifeView | null; disagreement?: DisagreementView | null }) {
  if (!life) return null;
  return (
    <section aria-label="Wear and remaining life" data-testid="tf-life" style={{ marginTop: 8 }}>
      {disagreement && (
        <p className="chip warn" role="alert" data-testid="tf-disagreement" style={{ margin: '0 0 4px' }}>
          {disagreement.text}. A person from Quality decides.
        </p>
      )}
      <p style={{ margin: 0 }}>
        <b data-testid="tf-life-wti">{wtiLine(life)}</b> · <b data-testid="tf-life-rul">{rulLine(life)}</b>{' '}
        <span className={`chip ${CHIP[life.confidence]}`} data-testid="tf-life-confidence">{confidenceLine(life)}</span>
      </p>
      <table className="tbl" style={{ marginTop: 4 }}>
        <thead>
          <tr><th>Component</th><th>Used (h)</th><th>Consumed</th><th>Remaining</th><th>Rating</th></tr>
        </thead>
        <tbody>
          {life.per_component.map((c) => (
            <tr key={c.name} data-testid={`tf-life-${c.name}`}>
              <td>{c.name}</td>
              <td>{c.used_hours}</td>
              <td>{c.consumed_pct}%</td>
              <td>{c.rul_pct}%</td>
              <td>{c.source === 'plm' ? 'PLM' : `Pack table ${life.table_version}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note" style={{ margin: '4px 0 0' }}>Rules {life.rule_version}. Computed from the telematics, the contract and the repair log; not written by a model.</p>
    </section>
  );
}
