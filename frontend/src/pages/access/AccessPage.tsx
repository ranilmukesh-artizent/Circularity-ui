import { useEffect, useRef, useState } from 'react';
import { invoke } from '../../api/actions';
import {
  accountRows, agentMetrics, approvalLimit, autoLevel, autoTypes, delegationLabel, delegations, facilities, fmtDateTime,
  governedAgents, hardRules, idp, idpRoleOf, idpRoles, levelRank, levels, pctTxt, refreshAccess, requests, roles, runLimits,
  selfApproveAllowed, type Level,
} from '../../api/access';
import { money } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { accounts, can, rolePolicy } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import type { PageProps } from '../registry';
import { Orgs } from './AccessOrgs';
import { ReqList } from './AccessRequests';
import { SectionTabs, sectionsOf } from './SectionTabs';

/** Access & Governance (Admin): the demo's renderAccess plus afAccessHTML, one section per route. */
export function AccessPage({ route }: PageProps) {
  useBackend();
  const { key } = sectionsOf('access', route.a);
  useEffect(() => {
    document.title = 'Access · Circularity Decision Workbench';
  }, []);
  return (
    <>
      <div className="phead">
        <div>
          <h1>Access</h1>
          <p>Who signs in as what, what the Approver may decide, and every access request. Every change is recorded in the audit log.</p>
        </div>
      </div>
      <SectionTabs page="access" a={route.a} />
      {key === 'accounts' && <Accounts />}
      {key === 'identity' && <Identity />}
      {key === 'delegations' && <Delegations />}
      {key === 'requests' && <AllRequests />}
      {key === 'autonomy' && <Autonomy />}
      {key === 'limits' && <Limits />}
      {key === 'agentsx' && <Agents />}
      {key === 'metrics' && <Metrics />}
      {key === 'orgs' && <Orgs />}
    </>
  );
}

function Accounts() {
  const rows = accountRows();
  return (
    <section className="panel" id="axAccounts">
      <div className="ph">
        <h3>Accounts and roles</h3>
        <span className="chip line">{rows.length} accounts</span>
      </div>
      <div className="tw">
        <table className="t static">
          <thead>
            <tr><th>Account</th><th>Role</th><th>Tenants</th><th>Lands on</th><th>What the role does</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.account.id}>
                <td><b>{r.account.label}</b></td>
                <td>{r.account.role}</td>
                <td>{r.tenants}</td>
                <td>{r.landsOn}</td>
                <td className="note">{r.policy.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note" style={{ padding: '8px 14px' }}>
        Accounts arrive from your identity provider (see Identity and users). Tenant grants last for the session.
      </div>
    </section>
  );
}

