import { updateAgent, type AgentsScreen } from '../../api/agents';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { NEVER_ALONE, STAGE_AUTONOMY, STAGE_AUTONOMY_NOTE, agentGroups, type AgentLine } from './agentsView';

const LEVEL_CHIP = { recommend: 'line', limits: 'y', alone: 'ok' } as const;
const when = (iso: string) => iso.slice(0, 16).replace('T', ' ');

function Row({ l, manage, busy, toggle }: { l: AgentLine; manage: boolean; busy: boolean; toggle: (l: AgentLine) => void }) {
  const a = l.agent;
  return (
    <tr data-agent={a.id}>
      <td><b>{a.name}</b><span className="note" style={{ display: 'block' }}>{l.summary}</span></td>
      <td>{l.stageLabel ?? <span className="note">Any case</span>}</td>
      <td>
        {l.autonomy ? <span className={'chip ' + LEVEL_CHIP[l.autonomy]} title={STAGE_AUTONOMY_NOTE[l.autonomy]}>{STAGE_AUTONOMY[l.autonomy]}</span> : <span className="note">Proposes; a person accepts</span>}
      </td>
      <td className="nowrap">
        <span className={'chip ' + (a.enabled ? 'ok' : 'warn')}>{a.enabled ? 'On' : 'Paused'}</span>{' '}
        {manage && <button className="btn sm" disabled={busy} onClick={() => toggle(l)}>{a.enabled ? 'Pause' : 'Resume'}</button>}
      </td>
      <td className="nowrap">
        {l.last ? <>{when(l.last.updated_at)} <span className="note">{l.last.case_id ?? ''}</span></> : <span className="note">No run yet</span>}
      </td>
    </tr>
  );
}

/**
 * The business view of the Agents page (UI audit gaps 14 and 21): the agents under their pack, what each does, the stage it
 * runs, how alone it may act, whether it is on and when it last ran. No model id or tool id. A stage's autonomy is the pack's
 * (set in Compose, with a checker); pausing an agent is the admin's switch.
 */
export function AgentsBusiness({ s }: { s: AgentsScreen }) {
  const action = useAction();
  const groups = agentGroups(s);
  const toggle = async (l: AgentLine) => {
    const r = await action.run(() => updateAgent(l.agent.id, { enabled: !l.agent.enabled }));
    if (r.ok) toast(l.agent.name + (l.agent.enabled ? ' is paused.' : ' runs again.'));
  };
  return (
    <section className="sect" id="agBusiness">
      <div className="sh">
        <h2>Agents</h2>
        <span className="note">{s.agents.length} agents · {s.agents.filter((a) => !a.enabled).length} paused</span>
      </div>
      <div className="callout info" style={{ marginBottom: 12 }}>
        <b>How far an agent may go.</b> Recommend only: it prepares, a person decides. Act within limits: it acts while value, confidence and volume stay
        inside the limits. Act alone: it acts without waiting. {NEVER_ALONE}{' '}
        Each pack sets the level of its stages in <a href="#/modeler">Compose, in the Modeler</a> (a second person approves the change).
      </div>
      {groups.map((g) => (
        <div key={g.key} style={{ marginBottom: 14 }} data-pack={g.key}>
          <h3 style={{ margin: '0 0 6px' }}>{g.title} <span className="note">{g.note}</span></h3>
          <div className="panel">
            <div className="tw">
              <table className="t static" aria-label={g.title + ' agents'}>
                <thead><tr><th>Agent</th><th>Stage</th><th>Autonomy</th><th>Status</th><th>Last run</th></tr></thead>
                <tbody>{g.rows.map((l) => <Row key={l.agent.id} l={l} manage={s.can.manage} busy={action.pending} toggle={toggle} />)}</tbody>
              </table>
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
