import { updateAgent, type AgentsScreen } from '../../api/agents';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { orgName, setupPath } from '../setup/setupView';
import { NEVER_ALONE, STAGE_AUTONOMY, STAGE_AUTONOMY_NOTE, agentGroups, type AgentLine, type SetupLine, type StageLevel } from './agentsView';

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

/** What the setups of a pack changed: one line a setup, with the stages it runs at another level and the way to its agents step. */
function Setups({ list }: { list: SetupLine[] }) {
  return (
    <div className="ag-setups">
      <h4>Changed in Set up</h4>
      <ul>
        {list.map((u) => (
          <li key={u.id} data-setup={u.id}>
            <span className="ag-setup-who">
              <b>{orgName(u.org)}</b>
              <span className="note">{u.live ? 'Live' : 'Approved, not live yet'}</span>
            </span>
            <span className="ag-setup-what">
              {u.changes.length === 0
                ? <span className="note">Runs every stage as the pack sets it.</span>
                : u.changes.map((c) => (
                    <span key={c.stage} className="ag-change">
                      {c.stage}: <s>{STAGE_AUTONOMY[c.from]}</s> <b>{STAGE_AUTONOMY[c.to]}</b>
                    </span>
                  ))}
            </span>
            <a className="lnk" href={'#' + setupPath({ compose: u.id, step: 'agents' })}>Open in Set up</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The business view of the Agents page (UI audit gaps 14 and 21): the agents under their pack, what each does, the stage it
 * runs, how alone it may act, whether it is on and when it last ran. No model id or tool id. A stage's autonomy is the pack's
 * (set in Set up's agents step, with a checker; what each setup changed is listed under its pack); pausing an agent is the admin's switch.
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
      <div className="ag-levels panel">
        <div className="pb">
          <h3>How far an agent may go</h3>
          <dl>
            {(Object.keys(STAGE_AUTONOMY) as StageLevel[]).map((k) => (
              <div key={k}>
                <dt><span className={'chip ' + LEVEL_CHIP[k]}>{STAGE_AUTONOMY[k]}</span></dt>
                <dd>{STAGE_AUTONOMY_NOTE[k]}</dd>
              </div>
            ))}
          </dl>
          <p className="ag-never"><b>Always a person:</b> {NEVER_ALONE}</p>
          <p className="note">A setup changes the level of a stage in <a href="#/setup">Set up, under Set agents</a>; a second person approves the change before it runs.</p>
        </div>
      </div>
      {groups.map((g, k) => (
        <details key={g.key} className="ag-pack" data-pack={g.key} open={k === 0 && !g.notSetUp}>
          <summary>
            <span className="ag-pack-title">{g.title}</span>
            <span className="note">{g.notSetUp ? 'Not set up' : `${g.rows.length} ${g.rows.length === 1 ? 'agent' : 'agents'}${g.key === 'platform' || g.key === 'outside' ? ' · ' + g.note : ''}`}</span>
          </summary>
          {g.notSetUp ? (
            <div className="panel"><div className="pb"><div className="empty"><b>Not set up</b>No stage agents for this pack yet. <a href={'#' + setupPath({ pack: g.key, fresh: true })}>Start a setup from this pack</a>.</div></div></div>
          ) : (
            <div className="panel">
              <div className="tw">
                <table className="t static" aria-label={g.title + ' agents'}>
                  <thead><tr><th>Agent</th><th>Stage</th><th>Autonomy</th><th>Status</th><th>Last run</th></tr></thead>
                  <tbody>{g.rows.map((l) => <Row key={l.agent.id} l={l} manage={s.can.manage} busy={action.pending} toggle={toggle} />)}</tbody>
                </table>
              </div>
              {g.setups && g.setups.length > 0 && <Setups list={g.setups} />}
            </div>
          )}
        </details>
      ))}
    </section>
  );
}