function Identity() {
  const I = idp();
  const accts = accounts().filter((a) => a.role !== 'Admin');
  const eligible = I.users.filter((u) => idpRoleOf(u) === 'Approver' && u.acct !== 'approver');
  const manage = can('manageIdentity');
  const [to, setTo] = useState(eligible[0]?.id ?? '');
  const [from, setFrom] = useState('2026-10-20');
  const [until, setUntil] = useState('2026-10-31');
  const action = useAction();
  const [err, setErr] = useState('');
  const approles = I.src === 'approles';

  const sync = async () => {
    if ((await invoke('access.syncDirectory', {})).ok) toast('Directory synced.');
  };
  const mapTo = async (acct: string, field: 'role' | 'site', value: string) => {
    const r = await action.run(() => invoke<{ label: string }>('access.mapIdentity', { acct, field, value }), 4200);
    if (!r.ok) return;
    toast('Mapping updated. ' + r.output.label + ' changes at their next sign-in.');
    void refreshAccess();
  };
  const remove = async (id: string) => {
    const r = await invoke<{ email: string }>('access.removeUser', { id });
    if (r.ok) toast(r.output.email + ' removed at the next provisioning sync.');
  };
  const saveOoo = async () => {
    const r = await action.run(() => invoke('access.setOutOfOffice', { to: to || eligible[0]?.id || '', from, until }), { all: setErr });
    if (!r.ok) return;
    setErr('');
    toast('Out-of-office delegation saved.');
  };

  return (
    <section className="panel sect" id="axIdp">
      <div className="ph">
        <div>
          <h3>Identity and users</h3>
          <div className="note">Synced from your identity provider</div>
        </div>
        <span className="sp" />
        <span className="chip ok">SCIM</span>
      </div>
      <div className="pb">
        <div className="idpg">
          <div className="idpc">
            <b>Identity provider</b>
            <span>Microsoft Entra ID (example)</span>
            <span className="note mono">Tenant ID 00000000-0000-0000-0000-000000000000 (placeholder)</span>
            <span className="note">Last directory sync {fmtDateTime(I.lastSync)}</span>
            {manage && (
              <div className="row" style={{ marginTop: 6 }}>
                <button className="btn sm pri" onClick={sync}>Sync from directory</button>
              </div>
            )}
          </div>
          <div className="idpc">
            <b>Setup order</b>
            <ol className="idps">
              <li><span className="chip ok">Done</span> 1 Single sign-on (SAML or OIDC)</li>
              <li><span className="chip ok">Done</span> 2 Provisioning (SCIM): creates, updates and removes users</li>
              <li><span className="chip ok">Done</span> 3 Role mapping</li>
            </ol>
            <span className="note">SSO must work before provisioning is switched on.</span>
          </div>
          <div className="idpc">
            <label htmlFor="idp-src"><b>Role source</b></label>
            <select id="idp-src" className="sel" value={I.src} disabled={!manage} onChange={(e) => invoke('access.setRoleSource', { src: e.target.value })}>
              <option value="approles">Entra ID App Roles (recommended)</option>
              <option value="groups">Directory groups</option>
            </select>
            <span className="note">App Roles keep working when a group is renamed and avoid group-overage limits.</span>
          </div>
        </div>
        <h4 style={{ margin: '14px 0 6px' }}>{approles ? 'App Role' : 'Directory group'} to role mapping</h4>
        <div className="tw">
          <table className="t static tight" id="idpMap">
            <thead>
              <tr><th>{approles ? 'App Role' : 'Group'}</th><th>Role</th><th>Tenant</th><th>Site or warehouse</th><th>Members</th></tr>
            </thead>
            <tbody>
              {accts.map((a) => {
                const grp = I.groups[a.id];
                return (
                  <tr key={a.id}>
                    <td className="mono">{approles ? grp.replace('circ-', 'Circularity.') : grp}</td>
                    <td>
                      <select className="sel" aria-label={'Role for ' + grp} value={a.role} disabled={!manage} onChange={(e) => mapTo(a.id, 'role', e.target.value)}>
                        {idpRoles().map((r) => <option key={r}>{r}</option>)}
                      </select>
                    </td>
                    <td>{rolePolicy(a.role).tenantScoped ? a.tenant || '—' : 'All'}</td>
                    <td>
                      <select className="sel" aria-label={'Site for ' + grp} value={a.warehouse || a.site || ''} disabled={!manage} onChange={(e) => mapTo(a.id, 'site', e.target.value)}>
                        <option value="">—</option>
                        {facilities().map((f) => <option key={f}>{f}</option>)}
                      </select>
                    </td>
                    <td className="note">1 · managed in your identity provider</td>
                  </tr>
                );
              })}
              <tr><td className="mono">—</td><td>Admin</td><td>All</td><td>—</td><td className="note">Assigned directly, never through a group</td></tr>
            </tbody>
          </table>
        </div>
        <p className="note" style={{ margin: '6px 0 0' }}>
          Group membership is read-only here. Mapped roles only add permissions; a user's effective access is the union of their roles.
        </p>
        <h4 style={{ margin: '14px 0 6px' }}>
          Users <span className="note">{I.users.length} from directory</span>
        </h4>
        <div className="tw">
          <table className="t static tight" id="idpUsers">
            <thead><tr><th>User</th><th>Role</th><th>Source</th></tr></thead>
            <tbody>
              {I.users.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.email}</td>
                  <td>{idpRoleOf(u)}</td>
                  <td><span className="chip line">From directory</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note" style={{ margin: '6px 0 0' }}>
          There is no Add user form. Users are added in your identity provider and appear after the next sync. A user removed in the directory loses access at
          the next provisioning sync; without provisioning, only at their next sign-in.
        </p>
        <div className="row" style={{ marginTop: 8 }}>
          {manage && I.users.some((u) => u.id === 'dep-pl') && (
            <button className="btn sm" onClick={() => remove('dep-pl')}>Apply directory removal</button>
          )}
        </div>
        <h4 style={{ margin: '16px 0 6px' }}>Approval hierarchy and delegation</h4>
        <dl className="tikv">
          <div><dt>Escalation path</dt><dd>Approver → Admin</dd></div>
          <div><dt>Limits</dt><dd>Approvals above $25k need Admin (shown only; assumed)</dd></div>
        </dl>
        <div className="grid g3" style={{ gap: '0 12px', marginTop: 8 }}>
          <div className="fld">
            <label htmlFor="ooo-to">Out-of-office delegate</label>
            <select id="ooo-to" value={to} onChange={(e) => setTo(e.target.value)}>
              {eligible.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
            </select>
            <div className="hint">Only users who already hold the Approver role can be picked.</div>
          </div>
          <div className="fld">
            <label htmlFor="ooo-from">From</label>
            <input id="ooo-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="fld">
            <label htmlFor="ooo-until">Until</label>
            <input id="ooo-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
          </div>
        </div>
        {err && <div className="err" id="ooo-err">{err}</div>}
        {manage && <button className="btn sm" onClick={saveOoo}>Save delegation</button>}
        {I.ooo.length > 0 && (
          <ul className="tiout" style={{ marginTop: 8 }}>
            {I.ooo.map((o, i) => (
              <li key={i}>
                <b>Approver → {o.email}</b>
                <span className="note">
                  {o.from} to {o.until} · whoever acts first completes the item{' '}
                  {manage && (
                    <button className="lnk" onClick={() => invoke('access.clearOutOfOffice', { index: i })}>Remove</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function Delegations() {
  const action = useAction();
  const manage = can('manageAccess');
  const toggle = async (k: string, on: boolean) => {
    const d = delegations().find((x) => x.k === k)!;
    const r = await action.run(() => invoke('access.setDelegation', { k, on }), 4200);
    if (!r.ok) return;
    void refreshAccess();
    toast(on ? 'The Approver can now decide ' + delegationLabel(d) + '.' : d.label + ' are now decided by Admin only.', 4200);
  };
  return (
    <section className="panel sect" id="axDeleg">
      <div className="ph">
        <h3>Approver delegations</h3>
        <span className="note">What the Approver may decide; Admin can always decide</span>
      </div>
      <div className="pb">
        {delegations().map((d) => (
          <label className="axd" key={d.k}>
            <input type="checkbox" checked={d.on} disabled={!manage} onChange={(e) => toggle(d.k, e.target.checked)} />
            <span>
              <b>{d.label}</b>
              <span className="note">{d.desc}</span>
            </span>
            <span className={'chip ' + (d.on ? 'ok' : 'line')}>{d.on ? 'Delegated' : 'Admin only'}</span>
          </label>
        ))}
      </div>
    </section>
  );
}

function AllRequests() {
  const all = requests();
  const pend = all.filter((r) => r.status === 'pending').length;
  return (
    <section className="panel sect" id="axReqs">
      <div className="ph">
        <h3>All requests</h3>
        <span className={'chip ' + (pend ? 'warn' : 'ok')}>{pend} pending</span>
      </div>
      <div className="pb">
        <ReqList list={all} empty={['No requests yet', 'Tenant access requests and MCP server proposals appear here.']} />
      </div>
    </section>
  );
}

function Autonomy() {
  const action = useAction();
  const L = levels();
  const rs = roles();
  const manage = can('manageAccess');
  const set = async (role: string, type: string, level: Level) => {
    const r = await action.run(() => invoke('access.setAutonomy', { role, type, level }), 4200);
    if (!r.ok) return;
    toast(role + ': ' + autoTypes().find((t) => t.k === type)!.t.toLowerCase() + ' → ' + L.find((l) => l.k === level)!.label + '.');
  };
  return (
    <section className="panel sect" id="axAuto">
      <div className="ph">
        <h3>Agent autonomy</h3>
        <span className="note">Role by action type, capped by the action's risk tier. Reads, drafts and what-ifs are always allowed.</span>
      </div>
      <div className="tw">
        <table className="t static tight afauto">
          <thead>
            <tr><th>Action type</th><th>Cap</th>{rs.map((r) => <th key={r}>{r}</th>)}</tr>
          </thead>
          <tbody>
            {autoTypes().map((t) => (
              <tr key={t.k}>
                <td><b>{t.t}</b></td>
                <td className="note">{L.find((l) => l.k === t.max)!.label}</td>
                {rs.map((r) => {
                  const id = `au-${r}-${t.k}`;
                  return (
                    <td key={r}>
                      <label className="sr" htmlFor={id}>{r}: {t.t}</label>
                      <select id={id} className="sel" value={autoLevel(r, t.k)} disabled={!manage} onChange={(e) => set(r, t.k, e.target.value as Level)}>
                        {L.filter((l) => levelRank(l.k) <= levelRank(t.max)).map((l) => <option key={l.k} value={l.k}>{l.label}</option>)}
                      </select>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pb note">
        {L.map((l, i) => (
          <span key={l.k}>
            {i > 0 && ' · '}
            <b>{l.label}</b>: {l.desc}
          </span>
        ))}
        . Defaults: Prepare everywhere (assumed, PR open decision). Every change is a commit by a person and goes to the audit log.
      </div>
    </section>
  );
}

function LimitRow({ role, manage }: { role: string; manage: boolean }) {
  const v = approvalLimit(role);
  const action = useAction();
  const ref = useRef<HTMLInputElement>(null);
  const save = async () => {
    const s = ref.current?.value ?? '';
    const r = await action.run(() => invoke<{ limit: number | null }>('access.setLimit', { role, amount: s === '' ? null : +s }), 4200);
    if (!r.ok) return;
    void refreshAccess();
    toast(role + ' approval limit: ' + (r.output.limit == null ? 'unlimited' : money(r.output.limit)) + '.');
  };
  return (
    <tr>
      <td>
        <b>{role}</b>
        {role === 'Planner' && <div className="note">$0 means Planners cannot approve. Raise it to let them approve within the limit.</div>}
      </td>
      <td>
        <label className="sr" htmlFor={'lim-' + role}>{role} limit</label>
        <input key={String(v)} ref={ref} id={'lim-' + role} type="number" min={0} step={500} defaultValue={v == null ? '' : v} placeholder="Unlimited" style={{ width: 140 }} />
      </td>
      <td>{manage && <button className="btn sm" onClick={save}>Save</button>}</td>
    </tr>
  );
}

function Limits() {
  const action = useAction();
  const manage = can('manageAccess');
  const rl = runLimits();
  const aRef = useRef<HTMLInputElement>(null);
  const bRef = useRef<HTMLInputElement>(null);
  const saveRun = async () => {
    const r = await action.run(() => invoke('access.setRunLimits', { actions: +(aRef.current?.value ?? 0), bulk: +(bRef.current?.value ?? 0) }), 4200);
    if (!r.ok) return;
    toast('Run limits saved.');
  };
  const self = async (on: boolean) => {
    const r = await invoke('access.setSelfApprove', { on });
    if (r.ok) toast(on ? 'Self-approval allowed within the limit.' : 'Self-approval not allowed.');
  };
  return (
    <section className="panel sect" id="axLimits">
      <div className="ph">
        <h3>Approval limits</h3>
        <span className="note">A decision above the approver's limit escalates to Admin</span>
      </div>
      <div className="pb">
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Role</th><th>Limit (USD)</th><th></th></tr></thead>
            <tbody>
              {['Approver', 'Admin', 'Planner'].map((r) => <LimitRow key={r} role={r} manage={manage} />)}
            </tbody>
          </table>
        </div>
        <label className="tog" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={selfApproveAllowed()} disabled={!manage} onChange={(e) => self(e.target.checked)} /> Allow a person to approve a decision
          they submitted, within their limit
        </label>
        <div className="axrl" key={rl.actions + '/' + rl.bulk}>
          <label htmlFor="rl-a">Max actions per agent run</label>
          <input ref={aRef} id="rl-a" type="number" min={1} max={500} defaultValue={rl.actions} style={{ width: 90 }} />
          <label htmlFor="rl-b">Max items per bulk plan</label>
          <input ref={bRef} id="rl-b" type="number" min={1} max={1000} defaultValue={rl.bulk} style={{ width: 90 }} />
          {manage && <button className="btn sm" onClick={saveRun}>Save</button>}
        </div>
      </div>
    </section>
  );
}

function Agents() {
  const action = useAction();
  const manage = can('manageAccess');
  const kill = async (id: string, name: string, on: boolean) => {
    const r = await action.run(() => invoke('agent.setEnabled', { id, on }));
    if (!r.ok) return;
    toast(name + (on ? ' is running again.' : ' is stopped. The runtime will not call it.'));
  };
  return (
    <section className="panel sect" id="axAgents">
      <div className="ph">
        <h3>Agents and kill switches</h3>
        <span className="note">Each agent acts as the signed-in person and never has more rights</span>
      </div>
      <div className="tw">
        <table className="t static tight">
          <thead>
            <tr><th>Agent</th><th>Scopes</th><th>Limits</th><th className="r">Prepared</th><th>Status</th></tr>
          </thead>
          <tbody>
            {governedAgents().map((a) => (
              <tr key={a.id}>
                <td>
                  <b>{a.name}</b>
                  <div className="note mono">{a.id}</div>
                </td>
                <td className="mono note">{a.scopes.join(', ')}</td>
                <td className="note">{a.limit}</td>
                <td className="r num">{a.prepared}</td>
                <td>
                  <label className="tog">
                    <input type="checkbox" checked={!a.stopped} disabled={!manage} onChange={(e) => kill(a.id, a.name, e.target.checked)} />{' '}
                    {a.stopped ? <span className="chip bad">Stopped</span> : <span className="chip ok">Running</span>}
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pb">
        <h4 style={{ margin: '0 0 6px' }}>Hard rules (never configurable)</h4>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {hardRules().map((h) => <li key={h}>{h}</li>)}
        </ul>
      </div>
    </section>
  );
}

function Metrics() {
  const M = agentMetrics();
  const share = Object.entries(M.share).map(([r, v]) => r + ' ' + pctTxt(v.agent / Math.max(1, v.all))).join(' · ');
  return (
    <section className="panel sect" id="axMetrics">
      <div className="ph">
        <h3>Agent metrics</h3>
        <span className="note">Success measures, counted from the journal and agent runs in this browser</span>
      </div>
      <div className="tw">
        <table className="t static tight">
          <thead>
            <tr><th>Measure</th><th>Now</th><th>Baseline (21 Oct, before the agent)</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Interactions to approve a recommended decision</td>
              <td className="num">{M.interactions == null ? '—' : M.interactions + ' over ' + M.approvals + ' approval' + (M.approvals > 1 ? 's' : '')}</td>
              <td className="num">7</td>
            </tr>
            <tr><td>Share of changes started through the agent</td><td>{share || '—'}</td><td>0%</td></tr>
            <tr><td>Proposal acceptance (no edit)</td><td>{pctTxt(M.acceptance)}</td><td>—</td></tr>
            <tr><td>Edit rate</td><td>{pctTxt(M.edit)}</td><td>—</td></tr>
            <tr><td>Undo rate</td><td>{pctTxt(M.undo)}</td><td>—</td></tr>
            <tr><td>Fallback rate (“I can't do that yet”)</td><td>{pctTxt(M.fallback)} of {M.runs} runs</td><td>—</td></tr>
            <tr><td>Time to decision (received to approval, median)</td><td>{M.ttd == null ? '—' : M.ttd + ' days'}</td><td>—</td></tr>
            <tr><td>Agent response time (mean)</td><td>{M.ms == null ? '—' : M.ms + ' ms'}</td><td>—</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
