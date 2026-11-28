import type { Composition } from '../../api/compose';
import { useModeler } from '../../api/modeler';
import { openAssistant } from '../../utils/askBus';
import { ModelerBody } from '../modeler/ModelerPage';
import { orgName } from './setupView';

/**
 * The flow stop of Set up: the Modeler's own flow editor for the setup's template and organisation, in the page. The canvas,
 * the inspector, the checks and the assistant column (Change flow) are the Modeler's components on the Modeler's draft, so
 * whatever is changed here is exactly what the Modeler shows, and the other way round. The rules the description led to are
 * listed above it: "Put it on the flow" hands one to the assistant, which shows the change on the canvas before anything is
 * saved. An agent's change is a proposal; the person applies it, and a different person approves the flow.
 */
export function ShapeStep({ c }: { c: Composition }) {
  const s = useModeler(c.pack_key, c.org_unit_id);
  const rules = c.change_set.rules ?? [];
  const inherited = s.flow.org_unit_id !== c.org_unit_id;
  return (
    <div className="sup-shape">
      {rules.length > 0 && (
        <div className="sup-rules">
          <p className="note">Your description led to {rules.length === 1 ? 'this rule' : `these ${rules.length} rules`}. Put one on the flow and the assistant shows the change before anything is saved.</p>
          <ul>
            {rules.map((r) => (
              <li key={r.id}>
                <span>{r.text}{r.assumed && <span className="note"> (assumed from the template’s default)</span>}</span>
                <button type="button" className="btn sm" disabled={!s.can.edit} onClick={() => openAssistant({ mode: 'change', question: r.text })}>Put it on the flow</button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {inherited && (
        <p className="note sup-inherit">
          {orgName(c.org_unit_id)} uses the flow of {orgName(s.flow.org_unit_id)}. A change here changes it for everyone who uses that flow{s.can.fork ? '; “Give it its own flow” in the bar below makes a copy first.' : '.'}
        </p>
      )}
      <div className="mdl sup-flow">
        <ModelerBody key={s.flow.id} s={s} tab="flow" compose={null} />
      </div>
    </div>
  );
}
