import { useState } from 'react';
import { registerAgent, type AgentKind, type AgentsScreen, type Autonomy } from '../../api/agents';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { idFromName, problem, toolOptions } from './register';

const CHECK_ROW = { display: 'flex', alignItems: 'baseline', gap: 6, fontWeight: 400, margin: '4px 0' } as const;
const BOX = { width: 'auto', margin: 0, flex: 'none' } as const;

const AUTONOMY: [Autonomy, string, string][] = [
  ['read', 'Read only', 'It reads and changes nothing.'],
  ['propose', 'Propose for a person', 'Every change it prepares waits for a person to accept it.'],
  ['act', 'Act within its tools', 'It prepares changes as the person who runs it. A person still approves every decision.'],
];

/** Register an agent (plan 8 UI gaps; Admin, agent.register): its name, kind, the tools it may use and how far it may
 * go. The tools offered are the MCP tools and the actions an agent may call; the server refuses any other. */
export function RegisterAgentDialog({ s, onClose }: { s: AgentsScreen; onClose: () => void }) {
  const action = useAction();
  const [name, setName] = useState('');
  const [id, setId] = useState('');
  const [idEdited, setIdEdited] = useState(false);
  const [kind, setKind] = useState<AgentKind>('external');
  const [autonomy, setAutonomy] = useState<Autonomy>('propose');
  const [tools, setTools] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState<Set<string>>(new Set());
  const [err, setErr] = useState('');
  const options = toolOptions(s);
  const agentId = idEdited ? id : idFromName(name);
  const body = { id: agentId, name: name.trim(), kind, tools: [...tools], org_scope: [...scope], autonomy };
  const flip = (set: Set<string>, k: string) => {
    const n = new Set(set);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    return n;
  };
  const save = async () => {
    const p = problem(body, s.agents.map((a) => a.id));
    if (p) return setErr(p);
    const r = await action.run(() => registerAgent(body), { all: setErr });
    if (!r.ok) return;
    toast(`${body.name} is registered.`);
    onClose();
  };
  return (
    <Modal
      title="Register agent"
      wide
      onClose={onClose}
      foot={
        <>
          {err && <span className="note err" role="alert">{err}</span>}
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" id="ag-reg-save" disabled={action.pending || !name.trim()} onClick={save}>Register</button>
        </>
      }
    >
      <div className="grid g2" style={{ gap: '0 14px' }}>
        <div>
          <div className="fld">
            <label htmlFor="ag-reg-name">Name</label>
            <input id="ag-reg-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="e.g. Claims helper" />
          </div>
          <div className="fld">
            <label htmlFor="ag-reg-id">Id</label>
            <input
              id="ag-reg-id"
              className="mono"
              value={agentId}
              maxLength={64}
              onChange={(e) => {
                setIdEdited(true);
                setId(e.target.value);
              }}
            />
            <div className="hint">The agent names this id when it calls Circularity.</div>
          </div>
          <div className="fld">
            <label htmlFor="ag-reg-kind">Kind</label>
            <select className="sel" id="ag-reg-kind" value={kind} onChange={(e) => setKind(e.target.value as AgentKind)}>
              <option value="external">External: runs outside Circularity</option>
              <option value="internal">Internal: runs inside Circularity</option>
            </select>
          </div>
          <fieldset className="fld">
            <legend>Autonomy</legend>
            {AUTONOMY.map(([k, l, d]) => (
              <div key={k} style={{ marginBottom: 6 }}>
                <label style={CHECK_ROW}>
                  <input type="radio" style={BOX} name="ag-reg-autonomy" checked={autonomy === k} onChange={() => setAutonomy(k)} /> {l}
                </label>
                <div className="hint" style={{ marginLeft: 20 }}>{d}</div>
              </div>
            ))}
          </fieldset>
          <fieldset className="fld">
            <legend>Org scope</legend>
            <div className="hint">None ticked: every org.</div>
            {s.orgs.map((o) => (
              <label key={o} style={CHECK_ROW}>
                <input type="checkbox" style={BOX} checked={scope.has(o)} onChange={() => setScope(flip(scope, o))} /> {o}
              </label>
            ))}
          </fieldset>
        </div>
        <fieldset className="fld">
          <legend>Tools it may use ({tools.size})</legend>
          <div className="hint">Actions that only a person may run, such as approving or changing access, are not offered.</div>
          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            {options.map((t) => (
              <label key={t.id} style={{ ...CHECK_ROW, fontSize: 12 }} title={t.kind === 'mcp' ? 'MCP tool' : t.title}>
                <input type="checkbox" style={BOX} checked={tools.has(t.id)} onChange={() => setTools(flip(tools, t.id))} />
                <span className="mono">{t.id}</span>
                {t.kind === 'action' && <span className="note">{t.title}</span>}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </Modal>
  );
}
