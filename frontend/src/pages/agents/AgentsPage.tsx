import { Fragment, useEffect, useState } from 'react';
import {
  acceptProposal, OWN_PROPOSAL_NOTE, rejectProposal, startRun, updateAgent, useAgents,
  type AgentPatch, type AgentProposal, type AgentRow, type AgentRun, type AgentsScreen, type Autonomy,
} from '../../api/agents'; // prettier-ignore
import { useBackend } from '../../api/useBackend';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { ModelsPanel } from './ModelsPanel';
import { RegisterAgentDialog } from './RegisterAgentDialog';

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
            The agents that may call Circularity, what they may use and how far they may go. Agents prepare and propose; a person accepts, approves and changes
            access.
          </p>
        </div>
      </div>
      {!s.can.manage && (
        <div className="callout info" style={{ marginBottom: 16 }}>
          <b>Read-only view.</b> Admin manages agents. You accept or reject the proposals your permissions cover.
        </div>
      )}
      <Registry s={s} />
      <Proposals list={s.proposals} />
      <Runs s={s} />
      <ModelsPanel />
      <Catalogue s={s} />
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
        <h2>Registry</h2>
        <span className="note">{s.agents.length} agents · {s.agents.filter((a) => !a.enabled).length} stopped</span>
        <span className="grow" />
        {s.can.manage && <button className="btn sm pri" id="ag-register" onClick={() => setRegistering(true)}>Register agent</button>}
      </div>
      <div className="panel">
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Agent</th><th>Kind</th><th>Status</th><th>Autonomy</th><th>Tools</th><th>Org scope</th><th></th></tr></thead>
            <tbody>
              {s.agents.map((a) => (
                <tr key={a.id} data-agent={a.id}>
                  <td><b>{a.name}</b> <span className="note mono">{a.id}</span></td>
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
                        <select id={'ag-au-' + a.id} value={a.autonomy} disabled={action.pending} onChange={(e) => change(a, { autonomy: e.target.value as Autonomy }, a.name + ' autonomy changed.')}>
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

function EditModal({ s, agent, busy, onClose, onSave }: {
  s: AgentsScreen; agent: AgentRow; busy: boolean; onClose: () => void; onSave: (p: AgentPatch) => void;
}) {
  const [tools, setTools] = useState(new Set(agent.tools));
  const [scope, setScope] = useState(new Set(agent.org_scope));
  const actions = s.tools.filter((t) => t.agent_allowed).map((t) => t.action);
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

function Proposals({ list }: { list: AgentProposal[] }) {
  const action = useAction();
  const [rejecting, setRejecting] = useState<AgentProposal | null>(null);
  const [reason, setReason] = useState('');
  const accept = async (p: AgentProposal) => {
    const r = await action.run(() => acceptProposal(p.id));
    if (r.ok) toast(`Proposal ${p.id} accepted: ${p.title} ran as you.`);
  };
  const reject = async () => {
    if (!rejecting) return;
    const r = await action.run(() => rejectProposal(rejecting.id, reason.trim()));
    if (!r.ok) return;
    toast(`Proposal ${rejecting.id} rejected.`);
    setRejecting(null);
    setReason('');
  };
  return (
    <section className="sect" id="agProps">
      <div className="sh">
        <h2>Proposals waiting for you</h2>
        <span className="note">An agent prepared these; nothing runs until a person accepts it</span>
      </div>
      <div className="panel">
        {list.length ? (
          <div className="tw">
            <table className="t static">
              <thead><tr><th>#</th><th>Agent</th><th>Action</th><th>Case</th><th>Prepared</th><th></th></tr></thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id} id={'agp-' + p.id}>
                    <td className="num">{p.id}</td>
                    <td>{p.agentName}</td>
                    <td>{p.title} <span className="note mono">{p.action}</span></td>
                    <td>{p.case_id ? <a href={caseHref(p.case_id)}>{p.case_id}</a> : <span className="note">—</span>}</td>
                    <td className="num nowrap">{p.at.slice(0, 16).replace('T', ' ')}</td>
                    <td className="nowrap">
                      {p.own ? <span className="note">{OWN_PROPOSAL_NOTE}</span> : <button className="btn sm pri" disabled={action.pending} onClick={() => accept(p)}>Accept</button>}{' '}
                      <button className="btn sm" disabled={action.pending} onClick={() => setRejecting(p)}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pb"><div className="empty"><b>Nothing waiting</b>Proposals that agents hold for a person you may decide show here.</div></div>
        )}
      </div>
      {rejecting && (
        <Modal
          title={'Reject proposal ' + rejecting.id}
          onClose={() => setRejecting(null)}
          foot={
            <>
              <button className="btn" onClick={() => setRejecting(null)}>Cancel</button>
              <button className="btn pri" disabled={action.pending} onClick={reject}>Reject</button>
            </>
          }
        >
          <div className="fld">
            <label htmlFor="agp-reason">Reason for the agent's owner</label>
            <textarea id="agp-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </Modal>
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

/** Start the case autopilot on a case (Admin): the agent acts as the person who starts it (agent.startRun). */
function StartRun({ agents }: { agents: AgentRow[] }) {
  const action = useAction();
  const on = agents.filter((a) => a.enabled);
  const [agent, setAgent] = useState(on[0]?.id ?? '');
  const [caseId, setCaseId] = useState('');
  const [err, setErr] = useState('');
  const start = async () => {
    const r = await action.run(() => startRun(agent, caseId.trim()), { all: setErr });
    if (!r.ok) return;
    setErr('');
    setCaseId('');
    toast(`Run ${r.output.run_id} started: case autopilot on ${r.output.case_id}.`);
  };
  return (
    <div className="pb axrl" style={{ borderBottom: '1px solid var(--line)' }}>
      <label htmlFor="ag-run-agent">Agent</label>
      <select id="ag-run-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
        {on.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <label htmlFor="ag-run-case">Case</label>
      <input id="ag-run-case" value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="e.g. RT-1048" style={{ width: 120 }} />
      <button className="btn sm pri" disabled={action.pending || !agent || !caseId.trim()} onClick={start}>Start case autopilot</button>
      {err && <span className="note err">{err}</span>}
    </div>
  );
}

function Runs({ s }: { s: AgentsScreen }) {
  const runs = s.runs;
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="sect" id="agRuns">
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
                      <td className="mono note">{r.playbook}</td>
                      <td>{r.case_id ? <a href={caseHref(r.case_id)}>{r.case_id}</a> : '—'}</td>
                      <td><span className={'chip ' + RUN_CHIP[r.status]}>{r.status}</span></td>
                      <td className="r">
                        <button className="btn sm ghost" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{r.steps.length}</button>
                      </td>
                      <td><Waiting run={r} /></td>
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

function Catalogue({ s }: { s: AgentsScreen }) {
  const [only, setOnly] = useState(false);
  const list = s.tools.filter((t) => !only || t.agent_allowed);
  return (
    <section className="sect" id="agTools">
      <div className="sh">
        <h2>Tool catalogue</h2>
        <span className="note">{s.tools.length} actions · {s.tools.filter((t) => t.agent_allowed).length} an agent may call</span>
        <span className="grow" />
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
                  <td>{t.agent_allowed ? <span className="chip ok">May call</span> : <span className="chip line">A person only</span>}</td>
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
