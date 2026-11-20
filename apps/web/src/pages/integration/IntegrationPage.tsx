/**
 * Connection Fabric (#/integration/<tab>): the page frame with breadcrumb and tabs, and the dispatcher for Overview,
 * Workflow Studio (owned by src/pages/workflows), Source Map, Source Tables, Canonical Models, Event Streams,
 * Conflict Queue, Manual Import and Monitor. Drawers and dialogs shared by several tabs live here.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBackend } from '../../api/useBackend';
import {
  available, deleteSource, followSync, intKids, intSub, mappings, notOnServer, openConflictCount, openDecisionCount, reconnectSource,
  rotateCredentials, source, srcTypes, syncSource, typeOf, undoActions, wfUsing,
} from '../../api/integration';
import { can, canPage } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import type { PageProps } from '../registry';
import { WorkflowStudio } from '../workflows/WorkflowStudio';
import { ConnectFlow, type CxStart } from './ConnectFlow';
import { FlowDiagram } from './FlowDiagram';
import { Monitor } from './Monitor';
import { Overview } from './FabricOverview';
import { Conflicts, EventDrawer, Events, Import, Models } from './Records';
import { SourceDrawer, type DrawerRef } from './SourceDrawer';
import { SourceMap } from './SourceMap';
import { Tables, TablesTiles } from './SourceTables';
import { ActToasts, canMgr, FrIt, IntCtx, NOMGR, runTest, toastAct, useTick, Vlogo, type IntUI } from './ui';

type Dialog =
  | { k: 'guide' } | { k: 'new' } | { k: 'disc'; id: string } | { k: 'del'; id: string } | { k: 'rot'; id: string } | { k: 'cx'; start: CxStart } | null;

export function IntegrationPage({ route, query }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const [drawer, setDrawer] = useState<DrawerRef | null>(null);
  const [drawerKey, setDrawerKey] = useState(0);
  const [dlg, setDlg] = useState<Dialog>(null);
  const [evId, setEvId] = useState<string | null>(null);
  useTick(1000);

  const T = intKids().filter((t) => canPage('integration', t[0]));
  const tab = T.some((t) => t[0] === route.a) ? route.a! : T.some((t) => t[0] === 'overview') && !route.a ? 'overview' : T[0]?.[0] ?? 'overview';
  const cur = T.find((t) => t[0] === tab) ?? T[0];

  useEffect(() => {
    document.title = 'Connection Fabric · ' + (cur?.[1] ?? '') + ' · Circularity Decision Workbench';
  }, [cur]);

  const ui: IntUI = useMemo(() => {
    const open = (r: DrawerRef) => { setDrawer(r); setDrawerKey((k) => k + 1); };
    const reconnect = async (id: string) => {
      if (!canMgr()) return toast(NOMGR);
      const r = await reconnectSource(id);
      if (!r.ok) return toast(r.error.message);
      const s = source(id);
      if (s) toast(s.name + ' is live again. Predictions no longer carry a stale-feed warning.');
    };
    return {
      openSource: (id, t) => open({ mode: 'edit', id, tab: t ?? 'conn' }),
      addSource: (cat) => { if (!canMgr()) return toast(NOMGR); open({ mode: 'new', id: '', tab: 'conn', cat }); },
      sync: async (id) => {
        if (!canMgr()) return toast(NOMGR);
        const s = source(id);
        if (s?.paused) return toast(s.name + ' is paused. Resume it to sync.');
        const r = await syncSource(id);
        if (!r.ok) { if (r.error.code !== 'duplicate') toast(r.error.message); return; }
        // report its result as the demo does when it finishes
        const name = s?.name ?? id;
        followSync(id, (x) => {
          if (!x.ok) toast(name + ': sync failed, ' + x.reason, 4200);
          else toast(name + ' synced: ' + x.rows.toLocaleString('en-US') + ' records updated.');
        });
      },
      pause: (id) => {
        if (!canMgr()) return toast(NOMGR);
        const s = source(id);
        if (!s) return;
        toast(notOnServer(s.paused ? 'Resuming a source' : 'Pausing a source'));
      },
      disconnect: (id) => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'disc', id }); },
      reconnect,
      remove: (id) => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'del', id }); },
      rotate: (id) => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'rot', id }); },
      connect: (catId) => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'cx', start: { mode: 'new', cat: catId } }); },
      reauth: (id) => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'cx', start: { mode: 'reauth', src: id } }); },
      newIntegration: () => { if (!canMgr()) return toast(NOMGR); setDlg({ k: 'new' }); },
      test: (id) => { const s = source(id); if (!s) return; if (!canMgr()) return toast(NOMGR); runTest(s); },
      openEvent: (id) => setEvId(id),
      go: (p) => { setDrawer(null); nav('/' + p); },
    };
  }, [nav]);

  if (tab === 'studio' && route.b) {
    return (
      <IntCtx.Provider value={ui}>
        <WorkflowStudio workflowId={route.b} query={query} />
      </IntCtx.Provider>
    );
  }

  const open = openConflictCount();
  const right = (
    <>
      <button className="btn" onClick={() => setDlg({ k: 'guide' })}><Icon name="book" /> Integration guide</button>
      {tab === 'overview' && canMgr() && <button className="btn pri" onClick={ui.newIntegration}><Icon name="plus" /> New integration</button>}
      {tab === 'map' && canMgr() && <button className="btn pri" onClick={() => ui.addSource('')}><Icon name="plus" /> Add source</button>}
    </>
  );
  let body: ReactNode;
  switch (tab) {
    case 'overview': body = <Overview />; break;
    case 'studio': body = <WorkflowStudio workflowId={null} query={query} />; break;
    case 'map': body = <SourceMap />; break;
    case 'tables': body = <><TablesTiles /><Tables /></>; break;
    case 'models': body = <Models />; break;
    case 'events': body = <Events onOpen={setEvId} />; break;
    case 'conflicts': body = <Conflicts />; break;
    case 'import': body = <Import />; break;
    default: body = <Monitor />;
  }

  return (
    <IntCtx.Provider value={ui}>
      <nav className="frbc" aria-label="Breadcrumb">
        <span>Integration</span><Icon name="chevR" /><span>Connection Fabric</span><Icon name="chevR" /><b>{cur?.[1]}</b>
      </nav>
      <div className="phead frph">
        <div><h1>Connection Fabric</h1><p>{intSub(tab)}</p></div>
        <div className="row">{right}</div>
      </div>
      <div className="tabs frtabs2" role="tablist">
        {T.map((t) => (
          <button key={t[0]} role="tab" aria-selected={tab === t[0]} onClick={() => nav('/integration/' + t[0])}>
            {t[0] === 'conflicts' ? 'Conflict Queue (' + open + ')' : t[1]}
          </button>
        ))}
      </div>
      {!canMgr() && (
        <div className="callout info" style={{ marginBottom: 14 }}>
          <b>Read-only view.</b> Only the Developer or Admin changes connections, tables, conflicts and workflows.
          {can('comment') && canPage('integration', 'map') ? ' You can comment on a source: open it and choose the Comments tab.' : ''}
        </div>
      )}
      {body}
      {drawer && <SourceDrawer key={drawerKey} at={drawer} onClose={() => setDrawer(null)} onOpen={(r) => { setDrawer(r); setDrawerKey((k) => k + 1); }} />}
      {evId && <EventDrawer id={evId} onClose={() => setEvId(null)} />}
      {dlg?.k === 'guide' && <GuideModal onClose={() => setDlg(null)} />}
      {dlg?.k === 'new' && <NewIntegration onClose={() => setDlg(null)} onPick={(id) => setDlg({ k: 'cx', start: { mode: 'new', cat: id } })} onBlank={() => { setDlg(null); ui.addSource(''); }} />}
      {dlg?.k === 'disc' && <DisconnectModal id={dlg.id} onClose={() => setDlg(null)} />}
      {dlg?.k === 'del' && <DeleteModal id={dlg.id} onClose={() => setDlg(null)} onDone={() => setDrawer((d) => (d && d.id === dlg.id ? null : d))} />}
      {dlg?.k === 'rot' && <RotateModal id={dlg.id} onClose={() => setDlg(null)} />}
      {dlg?.k === 'cx' && <ConnectFlow start={dlg.start} onClose={() => setDlg(null)} />}
      <ActToasts />
    </IntCtx.Provider>
  );
}

function GuideModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Integration guide" wide onClose={onClose} foot={<button className="btn" onClick={onClose}>Close</button>}>
      <p className="ink2" style={{ marginTop: 0 }}>
        Enterprise systems keep owning their transactions. Circularity reads their evidence through one adapter per system, maps it into versioned canonical models, decides with a person in the loop, and sends the approved instruction back to the system that does the work.
      </p>
      <ol className="frguide">
        <li><b>Connect</b> a system from the catalogue: choose how it authenticates, grant read scopes, test the connection.</li>
        <li><b>Map</b> its fields into the canonical model. The agent suggests mappings; you accept them.</li>
        <li><b>Run</b> its ingest workflow on a schedule or on events; failures go to the error handler with a reason.</li>
        <li><b>Monitor</b> freshness, success and failed records against the SLA, per source and per workflow.</li>
      </ol>
      <h3>How data flows</h3>
      <FlowDiagram />
    </Modal>
  );
}

function NewIntegration({ onClose, onPick, onBlank }: { onClose: () => void; onPick: (id: string) => void; onBlank: () => void }) {
  return (
    <Modal title="New integration" wide onClose={onClose} foot={<button className="btn" onClick={onClose}>Cancel</button>}>
      <p className="note" style={{ marginTop: 0 }}>Choose a system from the catalogue, or set up any other system by hand.</p>
      <div className="frpick">
        {available().map((c) => (
          <button key={c.id} className="frrec frpk" onClick={() => onPick(c.id)}>
            <Vlogo vendor={c.vendor} />
            <span><b>{c.vendor}</b><span className="note">{typeOf(c.type).label} · {c.desc}</span></span>
          </button>
        ))}
        <button className="frrec frpk" onClick={onBlank}>
          <FrIt ic="plus" h="neutral" cls="sm" />
          <span><b>Another system</b><span className="note">Set up a connection by hand</span></span>
        </button>
      </div>
    </Modal>
  );
}

function DisconnectModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [t, setT] = useState('');
  const s = source(id);
  if (!s) return null;
  const use = wfUsing(id), dec = openDecisionCount(), mp = mappings(id).length, T = srcTypes()[s.type];
  const ok = () => {
    if (t.trim() !== s.vendor) return;
    onClose();
    toast(notOnServer('Disconnecting a source'));
  };
  return (
    <Modal title={'Disconnect ' + s.vendor + '?'} onClose={onClose} foot={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn danger" id="frDiscOk" disabled={t.trim() !== s.vendor} onClick={ok}>Disconnect</button>
    </>}>
      <p style={{ marginTop: 0 }}>Circularity stops reading from <b>{s.vendor}</b> ({s.name}). The system itself is not changed, and the connection settings are kept so you can reconnect.</p>
      <div className="callout bad">
        <b>What depends on it</b>
        <ul className="frdep">
          <li>{use.length} workflow{use.length === 1 ? '' : 's'}{use.length ? ': ' + use.slice(0, 4).join(', ') + (use.length > 4 ? ' and ' + (use.length - 4) + ' more' : '') : ''}</li>
          <li>{mp} field mapping{mp === 1 ? '' : 's'} into {T ? T.target : 'its model'}</li>
          <li>{s.step.includes(1) ? dec + ' open decision' + (dec === 1 ? '' : 's') + ' read evidence from it and will say it is missing' : 'No open decision reads evidence from it'}</li>
        </ul>
      </div>
      <label htmlFor="frDiscT" style={{ display: 'block', marginTop: 12 }}>Type <b>{s.vendor}</b> to confirm</label>
      <input id="frDiscT" className="sel" style={{ width: '100%' }} autoComplete="off" value={t} onChange={(e) => setT(e.target.value)} />
    </Modal>
  );
}

function DeleteModal({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const [t, setT] = useState('');
  const s = source(id);
  if (!s) return null;
  const use = wfUsing(id), mp = mappings(id).length;
  const ok = async () => {
    const r = await deleteSource(id);
    if (!r.ok) return toast(r.error.message);
    onClose();
    onDone();
    toastAct(r.output.name + ' (' + r.output.vendor + ') deleted.', 'Undo', () => undoActions([r.seq!]));
  };
  return (
    <Modal title={'Delete ' + s.name + '?'} onClose={onClose} foot={<>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn danger" id="delBtn" disabled={t.trim().toLowerCase() !== s.name.toLowerCase()} onClick={ok}>Delete source</button>
    </>}>
      <p style={{ marginTop: 0 }}>This disconnects <b>{s.vendor}</b> from Circularity. Events already received stay in the stream and the audit trail.</p>
      <ul className="impact">
        <li>{mp} field mapping{mp === 1 ? '' : 's'} will be removed.</li>
        <li>{use.length ? <><b>{use.length} workflow{use.length > 1 ? 's' : ''} use this source</b> and will fail validation: {use.slice(0, 4).join(', ')}{use.length > 4 ? ' and ' + (use.length - 4) + ' more' : ''}.</> : 'No workflow uses this source.'}</li>
        {!!s.write.length && <li>Approved instructions can no longer be sent to {s.name}.</li>}
      </ul>
      <div className="fld"><label htmlFor="delType">Type <b>{s.name}</b> to confirm</label><input id="delType" autoComplete="off" value={t} onChange={(e) => setT(e.target.value)} /></div>
    </Modal>
  );
}

function RotateModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [secret, setSecret] = useState(''), [days, setDays] = useState('180'), [err, setErr] = useState('');
  const s = source(id);
  if (!s) return null;
  const ok = async () => {
    if (secret.length < 8) return setErr('Enter at least 8 characters.');
    const r = await rotateCredentials(id, +days);
    if (!r.ok) return setErr(r.error.message);
    onClose();
    if (r.output.stale) {
      const x = await reconnectSource(id);
      if (!x.ok) return toast(x.error.message);
      return toast(s.name + ' is live again. Predictions no longer carry a stale-feed warning.');
    }
    toast('Credentials updated for ' + s.name + '.');
  };
  return (
    <Modal title={'Rotate credentials for ' + s.name} onClose={onClose} foot={<>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn pri" onClick={ok}>Save credentials</button>
    </>}>
      <p className="note" style={{ marginTop: 0 }}>{s.vendor} · {s.auth}. The new secret is written to the vault. It is never shown again.</p>
      <div className="fld">
        <label htmlFor="rotSecret">New client secret or API key</label>
        <input id="rotSecret" type="password" autoComplete="new-password" placeholder="Paste the new secret" value={secret} onChange={(e) => setSecret(e.target.value)} />
        <div className="err" id="rotErr">{err}</div>
      </div>
      <div className="fld">
        <label htmlFor="rotDays">Expires after</label>
        <select id="rotDays" value={days} onChange={(e) => setDays(e.target.value)}>
          <option value="90">90 days</option><option value="180">180 days</option><option value="365">365 days</option>
        </select>
      </div>
    </Modal>
  );
}

