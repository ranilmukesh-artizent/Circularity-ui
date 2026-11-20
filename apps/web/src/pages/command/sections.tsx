/** Command Center panels: exceptions, Notify, Actions on me, handed off, approvals inbox, outcomes and the ranked table. */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  acknowledge, aomeItems, approvalCards, approvalLimit, awaitingApproval, ccFilters, clsIcon, decideRequest, decisionsAwaiting,
  exOwner, exRows, handedRows, inboxRequests, inboxScope, kfmt, rbPath, notifyRecipients, opScopeInfo, oppRow, oppRows, outcomesToConfirm,
  sendNotification, setCcFilters, toggleOpScope, type AccessRequest, type CcCase, type CcScope, type ExRow,
} from '../../api/command';
import { fmtDateYear, money } from '../../api/format';
import { can, canPage } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { Drawer, Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
const plural = (n: number, w: string) => n + ' ' + w + (n === 1 ? '' : 's');

/** Row that opens on click and on Enter, like the demo's data-act rows with tabindex. */
function rowProps(onOpen: () => void) {
  return { tabIndex: 0, onClick: onOpen, onKeyDown: (e: React.KeyboardEvent) => e.key === 'Enter' && onOpen() };
}
export function useOpenCase() {
  const nav = useNavigate();
  return (id: string) => nav('/product/' + id);
}

export function StageChip({ c }: { c: CcCase }) {
  switch (c.stage) {
    case 'awaiting_approval': return <span className="chip y">Awaiting approval</span>;
    case 'approved': return <span className="chip dk">Approved · handing off</span>;
    case 'executing': return <span className="chip ok" data-tip="Instruction sent; the enterprise system carries out the work and reports the outcome">Handed off</span>;
    case 'reeval': return <span className="chip warn">Re-evaluate</span>;
    case 'none': return c.blocked ? <span className="chip bad">Needs evidence</span> : <span className="chip line">—</span>;
    case 'closed': return <span className="chip ok">Closed</span>;
    default: return null;
  }
}

function OpScopeChip() {
  const { home, scope, locked } = opScopeInfo();
  if (!home) return null;
  return (
    <>
      <span className="chip line">{scope || 'All locations'}</span>
      {!locked && (
        <>
          {' '}
          <button className="lnk" onClick={toggleOpScope}>{scope ? 'Show all locations' : 'Back to ' + home}</button>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- exceptions by warehouse

export function Exceptions({ sc }: { sc: CcScope }) {
  const nav = useNavigate();
  const l = exRows(sc);
  const [view, setView] = useState<string | null>(null);
  const [notify, setNotify] = useState<string | null>(null);
  const find = (id: string | null) => (id ? l.find((x) => x.id === id) : undefined);
  const open = (x: ExRow) => {
    if (x.go) {
      if (rbPath(x.go)) nav('/' + x.go);
      else toast('Open Analytics for this metric.');
      return;
    }
    setView(x.id);
  };
  let prev = '';
  const viewing = find(view), notifying = find(notify);
  return (
    <section className="panel exp" id="ccEx">
      <div className="ph">
        <div>
          <h3>Exceptions by warehouse</h3>
          <div className="note">Which warehouse, what item, what value. Notify the owner when something is not being actioned.</div>
        </div>
        <span className="sp" />
        <span className={'chip ' + (l.length ? 'warn' : 'ok')}>{l.length} open · {kfmt(sum(l.map((x) => x.value)))}</span>
      </div>
      {l.length ? (
        <div className="tw">
          <table className="t cctab exl exw">
            <thead><tr><th>Warehouse</th><th>Exception</th><th>Items</th><th className="r">Value</th><th>Status</th><th /></tr></thead>
            <tbody>
              {l.map((x) => {
                const n = x.note, first = x.wh !== prev, top = x.items[0];
                prev = x.wh;
                return (
                  <tr key={x.id} data-ex={x.id} className={first ? 'exg1' : ''} data-tip={x.sev + ' severity · ' + x.trend} onClick={() => open(x)}>
                    <td data-l="Warehouse">{first ? <b>{x.wh}</b> : <span className="note">{x.wh}</span>}</td>
                    <td data-l="Exception">
                      <span className={'exsev ' + x.sev} aria-hidden="true" />
                      <span className="sr">{x.sev} severity: </span>
                      {x.title}
                    </td>
                    <td data-l="Items">
                      {top ? <>{plural(x.count, 'item')} <span className="note">· top: {top.id} {top.model}</span></> : <span className="note">Portfolio metric</span>}
                    </td>
                    <td className="r num" data-l="Value"><b>{kfmt(x.value)}</b></td>
                    <td data-l="Status">
                      {n ? (n.status === 'ack' ? <span className="chip ok">In hand by {n.ackBy}</span> : <span className="chip line">Notified {n.toLabel}</span>) : <span className="note">Open</span>}
                    </td>
                    <td className="nowrap exa" onClick={(e) => e.stopPropagation()}>
                      <button className="btn sm" onClick={() => open(x)}>{x.go ? 'Open Analytics' : 'View items'}</button>
                      {can('notify') && <> <button className="btn sm pri" onClick={() => setNotify(x.id)}>Notify owner</button></>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="pb"><div className="empty"><b>No exceptions</b>Nothing needs attention right now.</div></div>
      )}
      {viewing && <ExDrawer x={viewing} onClose={() => setView(null)} onNotify={() => { setView(null); setNotify(viewing.id); }} />}
      {notifying && <NotifyModal x={notifying} onClose={() => setNotify(null)} />}
    </section>
  );
}

/** The drill-down stays high level: warehouse, item, value. */
function ExDrawer({ x, onClose, onNotify }: { x: ExRow; onClose: () => void; onNotify: () => void }) {
  const open = canPage('product', 'case');
  return (
    <Drawer title={x.wh + ' · ' + x.title} sub="Exception by warehouse" onClose={onClose}
      foot={can('notify') ? <button className="btn pri" onClick={onNotify}>Notify owner</button> : undefined}>
      <p className="note" style={{ marginTop: 0 }}>{kfmt(x.value)} across {plural(x.count, 'item')}, highest value first.</p>
      <div className="tw">
        <table className="t static tight" id="exItems">
          <thead><tr><th>Warehouse</th><th>Item</th><th className="r">Value</th></tr></thead>
          <tbody>
            {x.items.slice(0, 40).map((i) => (
              <tr key={i.id}>
                <td>{x.wh}</td>
                <td>{open ? <a className="lnk" href={'#/product/' + i.id}>{i.id}</a> : i.id} {i.model}</td>
                <td className="r num">{kfmt(i.v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {x.items.length > 40 && <p className="note">Showing 40 of {x.items.length}.</p>}
    </Drawer>
  );
}

function NotifyModal({ x, onClose }: { x: ExRow; onClose: () => void }) {
  const [to, setTo] = useState(() => exOwner(x));
  const [sev, setSev] = useState<string>(x.sev);
  const [msg, setMsg] = useState('Please look at: ' + x.title.toLowerCase() + '.');
  const [err, setErr] = useState('');
  const send = async () => {
    const r = await sendNotification(x, to, sev, msg.trim());
    if (!r.ok) {
      if (r.error.code === 'validation_error') setErr(r.error.message);
      else toast(r.error.message);
      return;
    }
    onClose();
    toast('Notification sent to ' + r.output.to + '.', 4200);
  };
  return (
    <Modal title="Notify the owner" onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn pri" onClick={send}>Send notification</button></>}>
      <div className="callout info" style={{ marginBottom: 12 }}>
        <b>{x.wh} · {x.title}</b> · {kfmt(x.value)}{x.count ? ' · ' + x.count + ' items' : ''}
      </div>
      <div className="fld">
        <label htmlFor="nt-to">Recipient</label>
        <select id="nt-to" value={to} onChange={(e) => setTo(e.target.value)}>
          {notifyRecipients().map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
        </select>
        <div className="hint">Prefilled by exception type. You can change it.</div>
      </div>
      <div className="fld">
        <label htmlFor="nt-sev">Severity</label>
        <select id="nt-sev" value={sev} onChange={(e) => setSev(e.target.value)}>
          {['High', 'Medium', 'Low'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div className="fld">
        <label htmlFor="nt-msg">Message</label>
        <textarea id="nt-msg" maxLength={300} value={msg} onChange={(e) => setMsg(e.target.value)} />
        <div className="hint">Creates an Actions on me item and an audit entry. Do not enter personal data.</div>
        <div className="err" id="nt-err" hidden={!err}>{err}</div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Actions on me

export function Aome() {
  const l = aomeItems();
  const ack = async (id: string) => {
    const r = await acknowledge(id);
    if (r.ok) toast('Acknowledged. The sender sees it is in hand.');
    else toast(r.error.message);
  };
  return (
    <section className="panel" id="ccAome">
      <div className="ph">
        <div><h3>Actions on me</h3><div className="note">Everything whose next step is yours</div></div>
        <span className="sp" />
        <OpScopeChip />
        <span className={'chip ' + (l.length ? 'warn' : 'ok')}>{l.length}</span>
      </div>
      <div className="pb">
        {l.length ? (
          <>
            <ul className="aol">
              {l.slice(0, 8).map((i, n) => (
                <li key={n} className="aor">
                  <span className="aot"><b>{i.t}</b><span className="note">{i.d}</span></span>
                  {i.act === 'notifyAck' && i.arg ? (
                    can('ack') && <button className="btn sm pri" onClick={() => ack(i.arg!)}>{i.btn}</button>
                  ) : (
                    <a className="btn sm pri" href={'#/' + i.go}>{i.btn} →</a>
                  )}
                </li>
              ))}
            </ul>
            {l.length > 8 && <p className="note" style={{ margin: '8px 0 0' }}>{l.length - 8} more in the queues below.</p>}
          </>
        ) : (
          <div className="empty"><b>Nothing waits on you</b>New items appear here when a step becomes yours.</div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- handed off

export function Handed() {
  const openCase = useOpenCase();
  const l = handedRows(), { decider, rows: ap } = awaitingApproval();
  return (
    <div className="aogrid" id="ccHanded">
      <section className="panel">
        <div className="ph">
          <div><h3>Waiting for approval</h3><div className="note">Status only; {decider} decides</div></div>
          <span className="sp" />
          <OpScopeChip />
          <span className="chip line">{ap.length}</span>
        </div>
        {ap.length ? (
          <>
            <div className="tw">
              <table className="t cctab">
                <thead><tr><th>Return</th><th>Pathway</th><th>Waits on</th></tr></thead>
                <tbody>
                  {ap.slice(0, 6).map((c) => (
                    <tr key={c.id} {...rowProps(() => openCase(c.id))}>
                      <td data-l="Return"><b>{c.id}</b><div className="note">{c.location}</div></td>
                      <td data-l="Pathway">{c.plan}</td>
                      <td data-l="Waits on">{decider}{c.submitted ? ' · submitted' : ' · not yet submitted'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {ap.length > 6 && <p className="note" style={{ padding: '6px 14px', margin: 0 }}>{ap.length - 6} more</p>}
          </>
        ) : (
          <div className="pb"><div className="empty"><b>Nothing waiting</b>No decisions in this scope wait for approval.</div></div>
        )}
      </section>
      <section className="panel">
        <div className="ph">
          <div><h3>Handed off · awaiting outcome</h3><div className="note">Instructions with ERP, EAM or WMS; they carry out the work and report back</div></div>
          <span className="sp" />
          <span className="chip line" id="ccHandedN">{l.length}</span>
        </div>
        {l.length ? (
          <>
            <div className="tw">
              <table className="t cctab">
                <thead><tr><th>Return</th><th>Target system</th><th>External ref</th><th className="r">Age</th></tr></thead>
                <tbody>
                  {l.slice(0, 8).map((x) => (
                    <tr key={x.id} {...rowProps(() => openCase(x.id))}>
                      <td data-l="Return"><b>{x.id}</b><div className="note">{x.label}</div></td>
                      <td data-l="Target">{x.sys}</td>
                      <td className="mono" data-l="Ref">{x.ref ?? '—'}</td>
                      <td className="r num nowrap" data-l="Age">{x.age.toFixed(1)} d{x.over && <> <span className="chip warn">Overdue</span></>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {l.length > 8 && <p className="note" style={{ padding: '6px 14px', margin: 0 }}>{l.length - 8} more · oldest first</p>}
          </>
        ) : (
          <div className="pb"><div className="empty"><b>Nothing handed off</b>Approved instructions appear here until the system reports an outcome.</div></div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- outcomes to confirm

export function Outcomes() {
  const openCase = useOpenCase();
  const { rows: l, done } = outcomesToConfirm();
  return (
    <section className="panel" id="ccOutcomes">
      <div className="ph">
        <div><h3>Outcomes to confirm</h3><div className="note">Enterprise systems reported the outcome; Finance confirms the economic result.</div></div>
        <span className="sp" />
        <span className={'chip ' + (l.length ? 'warn' : 'ok')}>{l.length} waiting</span>
      </div>
      {l.length ? (
        <div className="tw">
          <table className="t cctab">
            <thead><tr><th>Return</th><th>Asset</th><th>Route</th><th className="r">Predicted net</th><th /></tr></thead>
            <tbody>
              {l.map((c) => (
                <tr key={c.id} {...rowProps(() => openCase(c.id))}>
                  <td data-l="Return"><b>{c.id}</b></td>
                  <td data-l="Asset">{c.product} <span className="note">{c.assetId}</span></td>
                  <td data-l="Route">{c.plan}</td>
                  <td className="r num" data-l="Predicted">{c.net == null ? '—' : money(c.net)}</td>
                  <td><span className="btn sm">Open to confirm</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="pb">
          <div className="empty"><b>Nothing to confirm right now</b>Cases appear here when enterprise systems report an outcome. {done} outcome{done === 1 ? '' : 's'} confirmed this session.</div>
        </div>
      )}
    </section>
  );
}

/** Senior view: the operational queues, read-only, only when asked for. */
export function OpsReadOnly({ sc }: { sc: CcScope }) {
  const openCase = useOpenCase();
  const net = (c: CcCase) => (c.recommendation ? c.recommendation.net : 0);
  const ap = sc.all.filter((c) => c._st === 'approval').sort((a, b) => net(b) - net(a));
  return (
    <div className="aogrid" id="ccOpsRO">
      <section className="panel">
        <div className="ph"><div><h3>Awaiting approval</h3><div className="note">Read-only</div></div><span className="sp" /><span className="chip line">{ap.length}</span></div>
        <div className="tw">
          <table className="t cctab">
            <tbody>
              {ap.slice(0, 6).map((c) => (
                <tr key={c.id} {...rowProps(() => openCase(c.id))}>
                  <td><b>{c.id}</b></td>
                  <td>{c.recommendation ? c.recommendation.plan : '—'}</td>
                  <td className="r num">{kfmt(net(c))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <Outcomes />
    </div>
  );
}

// ---------------------------------------------------------------- Approvals inbox

function ReqSummary({ r }: { r: AccessRequest }) {
  if (r.kind === 'tenant') return <><b>Access to {r.tenant}</b><div className="note">{r.reason}</div></>;
  const v = r.server!;
  return (
    <>
      <b>{v.name}</b> <span className={'chip ' + (v.access === 'write' ? 'dk' : 'ok')}>{v.access === 'write' ? 'Read and write' : 'Read only'}</span>
      <div className="note">{v.owner} · {v.purpose}</div>
      <div className="note">Tools: <span className="mono">{v.tools.join(', ')}</span> · Data: {v.data}</div>
    </>
  );
}
const REQ_ST = { pending: <span className="chip warn">Pending review</span>, approved: <span className="chip ok">Approved</span>, declined: <span className="chip bad">Declined</span> };

function ReqRow({ r, onDecide }: { r: AccessRequest; onDecide: (dec: 'approve' | 'decline') => void }) {
  return (
    <div className="rqrow" data-req={r.id}>
      <div className="rqm">
        <div className="row" style={{ gap: 6 }}><span className="chip line">{r.kindLabel}</span>{REQ_ST[r.status]}<span className="note num">{r.id}</span></div>
        <div style={{ marginTop: 6 }}><ReqSummary r={r} /></div>
        <div className="note" style={{ marginTop: 4 }}>
          Requested by {r.by} · {fmtDateYear(r.at)}
          {r.decidedBy && <> · {r.status === 'approved' ? 'approved' : 'declined'} by {r.decidedBy} on {fmtDateYear(r.decidedAt!)}{r.note ? ': ' + r.note : ''}</>}
        </div>
      </div>
      {r.canDecide && (
        <div className="rqa">
          <button className="btn sm pri" onClick={() => onDecide('approve')}>{r.kind === 'tenant' ? 'Approve access' : 'Approve proposal'}</button>
          <button className="btn sm" onClick={() => onDecide('decline')}>Decline</button>
        </div>
      )}
    </div>
  );
}

function DecideModal({ r, dec, onClose }: { r: AccessRequest; dec: 'approve' | 'decline'; onClose: () => void }) {
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const ok = async () => {
    const res = await decideRequest(r.id, dec, note.trim());
    if (!res.ok) {
      if (res.error.code === 'validation_error') setErr(res.error.message);
      else toast(res.error.message);
      return;
    }
    onClose();
    toast(r.id + ' ' + res.output.status + '.' + (r.kind === 'tenant' && res.output.status === 'approved' ? ' ' + r.by + ' can now open ' + r.tenant + '.' : ''), 4200);
  };
  return (
    <Modal title={(dec === 'approve' ? 'Approve ' : 'Decline ') + r.kindLabel.toLowerCase() + ' ' + r.id} onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Cancel</button><button className={'btn ' + (dec === 'approve' ? 'pri' : 'danger')} onClick={ok}>{dec === 'approve' ? 'Approve' : 'Decline'}</button></>}>
      <div className="callout info" style={{ marginBottom: 12 }}>
        <ReqSummary r={r} />
        <div className="note" style={{ marginTop: 6 }}>Requested by {r.by} on {fmtDateYear(r.at)}</div>
      </div>
      <div className="fld">
        <label htmlFor="rq-note">Note {dec === 'decline' ? <span className="muted">(required)</span> : <span className="muted">(optional)</span>}</label>
        <textarea id="rq-note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder={dec === 'decline' ? 'Say what would change your decision.' : 'Anything the requester should know.'} />
        <div className="hint">Recorded in the audit log. Do not enter personal data.</div>
        <div className="err" id="rq-err" hidden={!err}>{err}</div>
      </div>
      {r.kind === 'tenant' && dec === 'approve' && <p className="note" style={{ margin: 0 }}>{r.by} will see {r.tenant} cases for the rest of this session.</p>}
      {r.kind === 'mcp' && dec === 'approve' && <p className="note" style={{ margin: 0 }}>The server joins the MCP client list as approved. Connecting it is a separate step.</p>}
    </Modal>
  );
}

export function Inbox({ onPick }: { onPick: (arg: string) => void }) {
  const l = inboxRequests(), dec = can('approve.decisions') ? decisionsAwaiting() : 0, scope = inboxScope();
  const [deciding, setDeciding] = useState<{ r: AccessRequest; dec: 'approve' | 'decline' } | null>(null);
  return (
    <section className="panel" id="ccApprovals">
      <div className="ph">
        <div>
          <h3>Approvals inbox</h3>
          <div className="note">{scope ? 'Delegated to you by Admin: ' + (scope.join(', ') || 'nothing at the moment') : 'Every scope, as Admin'}</div>
        </div>
        <span className="sp" />
        {dec > 0 && <button className="btn sm" onClick={() => onPick('stage:approval')}>{dec} decision{dec > 1 ? 's' : ''} await approval</button>}
      </div>
      <div className="pb">
        {l.length ? l.map((r) => <ReqRow key={r.id} r={r} onDecide={(d) => setDeciding({ r, dec: d })} />)
          : <div className="empty"><b>Nothing waiting for you</b>Tenant access requests and MCP server proposals appear here.</div>}
      </div>
      {deciding && <DecideModal r={deciding.r} dec={deciding.dec} onClose={() => setDeciding(null)} />}
    </section>
  );
}

/** Submitted decisions as approval cards. Approve and Decline open the case, where the approval card lives. */
export function ApprovalCards() {
  const openCase = useOpenCase();
  const q = approvalCards(), lim = approvalLimit();
  const [batch, setBatch] = useState(false);
  if (!q.length) return null;
  return (
    <section className="sect" id="afApprCards">
      <div className="sh">
        <h2>Approval cards</h2>
        <span className="note">{q.length} submitted · by value, then deadline · each approved separately{lim !== Infinity ? ' · your limit ' + money(lim) : ''}</span>
        <button className="btn sm" onClick={() => setBatch(true)}>Review all {q.length} in turn</button>
      </div>
      <div className="afapq">
        {q.slice(0, 8).map((x) => (
          <article key={x.id} className="afc afc-approval">
            <header className="afch">
              <div>
                <h4>{x.id} · {x.plan}</h4>
                <div className="note">{x.model} · {x.owner} · {x.timing} · submitted by {x.submittedBy}</div>
              </div>
              <span className="afnet num">{money(x.net)}</span>
            </header>
            <p className="note">{x.risks.length ? 'Pre-approval check: ' + x.risks.join(' · ') : 'Pre-approval check: nothing to flag.'}</p>
            {Math.abs(x.net) > lim && <p className="note neg">Above your approval limit: it escalates to Admin.</p>}
            <footer className="afcf">
              {can('approve') && (
                <>
                  <button className="btn sm pri" onClick={() => openCase(x.id)}>Approve…</button>
                  <button className="btn sm" onClick={() => openCase(x.id)}>Decline…</button>
                </>
              )}
              <a className="btn sm" href={'#/product/' + x.id}>Open</a>
            </footer>
          </article>
        ))}
      </div>
      {batch && (
        <Modal title={'Review ' + q.length + ' approvals'} wide onClose={() => setBatch(false)} foot={<button className="btn" onClick={() => setBatch(false)}>Close</button>}>
          <p className="ink2" style={{ marginTop: 0 }}>
            Every item is listed with the instructions it would send. Each one is approved on its own, within your limit; there is no unlisted “approve all”.
          </p>
          {q.map((x) => (
            <div key={x.id} className="afbatch">
              <b>{x.id} · {x.plan} · <span className="num">{money(x.net)}</span></b>
              <div className="note">{x.steps.join(' · ')}</div>
              {x.risks.length > 0 && <div className="note">Check: {x.risks.join(' · ')}</div>}
              <button className="btn sm pri" onClick={() => openCase(x.id)}>Approve…</button>
            </div>
          ))}
        </Modal>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- actions to be prioritised

const VIEWS: [string, string][] = [['', 'All opportunities'], ['stage:approval', 'Awaiting approval'], ['stage:need', 'Needs evidence'], ['stage:reeval', 'Re-evaluate']];
const PRI: Record<string, string> = { High: 'bad', Medium: 'warn', Low: 'line' };

export function ActionsTable({ sc, onPick }: { sc: CcScope; onPick: (arg: string) => void }) {
  const openCase = useOpenCase();
  const f = ccFilters(), l = oppRows(sc), top = l.slice(0, 10);
  return (
    <section className="panel" id="ccActions" style={{ marginTop: 14 }}>
      <div className="ph">
        <div><h3>Actions to be prioritised</h3><div className="note">Ranked by predicted value and urgency. Select a row to investigate or act.</div></div>
      </div>
      <div className="filters">
        <div className="seg" role="group" aria-label="View">
          {VIEWS.map(([k, label]) => (
            <button key={label} aria-pressed={k === (f.stage ? 'stage:' + f.stage : '')} onClick={() => onPick(k || 'stage:')}>{label}</button>
          ))}
        </div>
        <input type="search" placeholder="Search opportunities" value={f.q} aria-label="Search opportunities" onChange={(e) => setCcFilters({ q: e.target.value })} />
        <span className="grow" />
        <span className="chip line">{l.length} opportunities</span>
      </div>
      <div id="ccTab">
        <div className="tw">
          <table className="t cctab">
            <thead>
              <tr>
                <th>#</th><th>Return</th><th>Asset</th><th className="cctr">Trigger</th><th>Recommended action</th><th className="r">Predicted value</th>
                <th>Deadline</th><th>Confidence</th><th className="cctr">Constraints</th><th>Priority</th><th>Status</th><th />
              </tr>
            </thead>
            <tbody>
              {top.length ? top.map((c, i) => {
                const o = oppRow(c, sc), r = c.recommendation;
                return (
                  <tr key={c.id} {...rowProps(() => openCase(c.id))}>
                    <td data-l="#">{i + 1}</td>
                    <td data-l="Return" className="nowrap"><b>{c.id}</b></td>
                    <td data-l="Asset">
                      <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                        <span className="thumb"><Icon name={clsIcon(c.cls)} /></span>
                        <span className="nowrap">
                          {c.product}{c.qty > 1 && <> <span className="note">×{c.qty}</span></>}
                          <div className="note num">{c.assetId}</div>
                        </span>
                      </div>
                    </td>
                    <td className="cctr" data-l="Trigger">{o.trigger}</td>
                    <td data-l="Action">{o.action}</td>
                    <td className="r num" data-l="Value">
                      <b>{r ? money(r.net) : '~' + money(c._val)}</b>
                      {!r && <div className="note">estimate</div>}
                    </td>
                    <td className="num nowrap" data-l="Deadline">{o.deadline}<div className="note">{o.left <= 0 ? 'overdue' : o.left + ' d left'}</div></td>
                    <td data-l="Confidence">
                      {o.conf == null ? <span className="muted">—</span> : (
                        <span className="ccconf">
                          <span className="bar"><i style={{ width: o.conf + '%', background: o.conf < 70 ? '#D4A800' : 'var(--ok)' }} /></span>
                          <b className="num">{o.conf}%</b>
                        </span>
                      )}
                    </td>
                    <td className="cctr" data-l="Constraints">{o.cons}</td>
                    <td data-l="Priority"><span className={'chip ' + (PRI[c._pri ?? ''] || 'line')}>{c._pri || '—'}</span></td>
                    <td data-l="Status"><StageChip c={c} /></td>
                    <td><span className="btn sm">{o.btn}</span></td>
                  </tr>
                );
              }) : (
                <tr><td colSpan={12}><div className="empty"><b>No assets match</b>Clear a filter or search to see the full list.</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="filters" style={{ borderTop: '1px solid var(--line2)', borderBottom: 0, justifyContent: 'space-between' }}>
          <span className="note">Showing {top.length} of {l.length}, ranked by predicted value and urgency.</span>
          <a className="btn sm" href="#/product">Open all returned assets</a>
        </div>
      </div>
    </section>
  );
}


