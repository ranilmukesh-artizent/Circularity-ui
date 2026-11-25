import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { invoke } from '../../api/actions';
import { mcpProposals } from '../../api/access';
import { useBackend } from '../../api/useBackend';
import {
  autoAgent, benchCases, caseOpenable, clientServers, exampleInput, hardRules, journeyStep,
  generatedTools, mcpAgents, PERM_CHIP, permCell, registryTools, runPlaygroundTool, tenantList, toolById,
  toolCalls, tools, toolSchema, type Tool, type ToolRun,
} from '../../api/mcp';
import { can, canPage } from '../../api/session';
import { sessionScoped } from '../../api/view';
import { Icon } from '../../components/Icon';
import { JsonView } from '../../components/kit/JsonView';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { ReqList } from '../access/AccessRequests';
import { SectionTabs, sectionsOf } from '../access/SectionTabs';
import type { PageProps } from '../registry';

// ---- view state that survives switching sections (the demo keeps it on S) ----
interface Pg { tool: string; agent: string | null; tenant: string; input: string | null; out: ToolRun | null; perm: string; callF: 'all' | 'issues' }
const pgState = sessionScoped<Pg>(() => ({ tool: 'get_case_evidence', agent: null, tenant: 'Customer A', input: null, out: null, perm: 'Customer A', callF: 'all' }));
function usePg(): [Pg, (p: Partial<Pg>) => void] {
  const [s, setS] = useState(pgState.current);
  return [s, (p) => setS((pgState.current = { ...pgState.current, ...p }))];
}

/** MCP & Tools: the demo's renderMcp, one section per route, plus the agent catalog and test bench (AF_ON). */
export function McpPage({ route }: PageProps) {
  useBackend();
  const { key } = sectionsOf('mcp', route.a);
  const [schema, setSchema] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  useEffect(() => {
    document.title = 'MCP & Tools · Circularity Decision Workbench';
  }, []);
  const showSchema = (id: string) => setSchema(id);

  return (
    <>
      <div className="phead">
        <div>
          <h1>MCP and tools</h1>
          <p>
            Agents and other platforms reach Circularity through governed tools. Agents assemble evidence, find opportunities, request gaps, coordinate approved
            instructions and reconcile results, always within their permissions.
          </p>
        </div>
      </div>
      <SectionTabs page="mcp" a={route.a} />
      {!can('useTools') && (
        <div className="callout info" style={{ marginBottom: 16 }}>
          <b>Read-only view.</b> The Developer manages agents, tools and MCP servers. {can('approve.mcp') ? 'You decide server proposals.' : ''}
        </div>
      )}
      {key === 'catalog' && (
        <>
          <RegistryCatalog />
          <Catalog onSchema={showSchema} />
        </>
      )}
      {key === 'agents' && (
        <>
          <AgentRegistry />
          <Generated />
        </>
      )}
      {key === 'playground' && canPage('mcp', 'playground') && (
        <>
          <div className="sect" id="pg">
            <div className="sh"><h2>Playground</h2></div>
            <Playground onSchema={showSchema} />
          </div>
          <Bench />
        </>
      )}
      {key === 'perms' && <Perms />}
      {key === 'calls' && <Calls />}
      {key === 'client' && <Client />}
      {key === 'proposals' && canPage('mcp', 'proposals') && <Proposals onPropose={() => setProposing(true)} />}
      {schema && <SchemaModal id={schema} onClose={() => setSchema(null)} />}
      {proposing && <ProposeModal onClose={() => setProposing(false)} />}
    </>
  );
}

/** Journey step chip, number only (stpn) or with its name (stp). */
function Stp({ n, full }: { n: number; full?: boolean }) {
  const j = journeyStep(n);
  return (
    <span className={'stp ' + j.status} title={`Journey step ${j.n}: ${j.name}${full ? ' — ' + j.desc : ''}`}>
      <b>{j.n}</b>
      {full && j.name}
    </span>
  );
}

