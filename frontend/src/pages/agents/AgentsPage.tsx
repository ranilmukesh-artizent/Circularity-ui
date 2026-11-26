import { Fragment, useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import {
  agentCredentials, findTools, issueCredential, revokeCredential, stageLabel, startRun, updateAgent, useAgents,
  type AgentCredential, type AgentPatch, type AgentProposal, type AgentRow, type AgentRun, type AgentsScreen, type Autonomy, type Playbook,
} from '../../api/agents'; // prettier-ignore
import { useBackend } from '../../api/useBackend';
import { Drawer, Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import './agents.css';
import { AgentsBusiness } from './AgentsBusiness';
import { ProposalItems } from '../../components/ProposalRow';
import { LlmModelsPanel } from './LlmModelsPanel';
import { OutsideClients } from './OutsideClients';
import { ModelsPanel } from './ModelsPanel';
import { RegisterAgentDialog } from './RegisterAgentDialog';
import { RunView } from './RunView';

const AUTONOMY: [Autonomy, string][] = [['read', 'Read only'], ['propose', 'Propose for a person'], ['act', 'Act within its tools']];
const RUN_CHIP: Record<AgentRun['status'], string> = { running: 'line', waiting: 'y', done: 'ok', failed: 'bad', stopped: 'warn' };
const caseHref = (id: string) => '#/product/' + id;

/** Agents (plan 8, MVP-11.8): the registry, the runs, the proposals that wait for a person and the tool catalogue. */
export function AgentsPage() {
  useBackend();
  const s = useAgents();
  useEffect(() => {
    document.title = 'Agents · Circularity Decision Workbench';
  }, []);
  return (
    <div className="frpage" id="agents">
      <div className="phead">
        <div>
          <h1>Agents</h1>
          <p>
            What each agent does for you, how far it may go and when it last ran. Agents prepare and propose; a person accepts, approves and changes
            access.
          </p>
        </div>
      </div>
      {!s.can.manage && (
        <div className="callout info" style={{ marginBottom: 16 }}>
          <b>Read-only view.</b> Admin manages agents. You accept or reject the proposals your permissions cover.
        </div>
      )}
      <AgentsBusiness s={s} />
      <Proposals list={s.proposals} />
      <Runs s={s} />
      <div className="ag-expert">
        <div className="ag-expert-head" id="agExpert">
          <h2>Models and tools</h2>
          <p className="note">For admins and developers: the registry, credentials, language models and the tool catalogue.</p>
        </div>
        <Registry s={s} />
        {s.can.manage && <Credentials agents={s.agents} />}
        {s.can.manage && <OutsideClients agents={s.agents} />}
        <LlmModelsPanel s={s} />
        <ModelsPanel />
        <Catalogue s={s} />
      </div>
    </div>
  );
}

function Registry({ s }: { s: AgentsScreen }) {
  const action = useAction();
  const [editing, setEditing] = useState<AgentRow | null>(null);
  const [registering, setRegistering] = useState(false);
  const change = async (a: AgentRow, patch: AgentPatch, done: string) => {
    const r = await action.run(() => updateAgent(a.id, patch));
    if (r.ok) toast(done);
    return r.ok;
  };
  return (
    <section className="sect" id="agReg">
      <div className="sh">
        <h2>Agent registry</h2>
        <span className="note">{s.agents.length} agents · {s.agents.filter((a) => !a.enabled).length} stopped</span>
        <span className="grow" />
        {s.can.manage && <button className="btn sm pri" id="ag-register" onClick={() => setRegistering(true)}>Register agent</button>}
      </div>
      <div className="panel">
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Agent</th><th>Kind</th><th>Status</th><th title="The most an agent may do over MCP, whatever its stages allow">Highest level</th><th>Tools</th><th>Org scope</th><th></th></tr></thead>
            <tbody>
              {s.agents.map((a) => (
                <tr key={a.id} data-agent={a.id}>
                  <td><b>{a.name}</b><span className="note mono ag-id">{a.id}</span></td>
                  <td><span className="chip line">{a.kind}</span></td>
                  <td className="nowrap">
                    <span className={'chip ' + (a.enabled ? 'ok' : 'bad')}>{a.enabled ? 'On' : 'Stopped'}</span>{' '}
                    {s.can.manage && (
                      <button className="btn sm" disabled={action.pending} onClick={() => change(a, { enabled: !a.enabled }, a.name + (a.enabled ? ' is stopped.' : ' runs again.'))}>
                        {a.enabled ? 'Stop' : 'Start'}
                      </button>
                    )}
                  </td>
                  <td>
                    {s.can.manage ? (
                      <>
                        <label className="sr" htmlFor={'ag-au-' + a.id}>Autonomy of {a.name}</label>
                        <select className="sel" id={'ag-au-' + a.id} value={a.autonomy} disabled={action.pending} onChange={(e) => change(a, { autonomy: e.target.value as Autonomy }, a.name + ' autonomy changed.')}>
                          {AUTONOMY.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                        </select>
                      </>
                    ) : (
                      <span className="chip line">{AUTONOMY.find(([k]) => k === a.autonomy)?.[1] ?? a.autonomy}</span>
                    )}
                  </td>
                  <td className="note" title={a.tools.join(', ')}>{a.tools.length ? `${a.tools.length} · ${a.tools.slice(0, 3).join(', ')}${a.tools.length > 3 ? ' …' : ''}` : 'None'}</td>
                  <td>{a.org_scope.length ? a.org_scope.map((o) => <span key={o} className="chip line" style={{ marginRight: 4 }}>{o}</span>) : <span className="note">Every org</span>}</td>
                  <td className="nowrap">{s.can.manage && <button className="btn sm" onClick={() => setEditing(a)}>Edit</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {registering && <RegisterAgentDialog s={s} onClose={() => setRegistering(false)} />}
      {editing && (
        <EditModal
          s={s}
          agent={editing}
          busy={action.pending}
          onClose={() => setEditing(null)}
          onSave={async (patch) => {
            if (await change(editing, patch, editing.name + ' updated.')) setEditing(null);
          }}
        />
      )}
    </section>
  );
}

/** P9-13.9: client credentials per agent. The secret is shown once, right after it is issued. */
function Credentials({ agents }: { agents: AgentRow[] }) {
  const action = useAction();
  const [agent, setAgent] = useState(agents[0]?.id ?? '');
  const [rows, setRows] = useState<AgentCredential[]>([]);
  const [secret, setSecret] = useState<{ client_id: string; client_secret: string } | null>(null);
  const load = async (id: string) => {
    const r = await agentCredentials(id);
    setRows(r.ok ? r.output.credentials : []);
  };
  useEffect(() => {
    if (agent) void load(agent);
    setSecret(null);
  }, [agent]);
  const issue = async () => {
    const r = await action.run(() => issueCredential(agent));
    if (r.ok) {
      setSecret(r.output);
      await load(agent);
    }
  };
  const revoke = async (id: string) => {
    const r = await action.run(() => revokeCredential(id));
    if (r.ok) {
      toast('Credential revoked.');
      await load(agent);
    }
  };
  return (
    <section className="sect" id="agCred">
      <div className="sh">
        <h2>Credentials</h2>
        <span className="note">A credential lets an agent get its own token. It acts as you, limited to its tools.</span>
        <span className="grow" />
        <label className="sr" htmlFor="ag-cred-agent">Agent</label>
        <select className="sel" id="ag-cred-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <button className="btn sm pri" id="ag-cred-issue" disabled={action.pending || !agent} onClick={issue}>Issue credential</button>
      </div>
      {secret && (
        <div className="callout info" style={{ marginBottom: 12 }}>
          <b>Client id</b> <span className="mono">{secret.client_id}</span>
          <div>
            <label className="sr" htmlFor="ag-cred-secret">Client secret</label>
            <input id="ag-cred-secret" className="mono" readOnly value={secret.client_secret} style={{ width: '100%' }} onFocus={(e) => e.currentTarget.select()} />
          </div>
          <span className="note">This secret is shown once. Store it in your agent's secret store.</span>
        </div>
      )}
      <div className="panel">
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Client id</th><th>Created</th><th>Last used</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={5} className="note">No credentials for this agent yet. Issue one to let it get its own token.</td></tr>}
              {rows.map((c) => (
                <tr key={c.client_id}>
                  <td className="mono">{c.client_id}</td>
                  <td>{c.created_at?.slice(0, 16).replace('T', ' ') ?? '—'}</td>
                  <td>{c.last_used_at?.slice(0, 16).replace('T', ' ') ?? 'Never'}</td>
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

function EditModal({ s, agent, busy, onClose, onSave }: {
  s: AgentsScreen; agent: AgentRow; busy: boolean; onClose: () => void; onSave: (p: AgentPatch) => void;
}) {
  const [tools, setTools] = useState(new Set(agent.tools));
  const [scope, setScope] = useState(new Set(agent.org_scope));
  const actions = s.tools.filter((t) => t.agent_mode !== 'no' && t.implemented).map((t) => t.action);
  const options = [...new Set([...s.mcp_tools, ...actions, ...agent.tools])];
  const flip = (set: Set<string>, k: string) => {
    const n = new Set(set);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    return n;
  };
  return (
    <Modal
      title={'Change ' + agent.name}
      wide
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" disabled={busy} onClick={() => onSave({ tools: [...tools], org_scope: [...scope] })}>Save</button>
        </>
      }
    >
      <div className="grid g2" style={{ gap: '0 14px' }}>
        <fieldset className="fld">
          <legend>Tools it may use ({tools.size})</legend>
          <div style={{ maxHeight: 320, overflow: 'auto' }}>
            {options.map((t) => (
              <label key={t} className="row mono" style={{ gap: 6, fontSize: 12 }}>
                <input type="checkbox" checked={tools.has(t)} onChange={() => setTools(flip(tools, t))} /> {t}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="fld">
          <legend>Org scope</legend>
          <div className="hint">None ticked: every org.</div>
          {s.orgs.map((o) => (
            <label key={o} className="row" style={{ gap: 6 }}>
              <input type="checkbox" checked={scope.has(o)} onChange={() => setScope(flip(scope, o))} /> {o}
            </label>
          ))}
        </fieldset>
      </div>
    </Modal>
  );
}

/** The held proposals as the shared ProposalRow cards (the same card as Home and the assistant): what accepting does,
 *  the hold reasons, bulk accept for the same reason; Accept runs as the signed-in person, Reject asks why. */
function Proposals({ list }: { list: AgentProposal[] }) {
  return (
    <section className="sect" id="agProps">
      <div className="sh">
        <h2>Proposals waiting for you</h2>
        <span className="note">An agent prepared these; nothing runs until a person accepts it</span>
      </div>
      {list.length ? (
        <ProposalItems list={list.map((p) => ({ ...p, why: p.why ?? '' }))} idPrefix="agp-" label="Proposals waiting for you" className="as-list" />
      ) : (
        <div className="panel"><div className="pb"><div className="empty"><b>Nothing waiting</b>Proposals that agents hold for a person you may decide show here.</div></div></div>
      )}
    </section>
  );
}

function Waiting({ run }: { run: AgentRun }) {
  const w = run.waiting;
  if (!w) return <span className="note">{run.reason ?? '—'}</span>;
  if ('proposal' in w) {
    const go = () => document.getElementById('agp-' + w.proposal)?.scrollIntoView({ block: 'center' });
    return <button className="btn sm" onClick={go}>Proposal {w.proposal}</button>;
  }
  return w.case_id ? <a className="btn sm" href={caseHref(w.case_id)}>Approval of {w.case_id}</a> : <span className="note">A person</span>;
}

const PLAYBOOKS: Record<Playbook, string> = { case_autopilot: 'Case autopilot', stage_chain: 'Stage chain' };

/** Start a playbook on a case (Admin): the agent acts as the person who starts it (agent.startRun). */
function StartRun({ agents }: { agents: AgentRow[] }) {
  const action = useAction();
  const on = agents.filter((a) => a.enabled);
  const [agent, setAgent] = useState(on[0]?.id ?? '');
  const [caseId, setCaseId] = useState('');
  const [playbook, setPlaybook] = useState<Playbook>('case_autopilot');
  const [err, setErr] = useState('');
  const start = async () => {
    const r = await action.run(() => startRun(agent, caseId.trim(), playbook), { all: setErr });
    if (!r.ok) return;
    setErr('');
    setCaseId('');
    toast(`Run ${r.output.run_id} started: ${PLAYBOOKS[playbook].toLowerCase()} on ${r.output.case_id}.`);
  };
  return (
    <div className="ag-form ag-run">
      <div className="ag-field">
        <label htmlFor="ag-run-agent">Agent</label>
        <select className="sel" id="ag-run-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
          {on.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>
      <div className="ag-field">
        <label htmlFor="ag-run-playbook">Playbook</label>
        <select className="sel" id="ag-run-playbook" value={playbook} onChange={(e) => setPlaybook(e.target.value as Playbook)}>
          {(Object.keys(PLAYBOOKS) as Playbook[]).map((p) => <option key={p} value={p}>{PLAYBOOKS[p]}</option>)}
        </select>
      </div>
      <div className="ag-field">
        <label htmlFor="ag-run-case">Case</label>
        <input id="ag-run-case" value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="e.g. RT-1048" />
      </div>
      <button className="btn sm pri" disabled={action.pending || !agent || !caseId.trim()} onClick={start}>Start run</button>
      {err && <span className="note err">{err}</span>}
    </div>
  );
}

function Runs({ s }: { s: AgentsScreen }) {
  const runs = s.runs;
  const [open, setOpen] = useState<string | null>(null);
  // a run linked from the assistant's strip ("View the run", plan 10) opens its drawer: #/agents?run=<id>
  const linked = new URLSearchParams(useLocation().search).get('run');
  const [viewing, setViewing] = useState<string | null>(linked);
  return (
    <section className="sect" id="agRuns">
      {viewing && <Drawer title={'Run ' + viewing} sub="What the agent did, step by step" wide onClose={() => setViewing(null)}><RunView runId={viewing} /></Drawer>}
      <div className="sh">
        <h2>Runs</h2>
        <span className="note">{runs.length} recent · {runs.filter((r) => r.status === 'waiting').length} waiting for a person</span>
      </div>
      <div className="panel">
        {s.can.manage && <StartRun agents={s.agents} />}
        {runs.length ? (
          <div className="tw">
            <table className="t static">
              <thead><tr><th>Run</th><th>Agent</th><th>Playbook</th><th>Case</th><th>Status</th><th className="r">Steps</th><th>Waiting for</th></tr></thead>
              <tbody>
                {runs.map((r) => (
                  <Fragment key={r.id}>
                    <tr>
                      <td className="mono">{r.id}</td>
                      <td>{r.agentName}</td>
                      <td className="mono note">{r.playbook}{r.stage && <><br />Stage: {stageLabel(r.stage)}</>}</td>
                      <td>{r.case_id ? <a href={caseHref(r.case_id)}>{r.case_id}</a> : '—'}</td>
                      <td><span className={'chip ' + RUN_CHIP[r.status]}>{r.status}</span></td>
                      <td className="r">
                        <button className="btn sm ghost" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{r.steps.length}</button>
                      </td>
                      <td><Waiting run={r} /> <button className="btn sm ghost" onClick={() => setViewing(r.id)}>View</button></td>
                    </tr>
                    {open === r.id && (
                      <tr>
                        <td colSpan={7}>
                          {r.steps.map((st) => (
                            <div key={st.n} className={'ev ' + (st.ok ? '' : 'missing')}>
                              <span className="ic">{st.ok ? '✓' : '✕'}</span>
                              <div><b className="mono">{st.n}. {st.tool}</b>{st.note && <small>{st.note}</small>}</div>
                              <em className="num">{st.at.slice(11, 19)}</em>
                            </div>
                          ))}
                          {!r.steps.length && <span className="note">No calls yet.</span>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pb"><div className="empty"><b>No runs yet</b>An agent's playbook runs on a case show here, step by step.</div></div>
        )}
      </div>
    </section>
  );
}

/** One chip per mode: May call, Held for a person, A person only, or Not built yet. */
function ModeChip({ t }: { t: AgentsScreen['tools'][number] }) {
  if (!t.implemented) return <span className="chip line">Not built yet</span>;
  if (t.agent_mode === 'held') return <span className="chip warn">Held for a person</span>;
  return t.agent_mode === 'yes' ? <span className="chip ok">May call</span> : <span className="chip line">A person only</span>;
}

function Catalogue({ s }: { s: AgentsScreen }) {
  const [only, setOnly] = useState(false);
  const [q, setQ] = useState('');
  const [found, setFound] = useState<AgentsScreen['tools'] | null>(null);
  useEffect(() => {
    let live = true;
    if (!q.trim()) {
      setFound(null);
      return;
    }
    const t = setTimeout(() => void findTools(q).then((r) => live && setFound(r)), 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q]);
  const list = found ?? s.tools.filter((t) => !only || t.agent_mode !== 'no');
  return (
    <section className="sect" id="agTools">
      <div className="sh">
        <h2>Tool catalogue</h2>
        <span className="note">{s.tools.length} actions · {s.tools.filter((t) => t.agent_mode !== 'no').length} an agent may call or prepare</span>
        <span className="grow" />
        <input type="search" aria-label="Find a tool" placeholder="Find a tool: what do you want to do?" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg">
          <button aria-pressed={!only} onClick={() => setOnly(false)}>All</button>
          <button aria-pressed={only} onClick={() => setOnly(true)}>Agent may call</button>
        </div>
      </div>
      <div className="panel">
        <div className="tw" style={{ maxHeight: 480, overflow: 'auto' }}>
          <table className="t static tight">
            <thead><tr><th>Tool</th><th>Action</th><th>Risk</th><th>Agents</th><th>What it does</th></tr></thead>
            <tbody>
              {list.map((t) => (
                <tr key={t.action}>
                  <td className="mono">{t.name}</td>
                  <td>{t.title}</td>
                  <td><span className={'chip ' + (t.risk === 'read' ? 'ok' : t.risk === 'commit' ? 'bad' : 'line')}>{t.risk}</span></td>
                  <td><ModeChip t={t} /></td>
                  <td className="note">{t.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
