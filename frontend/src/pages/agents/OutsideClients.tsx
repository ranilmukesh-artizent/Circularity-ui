/**
 * "Outside clients" on the Agents page (plan 9, P9-13.10): the pre-registered OAuth clients that may ask a person to let
 * them use Circularity's MCP tools as an agent. Admin registers (name, redirect URIs, the agent it acts as, the scopes it
 * may ask for) and revokes. A client holds no secret; every use starts with a person's consent. The client's tokens
 * prepare, never approve: writes are held for a person.
 */
import { useEffect, useState } from 'react';
import { OAUTH_SCOPES, outsideClients, registerClient, revokeClient, SCOPE_TEXT, type AgentRow, type OutsideClient } from '../../api/agents';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

export function OutsideClients({ agents }: { agents: AgentRow[] }) {
  const action = useAction();
  const [rows, setRows] = useState<OutsideClient[]>([]);
  const [name, setName] = useState('');
  const [uris, setUris] = useState('');
  const [agent, setAgent] = useState(agents[0]?.id ?? '');
  const [scopes, setScopes] = useState<string[]>(['cases:read']);
  const load = async () => {
    const r = await outsideClients();
    setRows(r.ok ? r.output.clients : []);
  };
  useEffect(() => {
    void load();
  }, []);
  const register = async () => {
    const redirect_uris = uris.split(/\s+/).filter(Boolean);
    const r = await action.run(() => registerClient({ name: name.trim(), redirect_uris, agent_id: agent, scopes }));
    if (r.ok) {
      toast('Client registered: ' + r.output.client_id);
      setName('');
      setUris('');
      await load();
    }
  };
  const revoke = async (id: string) => {
    const r = await action.run(() => revokeClient(id));
    if (r.ok) {
      toast('Client revoked.');
      await load();
    }
  };
  const flip = (s: string) => setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  return (
    <section className="sect" id="agClients">
      <div className="sh">
        <h2>Outside clients</h2>
        <span className="note">An outside MCP client asks a person for consent, then acts as an agent with the scopes below. Its writes are held for a person.</span>
      </div>
      <div className="panel" style={{ padding: 12, marginBottom: 12 }}>
        <label htmlFor="oc-name">Client name</label>
        <input id="oc-name" value={name} onChange={(e) => setName(e.target.value)} />{' '}
        <label htmlFor="oc-uris">Redirect URIs (one per line, exact)</label>
        <textarea id="oc-uris" value={uris} onChange={(e) => setUris(e.target.value)} rows={2} style={{ width: '100%' }} />
        <label htmlFor="oc-agent">Acts as</label>
        <select className="sel" id="oc-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div>
          {OAUTH_SCOPES.map((s) => (
            <label key={s} style={{ marginRight: 12 }}>
              <input type="checkbox" checked={scopes.includes(s)} onChange={() => flip(s)} /> {SCOPE_TEXT[s]}
            </label>
          ))}
        </div>
        <button className="btn sm pri" id="oc-register" disabled={action.pending || !name.trim() || !uris.trim() || !agent || scopes.length === 0} onClick={register}>
          Register client
        </button>
      </div>
      <div className="panel">
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Client</th><th>Agent</th><th>Scopes</th><th>Redirect URIs</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} className="note">No outside clients.</td></tr>}
              {rows.map((c) => (
                <tr key={c.client_id}>
                  <td>{c.name}<div className="mono note">{c.client_id}</div></td>
                  <td>{c.agent_name ?? c.agent_id}</td>
                  <td>{c.scopes.join(', ')}</td>
                  <td className="mono">{c.redirect_uris.join(', ')}</td>
                  <td><span className={'chip ' + (c.revoked_at ? 'bad' : 'ok')}>{c.revoked_at ? 'Revoked' : 'Active'}</span></td>
                  <td>{!c.revoked_at && <button className="btn sm" disabled={action.pending} onClick={() => revoke(c.client_id)}>Revoke</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