function SchemaModal({ id, onClose }: { id: string; onClose: () => void }) {
  const t = toolById(id)!;
  return (
    <Modal title={id} onClose={onClose} foot={<button className="btn" onClick={onClose}>Close</button>}>
      <p className="ink2" style={{ marginTop: 0 }}>{t.desc}</p>
      <JsonView variant="escaped" value={toolSchema(t)} />
    </Modal>
  );
}

/** Per agent, the tools generated from the action catalogue and their MCP hints (P9-2.13). */
function Generated() {
  const rows = generatedTools().filter((a) => a.tools.length > 0);
  const yn = (b: boolean) => <span className={'chip ' + (b ? 'warn' : 'line')}>{b ? 'yes' : 'no'}</span>;
  return (
    <section className="sect" id="afGen">
      <div className="sh">
        <h2>Generated from the action catalogue</h2>
        <span className="note">an agent gets a tool only for an action it may run; never a delete or an approval</span>
      </div>
      <div className="panel">
        <div className="tw" style={{ maxHeight: 420, overflow: 'auto' }}>
          <table className="t static tight">
            <thead><tr><th>Agent</th><th>Tool</th><th>Action</th><th>Read only</th><th>Destructive</th><th>Needs a person</th></tr></thead>
            <tbody>
              {rows.flatMap((a) => a.tools.map((t) => (
                <tr key={a.agent + t.tool}>
                  <td>{a.name}</td>
                  <td className="mono">{t.tool}</td>
                  <td className="mono note">{t.action}</td>
                  <td>{yn(t.read_only)}</td>
                  <td>{yn(t.destructive)}</td>
                  <td>{yn(t.needs_person)}</td>
                </tr>
              )))}
              {rows.length === 0 && <tr><td colSpan={6} className="note">No agent has a tool from the catalogue yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function RegistryCatalog() {
  const L = registryTools();
  const exposed = (r: string) =>
    r === 'commit' ? 'Prepare only; a person presses the final button'
      : r === 'act' ? 'Runs after a plan preview, or on its own when autonomy allows'
        : r === 'draft' ? 'Runs; the draft can be discarded' : 'Runs within your permissions';
  return (
    <section className="sect" id="afCat">
      <div className="sh">
        <h2>Agent tools from the action registry</h2>
        <span className="note">{L.length} actions · the same ones every button calls</span>
      </div>
      <div className="panel">
        <div className="tw" style={{ maxHeight: 420, overflow: 'auto' }}>
          <table className="t static tight">
            <thead><tr><th>Tool</th><th>Tier</th><th>Exposed to agents as</th><th>Permission</th><th>What it does</th></tr></thead>
            <tbody>
              {L.map((A) => (
                <tr key={A.id}>
                  <td className="mono">{A.exposedAs}</td>
                  <td><span className={'chip ' + (A.risk === 'read' ? 'ok' : A.risk === 'commit' ? 'bad' : 'line')}>{A.riskLabel}</span></td>
                  <td className="note">{exposed(A.risk)}</td>
                  <td className="mono note">{A.perm}</td>
                  <td className="note">{A.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Catalog({ onSchema }: { onSchema: (id: string) => void }) {
  const nav = useNavigate();
  const [, setPg] = usePg();
  const T = tools();
  const rules = hardRules();
  const tryTool = (id: string) => {
    setPg({ tool: id, agent: null, input: null, out: null });
    nav('/mcp/playground');
  };
  return (
    <div id="mcpCatalog">
      <div className="callout" style={{ marginBottom: 16 }}>
        <b>Hard rules.</b> {rules.slice(0, 2).join(' ')} Technical eligibility stays with engineering and policy; the economic choice comes from predictive valuation
        and constrained optimization.
      </div>
      <section className="panel">
        <div className="ph">
          <h3>Tool catalog</h3>
          <span className="chip line">{T.length} tools · {T.filter((t) => t.rw === 'write').length} write</span>
        </div>
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Tool</th><th>What it does</th><th>Access</th><th>Journey step</th><th>Approval</th><th></th></tr></thead>
            <tbody>
              {T.map((t) => (
                <tr key={t.id}>
                  <td className="mono"><b>{t.id}</b></td>
                  <td>{t.desc}</td>
                  <td><span className={'chip ' + (t.rw === 'write' ? 'dk' : 'ok')}>{t.rw === 'write' ? 'Write' : 'Read'}</span></td>
                  <td>{t.step.map((n, i) => <span key={i}>{i > 0 && ' '}<Stp n={n} /></span>)}</td>
                  <td>
                    {t.approval === 'none' ? <span className="note">None</span>
                      : t.approval === 'human approval required' ? <span className="chip y">Human approval</span>
                        : <span className="chip line">{t.approval.replace('agent scope: ', '')} only</span>}
                  </td>
                  <td className="nowrap">
                    <button className="btn sm" onClick={() => onSchema(t.id)}>Schema</button>{' '}
                    {can('useTools') && canPage('mcp', 'playground') && <button className="btn sm" onClick={() => tryTool(t.id)}>Try</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function AgentRegistry() {
  return (
    <div className="sect" id="mcpAgents">
      <div className="sh"><h2>Agent registry</h2></div>
      <div className="grid g3">
        {mcpAgents().map((a) => (
          <div className="panel" key={a.id}>
            <div className="ph">
              <h3>{a.name}</h3>
              <span className="chip line">Step {a.step}</span>
            </div>
            <div className="pb">
              <div className="row" style={{ gap: 5, marginBottom: 8 }}>
                {a.scopes.map((s) => <span key={s} className="chip y mono" style={{ fontSize: 11 }}>{s}</span>)}
              </div>
              <p className="ink2" style={{ margin: '0 0 8px' }}><b>Authority:</b> {a.limit}</p>
              <div className="note">Tools: {a.tools.join(', ')}</div>
              <div className="note" style={{ marginTop: 4 }}>{a.calls} calls this month</div>
            </div>
          </div>
        ))}
        <div className="panel" style={{ border: '2px solid var(--ink)' }}>
          <div className="ph"><h3>Hard rules in the UI</h3></div>
          <div className="pb">
            <ol style={{ margin: 0, paddingLeft: 18 }}>
              {hardRules().map((r) => <li key={r} style={{ marginBottom: 6 }}>{r}</li>)}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}

function Playground({ onSchema }: { onSchema: (id: string) => void }) {
  const [pg, setPg] = usePg();
  const t = toolById(pg.tool) as Tool;
  const ag = pg.agent || autoAgent(t.id);
  const o = pg.out;
  const use = can('useTools');
  const example = JSON.stringify(exampleInput(t), null, 2);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    const raw = pg.input != null ? pg.input : example;
    setBusy(true);
    try {
      setPg({ input: raw, out: await runPlaygroundTool(t.id, ag, pg.tenant, raw) });
    } catch (x) {
      toast('The tool call did not reach the server: ' + (x as Error).message, 4200);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid g2 mcppg">
      <div className="panel">
        <div className="ph"><h3>Tool playground</h3><span className="chip ok">connected data</span></div>
        <div className="pb">
          <div className="grid g2">
            <div className="fld">
              <label htmlFor="pg-tool">Tool</label>
              <select id="pg-tool" value={t.id} disabled={!use} onChange={(e) => setPg({ tool: e.target.value, agent: null, input: null, out: null })}>
                {tools().map((x) => <option key={x.id} value={x.id}>{x.id}{x.rw === 'write' ? ' (write)' : ''}</option>)}
              </select>
            </div>
            <div className="fld">
              <label htmlFor="pg-ag">Calling as</label>
              <select id="pg-ag" value={ag} disabled={!use} onChange={(e) => setPg({ agent: e.target.value })}>
                {mcpAgents().map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
          </div>
          <div className="fld">
            <label htmlFor="pg-ten">On behalf of tenant</label>
            <select id="pg-ten" value={pg.tenant} disabled={!use} onChange={(e) => setPg({ tenant: e.target.value, out: null })}>
              {tenantList().map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
          <div className="fld">
            <label htmlFor="pg-in">Input (JSON)</label>
            <textarea
              id="pg-in" className="code" style={{ minHeight: 130, whiteSpace: 'pre' }} spellCheck={false} readOnly={!use}
              value={pg.input != null ? pg.input : example}
              onChange={(e) => setPg({ input: e.target.value })}
            />
            <div className="hint">{t.desc}</div>
          </div>
          <div className="row">
            {use && <button className="btn pri" onClick={run} disabled={busy}><Icon name="play" /> Run tool</button>}
            {use && <button className="btn" onClick={() => setPg({ input: null, out: null })}>Reset input</button>}
            <button className="btn ghost" onClick={() => onSchema(t.id)}>View schema</button>
          </div>
          <div className="note" style={{ marginTop: 8 }}>Tip: try the same tool as a different agent, or a case owned by another tenant.</div>
        </div>
      </div>
      <div className="panel">
        <div className="ph">
          <h3>Response and trace</h3>
          {o && (
            <>
              <span className={'chip ' + (o.ok ? 'ok' : o.outcome.startsWith('held') ? 'y' : 'bad')}>{o.ok ? 'ok' : o.outcome}</span>
              <span className="note num">{o.ms} ms</span>
            </>
          )}
        </div>
        <div className="pb">
          {o ? (
            <>
              <div style={{ marginBottom: 12 }}>
                {o.trace.map((s, i) => (
                  <div key={i} className={'ev ' + (s.ok ? '' : 'missing')}>
                    <span className="ic">{s.ok ? '✓' : '✕'}</span>
                    <div><b>{s.n}</b><small>{s.detail}</small></div>
                    {s.ms != null && <em className="num">{s.ms} ms</em>}
                  </div>
                ))}
              </div>
              <JsonView variant="escaped" value={o.ok ? o.result : { error: o.error }} />
            </>
          ) : (
            <div className="empty">
              <b>No call yet</b>Choose a tool, edit the JSON, and run it. Responses come from your connected data, with the schemas the MCP server exposes.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Bench() {
  const cases = benchCases();
  const [sel, setSel] = useState(0);
  return (
    <section className="sect" id="afBench">
      <div className="sh">
        <h2>Agent test bench</h2>
        <span className="note">Run any catalog intent against the seeded data and compare with the expected card</span>
      </div>
      <div className="panel">
        <div className="pb">
          <div className="row">
            <label className="sr" htmlFor="afBq">Intent test</label>
            <select id="afBq" className="sel" value={sel} onChange={(e) => setSel(+e.target.value)}>
              {cases.map((c) => <option key={c.i} value={c.i}>{c.label}</option>)}
            </select>
            {/* the bench ran the demo's in-browser agent layer; the server has no bench yet */}
            <button className="btn pri" onClick={() => toast('Not available yet.')}>Run</button>
            <button className="btn" onClick={() => toast('Not available yet.')}>Run all</button>
          </div>
          <div id="afBenchOut" className="afbench" />
        </div>
      </div>
    </section>
  );
}

function Perms() {
  const [pg, setPg] = usePg();
  const ten = pg.perm;
  const T = tools();
  return (
    <div className="sect" id="mcpPerms">
      <div className="sh">
        <h2>Permission matrix</h2>
        <label className="sr" htmlFor="pt">Tenant</label>
        <select className="sel" id="pt" value={ten} onChange={(e) => setPg({ perm: e.target.value })}>
          {tenantList().map((x) => <option key={x}>{x}</option>)}
        </select>
      </div>
      <div className="panel">
        <div className="tw">
          <table className="t static">
            <thead>
              <tr>
                <th>Agent</th>
                {T.map((t) => (
                  <th key={t.id} className="mono" style={{ fontSize: 10.5, writingMode: 'vertical-rl', transform: 'rotate(180deg)', height: 140, verticalAlign: 'bottom' }}>{t.id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mcpAgents().map((a) => (
                <tr key={a.id}>
                  <td><b>{a.name}</b></td>
                  {T.map((t) => {
                    const c = permCell(a, t, ten);
                    return (
                      <td key={t.id} style={{ textAlign: 'center' }}>
                        <span className={PERM_CHIP[c.k]} style={{ minWidth: 52, justifyContent: 'center' }} data-tip={c.tip} title={c.tip}>{c.l}</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="legend">
        <span><span className="chip ok">Read</span> within tenant</span>
        <span><span className="chip dk">Write</span> within scope</span>
        <span><span className="chip y">Human</span> needs approval</span>
        <span><span className="chip warn">Own only</span> no cross-client consent</span>
        <span><span className="chip line">—</span> no scope</span>
      </div>
    </div>
  );
}

function Calls() {
  const [pg, setPg] = usePg();
  const cf = pg.callF;
  const all = toolCalls();
  const calls = all.filter((c) => cf === 'all' || c.outcome !== 'ok').slice(0, 30);
  const held = all.filter((c) => c.outcome === 'held for approval').slice(0, 4);
  const wr = tools().filter((t) => t.rw === 'write');
  return (
    <div className="grid sect mcpcg" id="mcpCalls">
      <section className="panel">
        <div className="ph">
          <h3>Call log</h3>
          <div className="seg">
            <button aria-pressed={cf === 'all'} onClick={() => setPg({ callF: 'all' })}>All</button>
            <button aria-pressed={cf === 'issues'} onClick={() => setPg({ callF: 'issues' })}>Held or denied</button>
          </div>
        </div>
        <div className="tw" style={{ maxHeight: 420, overflow: 'auto' }}>
          <table className="t static">
            <thead><tr><th>Time</th><th>Agent</th><th>Tool</th><th>Case</th><th className="r">Latency</th><th>Outcome</th></tr></thead>
            <tbody>
              {calls.map((c, i) => (
                <tr key={i}>
                  <td className="num nowrap">{new Date(c.ts).toISOString().slice(11, 19)}</td>
                  <td>{c.agent}</td>
                  <td className="mono">{c.tool}</td>
                  <td>{caseOpenable(c.caseId) ? <a href={'#/product/' + c.caseId}>{c.caseId}</a> : c.caseId}</td>
                  <td className="r num">{c.lat} ms</td>
                  <td><span className={'chip ' + (c.outcome === 'ok' ? 'ok' : c.outcome.startsWith('held') ? 'y' : 'bad')}>{c.outcome}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="ph"><h3>Write-tool gate</h3><Stp n={5} full /></div>
        <div className="pb">
          <p className="ink2" style={{ marginTop: 0 }}>Write tools that commit stock, spend or price stop here until a person approves.</p>
          {wr.map((t) => (
            <div className="ev" key={t.id}>
              <span className="ic" style={{ background: 'var(--ink)', color: 'var(--bg)' }}>✎</span>
              <div>
                <b className="mono">{t.id}</b>
                <small>{t.approval === 'human approval required' ? 'Needs human approval' : 'Agent scope: ' + t.approval.replace('agent scope: ', '')}</small>
              </div>
              <em>{t.step.map((n) => 'S' + n).join(' ')}</em>
            </div>
          ))}
          <h4 style={{ margin: '14px 0 6px' }}>Needs human approval now</h4>
          {held.length ? (
            held.map((c, i) => (
              <div key={i} className="row" style={{ padding: '6px 0', borderBottom: '1px solid var(--line2)' }}>
                <span className="grow">
                  <b>{c.caseId}</b> <span className="note">{c.tool} · {c.agent}</span>
                </span>
                {caseOpenable(c.caseId) && <a className="btn sm" href={'#/product/' + c.caseId}>Review</a>}
              </div>
            ))
          ) : (
            <div className="note">Nothing waiting.</div>
          )}
        </div>
      </section>
    </div>
  );
}

function Client() {
  return (
    <div id="mcpClient">
      <p className="ink2" style={{ marginTop: 0, maxWidth: '75ch' }}>
        Circularity can consume enterprise MCP servers instead of custom adapters where they exist. Anything an adapter reads or writes still lands in the same
        canonical models and tenant boundaries.
      </p>
      <div className="grid g2">
        {clientServers().map((s) => (
          <div className="panel" key={s.id}>
            <div className="ph">
              <h3>{s.name}</h3>
              <span className={'chip ' + (s.status === 'connected' ? 'ok' : s.status === 'token expired' ? 'warn' : 'line')}>{s.status}</span>
            </div>
            <div className="pb">
              <div className="note" style={{ marginBottom: 8 }}>{s.owner} · used in {s.used}</div>
              <div className="row" style={{ gap: 5 }}>
                {s.tools.map((x, i) => <span key={i} className="chip line mono" style={{ fontSize: 11 }}>{x}</span>)}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="callout info" style={{ marginTop: 14 }}>
        Consumed tools are called with the same approval rules. A write through an enterprise MCP server still needs the human approval reference from step 5.
      </div>
    </div>
  );
}

function Proposals({ onPropose }: { onPropose: () => void }) {
  return (
    <div className="sect" id="mcpProps">
      <div className="sh">
        <h2>Server proposals</h2>
        <span className="grow" />
        {can('proposeMcp') && <button className="btn pri" onClick={onPropose}>Propose MCP server</button>}
      </div>
      <p className="note" style={{ margin: '-4px 0 10px' }}>
        New enterprise MCP servers are reviewed before any agent can call them.{' '}
        {can('approve.mcp') ? 'You can approve or decline pending proposals.' : 'An Approver with the MCP delegation, or Admin, decides.'}
      </p>
      <div className="panel">
        <div className="pb">
          <ReqList list={mcpProposals()} empty={['No proposals yet', 'The Developer proposes new servers here.']} />
        </div>
      </div>
    </div>
  );
}

function ProposeModal({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ n: '', o: '', p: '', t: '', a: 'read', d: '' });
  const [err, setErr] = useState('');
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function submit() {
    const r = await invoke<{ id: string }>('mcp.propose', {
      name: f.n.trim(), owner: f.o.trim(), purpose: f.p.trim(),
      tools: f.t.split(',').map((x) => x.trim()).filter(Boolean), access: f.a || 'read', data: f.d.trim(),
    });
    if (!r.ok) {
      let m = r.error.message;
      if (r.error.code === 'validation_error' && /"owner"/.test(m)) m = 'Enter the vendor or owner.';
      if (r.error.code === 'validation_error' && /"data"/.test(m)) m = 'Say what data it touches.';
      return setErr(m);
    }
    onClose();
    toast(r.output.id + ' submitted. It waits for an Approver or Admin.', 4200);
  }
  return (
    <Modal
      title="Propose an MCP server"
      wide
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" onClick={submit}>Submit for review</button>
        </>
      }
    >
      <p className="ink2" style={{ marginTop: 0 }}>An Approver with the MCP delegation, or Admin, reviews every new server before agents can use it.</p>
      <div className="grid g2" style={{ gap: '0 14px' }}>
        <div className="fld">
          <label htmlFor="mp-n">Server name</label>
          <input id="mp-n" maxLength={60} placeholder="e.g. Fleet telematics MCP server" autoComplete="off" value={f.n} onChange={set('n')} />
        </div>
        <div className="fld">
          <label htmlFor="mp-o">Vendor or owner</label>
          <input id="mp-o" maxLength={40} placeholder="e.g. TrackLine" autoComplete="off" value={f.o} onChange={set('o')} />
        </div>
      </div>
      <div className="fld">
        <label htmlFor="mp-p">Purpose</label>
        <textarea id="mp-p" maxLength={300} placeholder="What agents would use it for" value={f.p} onChange={set('p')} />
      </div>
      <div className="grid g2" style={{ gap: '0 14px' }}>
        <div className="fld">
          <label htmlFor="mp-t">Tools it exposes</label>
          <input id="mp-t" maxLength={200} placeholder="Comma separated, e.g. telemetry.hours" autoComplete="off" value={f.t} onChange={set('t')} />
        </div>
        <div className="fld">
          <label htmlFor="mp-a">Access</label>
          <select id="mp-a" value={f.a} onChange={set('a')}>
            <option value="read">Read only</option>
            <option value="write">Read and write</option>
          </select>
        </div>
      </div>
      <div className="fld">
        <label htmlFor="mp-d">Data it touches</label>
        <input id="mp-d" maxLength={160} placeholder="e.g. device telemetry; no personal data" autoComplete="off" value={f.d} onChange={set('d')} />
        <div className="hint">Describe data categories only. Do not paste real records.</div>
      </div>
      {err && <div className="err" id="mp-err">{err}</div>}
    </Modal>
  );
}
