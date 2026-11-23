import { fmtDateYear } from '../../api/format';
import { rollbackFlow } from '../../api/modeler';
import type { ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const VERB: Record<string, string> = {
  'flow.saveDraft': 'Saved draft', 'flow.fork': 'Gave the org its own flow', 'flow.submit': 'Submitted', 'flow.approve': 'Approved',
  'flow.reject': 'Returned to draft', 'flow.publish': 'Published', 'flow.discard': 'Discarded draft', 'flow.rollback': 'Rolled back',
}; // prettier-ignore

/** The versions earlier publishes replaced (with Rollback for an approver), and the flow's log. */
export function HistoryPanel({ s }: { s: ModelerScreen }) {
  const action = useAction();
  const rollback = async () => {
    const r = await action.run(() => rollbackFlow(s.flow.id), 4200);
    if (r.ok && r.output.log) toast(r.output.log + '.');
  };
  return (
    <Panel title="History" sub={'Published v' + s.flow.ver}
           right={s.can.approve && s.versions.length > 0 ? <button className="btn sm" disabled={action.pending} onClick={rollback}>Roll back to v{s.versions[0].ver}</button> : undefined}>
      {s.versions.length === 0 && <p className="note">No earlier versions.</p>}
      {s.versions.length > 0 && (
        <ul className="mdl-hist">
          {s.versions.map((v) => (
            <li key={v.ver}>v{v.ver} · {v.note ?? ''}{v.published_at ? ' · ' + fmtDateYear(v.published_at) : ''}</li>
          ))}
        </ul>
      )}
      <h4>Log</h4>
      {s.log.length === 0 && <p className="note">No changes yet.</p>}
      <ul className="mdl-hist">
        {s.log.slice(0, 30).map((l, i) => (
          <li key={i}>
            <span className="note">{fmtDateYear(l.at)}</span> {VERB[l.action] ?? l.action} · {l.actor}
            {l.note && <span className="note"> · {l.note}</span>}
          </li>
        ))}
      </ul>
    </Panel>
  ); // prettier-ignore
}
