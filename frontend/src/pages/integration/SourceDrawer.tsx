/* The source drawer (the demo's sdOpen / sdRender with the Connection Fabric tabs): Overview, Configuration, Data Mapping,
   Sync & History, Security, Comments for a connected system; Connection, Operations, Field mapping for a new one. */
import { Suspense, useMemo, useState, type ReactNode } from 'react';
import { fmtDateYear } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import {
  addComment, authOpts, hashId, canon, canonPrefix, cfgDefaults, commentsOf, connMethods, credDays, failedRecords, isoTime, mappings,
  mappingVersions, previewMapping, revertMapping, type MapPreview, saveSource, series, source, sources, srcAgeText, srcFailing, srcFresh, srcTypes, successRate, testDraft, wfUsing, type Draft, type Source,
} from '../../api/integration';
import { useOrgUnits } from '../../api/orgs';
import { can } from '../../api/session';
import { Drawer } from '../../components/Overlay';
import { Icon } from '../../components/Icon';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { Delta, pctDelta } from '../../components/kit/Delta';
import { IconTile } from '../../components/kit/IconTile';
import { Segmented } from '../../components/kit/Segmented';
import { StatusChip } from '../../components/kit/StatusChip';
import { VendorLogo } from '../../components/kit/VendorLogo';
import { TestSteps } from './ConnectionTests';
import { canMgr, NOMGR, useInt } from './FabricContext';
import { fmtN, plural, sum, when } from './fabricFormat';
import { FabricStatus } from './FabricStatus';

export interface DrawerRef { mode: 'edit' | 'new'; id: string; tab: string; cat?: string }
type Errs = Record<string, string>;
type Test = { state?: 'running'; ok?: boolean; msg?: string } | null;

const draftOf = (s: Source): Draft => ({
  type: s.type, name: s.name, vendor: s.vendor, ver: s.ver, env: s.env, url: s.url, method: s.method, cfg: { ...s.cfg }, interval: s.interval, auth: s.auth, owner: s.owner,
});
function newDraft(cat: string): Draft {
  const T = srcTypes(), type = Object.keys(T).find((k) => T[k].cat === (cat || 'internal')) || 'crm', t = T[type];
  return { type, name: t.label, vendor: t.vendors[0], ver: '', env: 'Production', url: '', method: 'api', cfg: cfgDefaults('api'), interval: 0, auth: connMethods().api.auth, owner: '' };
}
const CONN_KEY = (k: string) => ['name', 'url', 'auth', 'interval'].includes(k) || /^c_/.test(k);

function validate(mode: string, id: string, d: Draft, maps: string[][], ops: { read: string[]; write: string[] }): Errs {
  const c = d.cfg as Record<string, string | number | undefined>, e: Errs = {}, s = mode === 'edit' ? source(id) : undefined;
  const off = !!s && s.status === 'unavailable' && /^Pending/.test(d.auth);
  if (!d.name.trim()) e.name = 'Enter a display name.';
  else if (sources().some((x) => x.id !== id && x.name.toLowerCase() === d.name.trim().toLowerCase() && x.vendor === d.vendor)) e.name = 'A source with this name and vendor already exists.';
  if (!off) {
    const https = (v: unknown) => /^https?:\/\/[^\s/]+(\/\S*)?$/i.test(String(v || '').trim());
    if (/^Pending/.test(d.auth)) e.auth = 'Choose an authentication method.';
    if (connMethods()[d.method].url && !https(d.url)) e.url = 'Enter a full URL starting with https://.';
    if (d.method === 'jdbc') {
      if (!/^[\w.-]+$/.test(String(c.host || '').trim())) e.c_host = 'Enter the database host name.';
      const p = +(c.port ?? 0);
      if (!(p >= 1 && p <= 65535)) e.c_port = 'Enter a port from 1 to 65535.';
      if (!String(c.database || '').trim()) e.c_database = 'Enter the database or service name.';
    }
    if (d.method === 'delta') {
      if (!https(c.endpoint)) e.c_endpoint = 'Enter the https:// sharing endpoint.';
      if (!String(c.share || '').trim()) e.c_share = 'Enter the share name.';
    }
    if (d.method === 'file') {
      const m = +(c.maxmb ?? 0);
      if (!(m >= 1 && m <= 1024)) e.c_maxmb = 'The limit is 1 GB (1024 MB) per file.';
      if (c.delivery === 'SFTP drop' && !/^(\/|sftp:\/\/)\S+/.test(String(c.path || '').trim())) e.c_path = 'Enter the SFTP path, for example /outbound/file.csv.';
    }
    if (d.method === 'api' && !c.spec) e.c_spec = 'Choose REST or OData.';
    if (connMethods()[d.method].sched) {
      const lo = d.method === 'api' ? 0 : 1;
      if (!(d.interval !== '' && d.interval >= lo && d.interval <= 1440)) e.interval = 'Enter ' + lo + ' to 1440 minutes.';
    }
  }
  if (!off && !ops.read.map((x) => x.trim()).filter(Boolean).length) e.ops = 'Add at least one read operation.';
  if (ops.read.concat(ops.write).some((x) => x.trim() && !/^(GET|POST|PUT|PATCH|DELETE|IMPORT|SELECT|EXTRACT|READ|SUBSCRIBE)\s+\S+/i.test(x.trim())))
    e.ops = 'Each operation starts with a verb, for example GET /assets or SELECT * FROM table.';
  const seen = new Set<string>();
  maps.forEach((m, i) => {
    if (!m[0].trim()) e['m' + i + '_0'] = 'x';
    if (!m[2].trim()) e['m' + i + '_2'] = 'x';
    if (m[2].trim() && seen.has(m[2].trim() + '|' + m[0].trim())) e['m' + i + '_2'] = 'x';
    seen.add(m[2].trim() + '|' + m[0].trim());
  });
  if (Object.keys(e).some((k) => /^m\d/.test(k))) e.maps = 'Every mapping row needs a source field and a canonical field, and rows cannot repeat.';
  return e;
}

export function SourceDrawer({ at, onClose, onOpen }: { at: DrawerRef; onClose: () => void; onOpen: (r: DrawerRef) => void }) {
  useBackend();
  const ui = useInt();
  const mode = at.mode, s = mode === 'edit' ? source(at.id) : undefined;
  const [tab, setTab] = useState(at.tab);
  const [d, setD] = useState<Draft>(() => (s ? draftOf(s) : newDraft(at.cat ?? '')));
  const [maps, setMaps] = useState<string[][]>(() => (s ? mappings(s.id).map((r) => r.slice()) : []));
  const [ops, setOps] = useState(() => ({ read: s ? s.read.slice() : [], write: s ? s.write.slice() : [] }));
  const [errs, setErrs] = useState<Errs>({});
  // the org unit the source belongs to ('': shared by every org); sent only when changed (source.update org_unit_id)
  const savedOrg = s?.org_unit_id ?? '';
  const [org, setOrg] = useState(savedOrg);
  const [dirty, setDirty] = useState(mode === 'new');
  const [test, setTest] = useState<Test>(null);
  const [use, setUse] = useState('30');
  const action = useAction();
  const mgr = canMgr();

  if (mode === 'edit' && !s) return null;
  const touch = () => setDirty(true);
  const clearErr = (...k: string[]) => setErrs((e) => { const n = { ...e }; k.forEach((x) => delete n[x]); return n; });

  const setField = (k: keyof Draft | 'type' | 'method', v: string) => {
    const T = srcTypes(), CM = connMethods();
    if (k === 'type') {
      const nk = Object.keys(T).find((x) => T[x].label === v)!, pt = T[d.type];
      setD({ ...d, type: nk, name: d.name === pt.label ? T[nk].label : d.name, vendor: T[nk].vendors[0] });
    } else if (k === 'method') {
      const nk = Object.keys(CM).find((x) => CM[x].label === v)!, m = CM[nk];
      setD({ ...d, method: nk, cfg: cfgDefaults(nk), auth: m.auth, interval: m.sched ? (nk === 'api' ? 0 : d.interval || 15) : 0 });
      setErrs({});
    } else if (k === 'interval') setD({ ...d, interval: v === '' ? '' : +v });
    else setD({ ...d, [k]: v });
    clearErr(k);
    touch();
  };

  async function save() {
    if (!mgr) return toast(NOMGR);
    const e = validate(mode, at.id, d, maps, ops);
    if (Object.keys(e).length) {
      setErrs(e);
      const n = Object.keys(e).filter((k) => k !== 'maps' && k !== 'ops' && !/^m\d/.test(k)).length + (e.maps ? 1 : 0) + (e.ops ? 1 : 0);
      setTab(Object.keys(e).some(CONN_KEY) ? 'conn' : e.ops ? (mode === 'new' ? 'ops' : 'conn') : 'map');
      toast('Fix ' + n + ' item' + (n > 1 ? 's' : '') + ' before saving. Errors are marked in the form.');
      return;
    }
    const r = await action.run(() => saveSource(mode, at.id, d, maps, ops, org !== savedOrg ? org : undefined), {
      all: (m, code) => {
        if (code === 'conflict' && /No changes/.test(m)) { toast('No changes to save.'); setDirty(false); } else toast(m);
      },
    });
    if (!r.ok) return;
    const o = r.output;
    if (o.mode === 'new') {
      // the server records the first sync itself: a source set up by hand has no simulated system behind it
      toast(o.name + ' (' + o.vendor + ') connected. Initial sync started.');
      onOpen({ mode: 'edit', id: o.source_id, tab: 'conn' });
      return;
    }
    setDirty(false); setErrs({}); setTest(null);
    toast(o.name + ' saved. Configuration is now v' + o.ver + '.');
    if (o.wasOff) window.setTimeout(() => ui.sync(o.source_id), 400);
  }

  function runTest() {
    const e = validate(mode, at.id, d, maps, ops), bad = Object.keys(e).filter(CONN_KEY);
    setTab('conn');
    if (bad.length) { setErrs(e); setTest({ ok: false, msg: 'Fix the highlighted connection settings first.' }); return; }
    setTest({ state: 'running' });
    // the server probes the source's connector when the endpoint is the saved one (source.test with the draft)
    void testDraft(mode === 'edit' ? at.id : '', d, ops).then((r) => setTest(r.ok ? r.output : { ok: false, msg: r.error.message }));
  }

  function revert() {
    if (!s) return;
    setD(draftOf(s)); setMaps(mappings(s.id).map((r) => r.slice())); setOps({ read: s.read.slice(), write: s.write.slice() }); setOrg(savedOrg);
    setErrs({}); setDirty(false); setTest(null);
    toast('Changes reverted to the saved configuration.');
  }

  const cmN = s ? commentsOf('src:' + s.id).length : 0;
  const tabs: [string, string][] = mode === 'new'
    ? [['conn', 'Connection'], ['ops', 'Operations'], ['map', 'Field mapping (' + maps.length + ')']]
    : [['ov', 'Overview'], ['conn', 'Configuration'], ['map', 'Data Mapping (' + maps.length + ')'], ['hist', 'Sync & History'], ['sec', 'Security'], ['cm', 'Comments (' + cmN + ')']];

  const title = s ? (
    <span className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
      <VendorLogo vendor={s.vendor} />
      <span>{s.name}</span>
      {s.syncing ? <span className="chip y">Syncing</span> : <StatusChip s={s.status} />}
    </span>
  ) : 'Add source';
  const sub = s ? s.vendor + ' adapter · config v' + s.cfgVer : 'Connect a system. Each system is its own connector.';

  const conn = (
    <>
      <ConnTab s={s} d={d} errs={errs} setField={setField} setCfg={(k, v) => { setD({ ...d, cfg: { ...d.cfg, [k]: v } }); clearErr('c_' + k); touch(); }} test={test} />
      <Suspense fallback={<p className="note">Loading org units…</p>}>
        <OrgUnitSelect id="sd_org" value={org} disabled={!mgr} onChange={(v) => { setOrg(v); touch(); }} />
      </Suspense>
    </>
  );
  const opsTab = (
    <OpsTab ops={ops} err={errs.ops} onChange={(o) => { setOps(o); clearErr('ops'); touch(); }} />
  );
  let body: ReactNode;
  if (tab === 'conn') body = mode === 'edit' ? <>{conn}<div className="frops2">{opsTab}</div></> : conn;
  else if (tab === 'ops') body = opsTab;
  else if (tab === 'map') body = <MapTab s={s} dirty={dirty} d={d} maps={maps} errs={errs} onChange={(m, k) => { setMaps(m); if (k) clearErr(k, 'maps'); touch(); }} onReverted={(m) => { setMaps(m.map((r) => r.slice())); }} />;
  else if (tab === 'cm' && s) body = <Comments k={'src:' + s.id} label="source" />;
  else if (tab === 'ov' && s) body = <OvTab s={s} use={use} setUse={setUse} />;
  else if (tab === 'sec' && s) body = <SecTab s={s} />;
  else if (s) body = <HistTab s={s} />;

  let foot: ReactNode;
  if (!mgr) foot = <span className="note">Read-only. Only the Developer or Admin changes this connection.</span>;
  else if (mode === 'new')
    foot = (
      <>
        <button className="btn pri" onClick={save}>Create connection</button>
        <button className="btn" onClick={runTest}>Test connection</button>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
      </>
    );
  else if (s && ['ov', 'hist', 'sec'].includes(tab))
    foot = s.status === 'unavailable' ? (
      <>
        <button className="btn pri" onClick={() => ui.reconnect(s.id)}><Icon name="unplug" /> {s.disconnected ? 'Reconnect' : 'Connect'}</button>
        <span className="grow" />
        <button className="btn" onClick={() => setTab('conn')}><Icon name="edit" /> Edit</button>
      </>
    ) : (
      <>
        <button className="btn" disabled={!!(s.syncing || s.paused || s.status === 'manual')} onClick={() => ui.sync(s.id)}><Icon name="sync" /> Sync now</button>
        <button className="btn" onClick={() => ui.pause(s.id)}>{s.paused ? <><Icon name="play" /> Resume</> : <><Icon name="pause" /> Pause</>}</button>
        <button className="btn" onClick={() => setTab('conn')}><Icon name="edit" /> Edit</button>
        <span className="grow" />
        <button className="btn danger" onClick={() => ui.disconnect(s.id)}><Icon name="unplug" /> Disconnect</button>
      </>
    );
  else if (s)
    foot = (
      <>
        <button className="btn pri" disabled={!dirty} onClick={save}>Save changes</button>
        <button className="btn" disabled={!dirty} onClick={revert}>Revert</button>
        <button className="btn" onClick={runTest}>Test connection</button>
        {s.status === 'stale' ? (
          <button className="btn dark" onClick={() => { setTest(null); ui.reconnect(s.id); }}>Refresh token and re-sync</button>
        ) : s.status === 'manual' ? (
          <button className="btn" onClick={() => { onClose(); ui.go('integration/import'); }}>Open Manual import</button>
        ) : (
          <button className="btn" disabled={!!(s.syncing || s.status === 'unavailable')} onClick={() => ui.sync(s.id)}>{s.syncing ? 'Syncing…' : 'Sync now'}</button>
        )}
        <span className="grow" />
        {dirty && <span className="chip y">Unsaved changes</span>}
        <button className="btn danger" onClick={() => ui.remove(s.id)}>Delete</button>
      </>
    );

  return (
    <Drawer title={title} sub={sub} wide onClose={onClose} foot={foot}>
      <div className="tabs sdtabs" role="tablist">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k || (tab === 'ops' && k === 'conn' && mode === 'edit')} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <fieldset disabled={!mgr && tab !== 'cm'} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>{body}</fieldset>
    </Drawer>
  );
}

/** The connector's own word when the screen shows it as stale (failing: the system did not answer; auth_expired). */
const connectorNote = (s: Source): string | null =>
  s.connectorStatus === 'failing' ? 'Connector failing: the system did not answer'
    : s.connectorStatus === 'auth_expired' ? 'Connector credentials refused' : null;

function LiveKv({ s }: { s: Source }) {
  return (
    <dl className="kv sdlive">
      <dt>Status</dt>
      <dd>{s.syncing ? <span className="chip y">Syncing {s.syncPct || 0}%</span> : <StatusChip s={s.status} />}{connectorNote(s) && <span className="note"> · {connectorNote(s)}</span>}</dd>
      <dt>Last sync</dt>
      <dd><span className="num">{s.lastSync == null ? (s.status === 'unavailable' ? 'Not connected' : 'Never') : srcAgeText(s).replace(/^(Updated|Last import) /, '')}</span></dd>
      <dt>Freshness · completeness · confidence</dt>
      <dd className="num">{s.lastSync == null ? '—' : srcFresh(s) + '% · ' + s.compl + '% · ' + s.conf + '%'}</dd>
      <dt>Records</dt>
      <dd className="num">{fmtN(s.records)}</dd>
      <dt>Source authority for</dt>
      <dd>{s.authority.length ? s.authority.join(', ') : '—'}</dd>
    </dl>
  );
}

function ConnTab({ s, d, errs: e, setField, setCfg, test }: {
  s?: Source; d: Draft; errs: Errs; setField: (k: keyof Draft, v: string) => void; setCfg: (k: string, v: string | number) => void; test: Test;
}) {
  const T = srcTypes(), CM = connMethods(), t = T[d.type], cm = CM[d.method];
  const vs = t.vendors.includes(d.vendor) ? t.vendors : [d.vendor].concat(t.vendors), AO = authOpts(), au = AO.includes(d.auth) ? AO : [d.auth].concat(AO);
  const err = (k: string) => (e[k] ? <div className="err">{e[k]}</div> : null);
  const tx = (k: keyof Draft, l: string, p: Record<string, unknown> = {}) => (
    <div className="fld">
      <label htmlFor={'sd_' + k}>{l}</label>
      <input id={'sd_' + k} value={String(d[k] ?? '')} autoComplete="off" onChange={(ev) => setField(k, ev.target.value)} {...p} />
      {err(k)}
    </div>
  );
  const sl = (k: keyof Draft, l: string, opts: string[], cur: string, dis?: boolean) => (
    <div className="fld">
      <label htmlFor={'sd_' + k}>{l}</label>
      <select id={'sd_' + k} value={cur} disabled={dis} onChange={(ev) => setField(k, ev.target.value)}>
        {opts.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      {err(k)}
    </div>
  );
  const age = s ? Math.floor((Date.now() - s.credAt) / 86400000) : 0, left = s ? s.credDays - age : 0;
  return (
    <>
      {s?.note && <div className={'callout ' + (s.status === 'unavailable' ? 'bad' : '')} style={{ marginBottom: 14 }}>{s.note}</div>}
      {s && <div id="sdLive"><LiveKv s={s} /></div>}
      <div className="grid g2" style={{ gap: '0 14px' }}>
        {tx('name', 'Display name', { maxLength: 60 })}
        {sl('type', 'System type', Object.keys(T).map((k) => T[k].label), t.label, !!s)}
        {sl('vendor', 'Vendor product', vs, d.vendor)}
        {tx('ver', 'Product version', { placeholder: 'e.g. 2023 FPS02' })}
        {sl('env', 'Environment', ['Production', 'Staging', 'Sandbox'], d.env)}
        {tx('owner', 'Owner team', { placeholder: 'e.g. Finance Systems' })}
      </div>
      <div className="methodbox">
        <div className="fld" style={{ marginBottom: 6 }}>
          <label htmlFor="sd_method">Connection method</label>
          <select id="sd_method" value={cm.label} onChange={(ev) => setField('method', ev.target.value)}>
            {Object.keys(CM).map((k) => <option key={k} value={CM[k].label}>{CM[k].label} · {CM[k].sub}</option>)}
          </select>
        </div>
        <div className="note" style={{ marginBottom: 12 }}>{cm.tip}</div>
        <div className="grid g2" style={{ gap: '0 14px' }}>
          {cm.fields.map((f) => {
            if (f.k === 'path' && d.cfg.delivery !== 'SFTP drop') return null;
            const v = d.cfg[f.k], id = 'sdc_' + f.k;
            return (
              <div className="fld" key={f.k}>
                <label htmlFor={id}>{f.l}{f.req ? ' *' : ''}</label>
                {f.t === 'select' ? (
                  <select id={id} value={String(v)} onChange={(ev) => setCfg(f.k, ev.target.value)}>
                    {(f.o as string[]).map((x) => <option key={x}>{x}</option>)}
                  </select>
                ) : (
                  <input id={id} type={f.t === 'number' ? 'number' : undefined} value={v == null ? '' : String(v)} placeholder={String(f.o || '')} autoComplete="off" spellCheck={false}
                    onChange={(ev) => setCfg(f.k, ev.target.value)} />
                )}
                {err('c_' + f.k)}
              </div>
            );
          })}
        </div>
        {!!cm.url && tx('url', 'Base URL or endpoint', { placeholder: 'https://system.example.com/api', spellCheck: false })}
        {!!cm.sched && (
          <div className="fld" style={{ maxWidth: 260 }}>
            <label htmlFor="sd_interval">{d.method === 'api' ? 'Poll interval (minutes, 0 = real time)' : 'Pull every (minutes)'}</label>
            <input id="sd_interval" type="number" min={d.method === 'api' ? 0 : 1} max={1440} value={d.interval} onChange={(ev) => setField('interval', ev.target.value)} />
            {err('interval')}
          </div>
        )}
      </div>
      {sl('auth', 'Authentication', au, d.auth)}
      <div className="credrow">
        <div>
          <b>Credentials</b>
          <div className="note">{s && s.credAt ? (left < 0 ? 'Secret expired ' + -left + ' days ago.' : 'Secret rotated ' + age + ' days ago · expires in ' + left + ' days.') : 'Encrypted and stored by Circularity after you save.'}</div>
        </div>
        {s && <RotateBtn id={s.id} label="Rotate credentials" />}
      </div>
      <div id="sdTest">
        {test && (test.state === 'running' ? (
          <div className="callout info"><span className="spin" /> Testing connection to {d.url || 'the endpoint'}…</div>
        ) : (
          <div className={'callout ' + (test.ok ? 'ok' : 'bad')}><b>{test.ok ? 'Connection OK' : 'Connection failed'}.</b> {test.msg}</div>
        ))}
      </div>
    </>
  );
}

function RotateBtn({ id, label }: { id: string; label: ReactNode }) {
  const ui = useInt();
  return <button className="btn sm" onClick={() => ui.rotate(id)}>{label}</button>;
}

function OpsTab({ ops, err, onChange }: { ops: { read: string[]; write: string[] }; err?: string; onChange: (o: { read: string[]; write: string[] }) => void }) {
  const blk = (w: 'read' | 'write', t: string, ph: string) => (
    <>
      <h4 style={{ margin: '0 0 6px' }}>{t}</h4>
      {ops[w].length ? ops[w].map((o, i) => (
        <div className="oprow" key={i}>
          <input className="mono" value={o} placeholder={ph} aria-label={t + ' ' + (i + 1)} spellCheck={false}
            onChange={(e) => onChange({ ...ops, [w]: ops[w].map((x, j) => (j === i ? e.target.value : x)) })} />
          <button className="iconbtn sm" aria-label="Remove operation" onClick={() => onChange({ ...ops, [w]: ops[w].filter((_, j) => j !== i) })}><Icon name="close" /></button>
        </div>
      )) : <div className="note" style={{ marginBottom: 6 }}>None configured.{w === 'write' ? ' Circularity cannot write to this system.' : ''}</div>}
      <button className="btn sm" style={{ margin: '6px 0 18px' }} onClick={() => onChange({ ...ops, [w]: ops[w].concat('') })}>+ Add {w} operation</button>
    </>
  );
  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>Operations Circularity may call on this system. Write operations only run after Human approval.</p>
      {blk('read', 'Read operations', 'GET /resource')}
      {blk('write', 'Write operations', 'POST /resource')}
      {err && <div className="err">{err}</div>}
    </>
  );
}

/** The mapping version a sync applies, Revert to an older version, and a preview of the rows on a sample record. */
function MapVersionBar({ s, maps, dirty, onReverted }: { s: Source; maps: string[][]; dirty: boolean; onReverted: (m: string[][]) => void }) {
  const mv = mappingVersions(s.id);
  const [pv, setPv] = useState<MapPreview | { state: 'running' } | { fail: string } | null>(null);
  const [to, setTo] = useState('');
  const action = useAction();
  const older = mv.versions.filter((v) => v.version !== mv.version);
  async function preview() {
    setPv({ state: 'running' });
    const r = await previewMapping(s.id, maps);
    setPv(r.ok ? r.output : { fail: r.error.message });
  }
  async function revert() {
    const v = +to;
    if (!v) return;
    const r = await action.run(() => revertMapping(s.id, v));
    if (!r.ok) return;
    setTo(''); setPv(null);
    onReverted(r.output.maps);
    toast('Field mapping reverted to v' + v + ' (now v' + r.output.version + '). The next sync applies it.');
  }
  return (
    <div className="callout info" style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <span>
          {mv.version == null ? <>Mapping: <b>the connector's built-in mapping</b> (no saved version)</> : <>Mapping <b>v{mv.version}</b> runs on every sync{mv.versions[0] ? <> · saved by {mv.versions[0].by}</> : null}</>}
        </span>
        <span className="grow" />
        <button className="btn sm" onClick={preview}>Preview on a sample record</button>
        {older.length > 0 && (
          <>
            <select aria-label="Mapping version to revert to" value={to} onChange={(ev) => setTo(ev.target.value)} disabled={dirty}>
              <option value="">Revert to…</option>
              {older.map((v) => <option key={v.version} value={v.version}>v{v.version}{v.note ? ' · ' + v.note : ''}</option>)}
            </select>
            <button className="btn sm" disabled={!to || dirty} onClick={revert}>Revert</button>
          </>
        )}
      </div>
      <div className="note">Rules a sync applies: copy, upper, lower, number, int, date, utc, units:kg&gt;t, fx:INR, code:grade. Any other text keeps the connector's own rule on a built-in row and copies the value on a row you add.</div>
      {pv && ('state' in pv ? <div className="note"><span className="spin" /> Mapping a sample record…</div>
        : 'fail' in pv ? <div className="err">{pv.fail}</div>
        : <MapPreviewView pv={pv} />)}
    </div>
  );
}

function MapPreviewView({ pv }: { pv: MapPreview }) {
  const show = (v: unknown) => (v == null ? '—' : typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : String(v));
  return (
    <div style={{ marginTop: 10 }}>
      {pv.record && <div className="note">Sample record <span className="mono">{pv.record.resource}/{pv.record.ext_id}</span> (the newest landed)</div>}
      {pv.error && <div className="err">{pv.record ? 'This record would fail: ' : ''}{pv.error}</div>}
      {pv.facts.length > 0 && (
        <div className="tw">
          <table className="t static">
            <thead><tr><th>Canonical field</th><th>Value</th><th>From</th><th>Rule</th><th /></tr></thead>
            <tbody>
              {pv.facts.map((f, i) => (
                <tr key={i}>
                  <td className="mono">{f.target}</td><td className="mono">{show(f.value)}</td>
                  <td className="mono">{f.source_field ?? '—'}</td><td>{f.transform ?? '—'}</td>
                  <td>{f.status === 'kept' ? null : <span className={'chip ' + (f.status === 'changed' ? 'y' : 'g')}>{f.status === 'changed' ? 'Changed' : 'Added'}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pv.dropped.length > 0 && <div className="note">Not mapped any more: <span className="mono">{pv.dropped.join(', ')}</span></div>}
    </div>
  );
}

function MapTab({ s, dirty, d, maps, errs: e, onChange, onReverted }: {
  s?: Source; dirty: boolean; d: Draft; maps: string[][]; errs: Errs; onChange: (m: string[][], k?: string) => void; onReverted: (m: string[][]) => void;
}) {
  const P = canonPrefix();
  const opts = useMemo(() => canon().flatMap((m) => m.fields.map((f) => P[m.n] + '.' + f.replace(/\[\]$/, ''))), [P]);
  const H = ['Source field', 'Sample value', 'Canonical field', 'Normalised', 'Rule'];
  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>
        Source field → canonical field. Units, currency, timestamps and status codes are normalised; source values and provenance are retained. Target model: <b>{srcTypes()[d.type].target}</b>.
      </p>
      {s && <MapVersionBar s={s} maps={maps} dirty={dirty} onReverted={onReverted} />}
      <datalist id="canonFields">{opts.map((o) => <option key={o} value={o} />)}</datalist>
      {maps.length ? (
        <div className="tw">
          <table className="t static maptbl">
            <thead><tr>{H.map((h) => <th key={h}>{h}</th>)}<th /></tr></thead>
            <tbody>
              {maps.map((m, i) => (
                <tr key={i}>
                  {[0, 1, 2, 3, 4].map((c) => (
                    <td key={c}>
                      <input className={'mono ' + (e['m' + i + '_' + c] ? 'bad' : '')} value={m[c] || ''} list={c === 2 ? 'canonFields' : undefined} aria-label={H[c] + ' row ' + (i + 1)} spellCheck={false}
                        onChange={(ev) => onChange(maps.map((r, j) => (j === i ? r.map((x, k) => (k === c ? ev.target.value : x)) : r)), 'm' + i + '_' + c)} />
                    </td>
                  ))}
                  <td><button className="iconbtn sm" aria-label="Remove mapping row" onClick={() => onChange(maps.filter((_, j) => j !== i))}><Icon name="close" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty"><b>No field mapping yet</b>Add at least one mapping before this source can feed a canonical model in a workflow.</div>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn sm" onClick={() => onChange(maps.concat([['', '', '', '', '']]))}>+ Add field mapping</button>
        {e.maps && <span className="err">{e.maps}</span>}
      </div>
    </>
  );
}

function HistTab({ s }: { s: Source }) {
  return (
    <>
      <h4 style={{ margin: '0 0 6px' }}>Sync runs</h4>
      {s.runs.length ? (
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Run</th><th>Time</th><th>Trigger</th><th className="r">Records</th><th className="r">Duration</th><th>Result</th></tr></thead>
            <tbody>
              {s.runs.map((r) => (
                <tr key={r.id + r.ts}>
                  <td className="mono">{r.id}</td>
                  <td className="num nowrap">{new Date(r.ts).toTimeString().slice(0, 8)}</td>
                  <td>{r.trigger}</td>
                  <td className="r num">{fmtN(r.rows)}</td>
                  <td className="r num">{r.dur} s</td>
                  <td><span className={'chip ' + (r.result === 'success' ? 'ok' : r.result === 'running' ? 'y' : 'bad')}>{r.result === 'success' ? 'Success' : r.result === 'running' ? 'Running' : 'Failed'}</span>{r.note && <div className="note">{r.note}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="note">No sync runs recorded in this session yet. Use Sync now.</div>}
      <h4 style={{ margin: '18px 0 6px' }}>Change history</h4>
      <AuditTable s={s} rev={false} />
    </>
  );
}

function AuditTable({ s, rev }: { s: Source; rev: boolean }) {
  const l = rev ? s.audit.slice().reverse() : s.audit;
  return (
    <div className="tw">
      <table className="t static tight">
        <thead><tr><th>Version</th><th>When</th><th>By</th><th>Change</th></tr></thead>
        <tbody>
          {l.map((a, i) => (
            <tr key={i}><td className="mono">v{a.ver}</td><td className="num nowrap">{when(a.ts)}</td><td>{a.who}</td><td>{a.change}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Comments({ k, label }: { k: string; label: string }) {
  useBackend();
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const l = commentsOf(k);
  const action = useAction();
  const post = async () => {
    const r = await action.run(() => addComment(k, text.trim()), { all: setErr });
    if (!r.ok) return;
    setText(''); setErr('');
    toast('Comment posted.');
  };
  return (
    <div className="cmbox" id="cmBox">
      <h4 style={{ margin: '18px 0 6px' }}>Comments <span className="note">{l.length}</span></h4>
      {l.length ? l.map((c, i) => (
        <div className="cmi" key={i}>
          <div className="row" style={{ gap: 8 }}><b>{c.by}</b><span className="note num">{isoTime(c.at)}</span></div>
          <div className="cmt">{c.text}</div>
        </div>
      )) : <div className="note">No comments yet.</div>}
      {can('comment') ? (
        <>
          <div className="fld" style={{ margin: '10px 0 8px' }}>
            <label htmlFor="cmText">Add a comment</label>
            <textarea id="cmText" maxLength={500} placeholder={'Visible to everyone who can see this ' + label + '.'} value={text} onChange={(e) => setText(e.target.value)} />
            <div className="hint">Do not enter personal data.</div>
            <div className="err" id="cmErr" hidden={!err}>{err}</div>
          </div>
          <button className="btn sm pri" onClick={post}>Post comment</button>
        </>
      ) : <div className="note" style={{ marginTop: 8 }}>Finance, Developer and Admin can comment here.</div>}
    </div>
  );
}

/* ---- Overview tab (frSdOv) ---- */
function HealthCard({ s }: { s: Source }) {
  const fail = srcFailing(s);
  const st = s.disconnected ? 'disconnected' : s.paused ? 'paused' : s.status === 'unavailable' ? 'unavailable' : s.status === 'stale' ? 'stale' : fail ? 'failing' : s.status === 'manual' ? 'manual' : 'healthy';
  const head = { healthy: 'Connection healthy', stale: 'Feed is stale', failing: 'Ingest workflow failing', unavailable: 'Not connected', disconnected: 'Disconnected', paused: 'Paused', manual: 'Manual import' }[st];
  const next = s.paused ? 'Paused' : s.interval && s.lastSync ? new Date(s.lastSync + s.interval * 60000).toISOString().slice(11, 16) + ' UTC' : /event|webhook/i.test(s.mode) ? 'On event' : '—';
  return (
    <div className={'frhc ' + st}>
      <IconTile ic={st === 'healthy' ? 'checks' : st === 'manual' ? 'file' : 'alert'} h={st === 'healthy' ? 'int' : st === 'manual' || st === 'paused' ? 'neutral' : 'alert'} />
      <div>
        <b>{head}</b>
        <span className="note">{s.disconnected ? 'Disconnected by ' + (s.discBy || 'Admin') + '. Reconnect to resume.' : [connectorNote(s), s.note || srcAgeText(s)].filter(Boolean).join('. ')}</span>
      </div>
      <dl>
        <dt>Last sync</dt><dd>{s.lastSync ? when(s.lastSync) : '—'}</dd>
        <dt>Next sync</dt><dd>{next}</dd>
      </dl>
    </div>
  );
}

export function UsageChart({ s, n }: { s: Source; n: number }) {
  const a = series(s, n), hx = (i: number) => parseInt(hashId(s.id + 'c' + i), 16);
  const b = a.map((v, i) => Math.round(v * (2.2 + (hx(i) % 6) / 10))), mx = Math.max(1, ...b), W = 320, H = 90;
  const pt = (v: number[]) => v.map((x, i) => ((i / (v.length - 1 || 1)) * W).toFixed(1) + ',' + (H - 4 - (x / mx) * (H - 10)).toFixed(1)).join(' ');
  return (
    <>
      <svg className="frchart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={'Records synced and API calls, last ' + n + ' days'}>
        <g stroke="var(--line)" strokeWidth="1">{[0, 1, 2, 3].map((i) => <path key={i} d={`M0 ${4 + (i * (H - 10)) / 3}H${W}`} />)}</g>
        <polyline points={pt(b)} fill="none" stroke="var(--h-int)" strokeWidth="1.8" />
        <polyline points={pt(a)} fill="none" stroke="var(--h-money)" strokeWidth="1.8" />
      </svg>
      <div className="frlegl"><span><i style={{ background: 'var(--h-money)' }} />Records synced</span><span><i style={{ background: 'var(--h-int)' }} />API calls</span></div>
    </>
  );
}

function OvTab({ s, use, setUse }: { s: Source; use: string; setUse: (v: string) => void }) {
  const ui = useInt();
  const n = +use, a = series(s, n), rec = sum(a), calls = Math.round(rec * 2.4), pr = sum(series(s, n * 2).slice(0, n));
  const uses = wfUsing(s.id), wr = (s.write || []).length, CM = connMethods();
  const trouble = s.status === 'stale' || s.status === 'unavailable' || srcFailing(s);
  return (
    <>
      <HealthCard s={s} />
      <h4>Connection details</h4>
      <dl className="frdl">
        <dt>Environment</dt><dd><span className="chip ok">{s.env || 'Production'}</span></dd>
        <dt>Instance URL</dt><dd className="mono">{s.url || '—'}</dd>
        <dt>Connector</dt><dd>{CM[s.method] ? CM[s.method].label : s.mode} · {s.ver}</dd>
        <dt>Auth</dt><dd>{s.auth}</dd>
        <dt>Connected by</dt><dd>{s.owner} · integration owner</dd>
        <dt>Connected on</dt><dd>{fmtDateYear(new Date(s.audit && s.audit[0] ? s.audit[0].ts : s.updatedAt))}</dd>
        <dt>Last sync</dt><dd>{srcAgeText(s)}</dd>
      </dl>
      <h4>Usage and performance</h4>
      <div className="frusg"><Segmented items={[['7', '7D'], ['30', '30D'], ['90', '90D']]} cur={use} onPick={setUse} label="Usage period" /></div>
      <div className="frust">
        <div><span className="note">Records synced</span><b className="num">{fmtN(rec)}</b><Delta d={pctDelta(rec, pr, true)} /></div>
        <div><span className="note">API calls</span><b className="num">{fmtN(calls)}</b><Delta d={pctDelta(calls, Math.round(pr * 2.4), null)} /></div>
        <div><span className="note">Success rate</span><b className="num">{s.status === 'unavailable' ? '—' : successRate(s) + '%'}</b><span className="note">{fmtN(failedRecords(s, n))} failed records</span></div>
      </div>
      <UsageChart s={s} n={n} />
      <details className="frsect">
        <summary><Icon name="shield" /><span><b>Permissions and access</b><small>{(s.read || []).length} read and {plural(wr, 'write operation')}; writes only after Human approval</small></span></summary>
        <ul className="mono frops">{(s.read || []).map((o) => <li key={o}>{o}</li>)}{(s.write || []).map((o) => <li key={o} className="w">{o}</li>)}</ul>
      </details>
      <details className="frsect">
        <summary><Icon name="layers" /><span><b>Key features</b><small>What it supplies and where it has authority</small></span></summary>
        <p>{s.inputs}</p>
        <p className="note">Authority: {(s.authority || []).join(', ') || '—'} · Used by {plural(uses.length, 'workflow')} · Steps {s.step.map((x) => 'S' + x).join(' ')}</p>
      </details>
      <details className="frsect" open={trouble}>
        <summary><Icon name="help" /><span><b>Troubleshooting</b><small>Logs, errors and recovery steps</small></span></summary>
        <p>{s.note || 'No open issues. The last runs completed without errors.'}</p>
        {canMgr() && <div className="row"><button className="btn sm" onClick={() => ui.test(s.id)}><Icon name="play" /> Test connection</button></div>}
        <div id="frSdTest"><TestSteps id={s.id} /></div>
      </details>
    </>
  );
}

function SecTab({ s }: { s: Source }) {
  const ui = useInt();
  const exp = s.credAt ? new Date(s.credAt + s.credDays * 864e5) : null, d = s.credAt ? credDays(s) : null;
  return (
    <>
      <h4>Authentication</h4>
      <dl className="frdl">
        <dt>Method</dt><dd>{s.auth}</dd>
        <dt>Credential issued</dt><dd>{s.credAt ? fmtDateYear(new Date(s.credAt)) : '—'}</dd>
        <dt>Expires</dt>
        <dd>{exp && d != null ? <>{fmtDateYear(exp)} · {d < 0 ? 'expired' : d + ' days'}{d <= 14 && <> <FabricStatus k="expiring" /></>}</> : '—'}</dd>
        <dt>Stored</dt><dd>{s.credential ? <>Encrypted by Circularity · version {s.credential.version} · ends in ••••{s.credential.last4}</> : 'Encrypted by Circularity when you rotate it; never shown in the interface'}</dd>
      </dl>
      {canMgr() && (
        <div className="row" style={{ margin: '8px 0 14px' }}>
          <RotateBtn id={s.id} label={<><Icon name="key" /> Rotate secret</>} />
          {s.status === 'stale' && <button className="btn sm pri" onClick={() => ui.reauth(s.id)}>Re-authenticate</button>}
        </div>
      )}
      <h4>Scopes</h4>
      <ul className="mono frops">{(s.read || []).map((o) => <li key={o}>{o}</li>)}{(s.write || []).map((o) => <li key={o} className="w">{o} · after approval</li>)}</ul>
      <h4>Audit</h4>
      <AuditTable s={s} rev />
    </>
  );
}

/** The org unit a source belongs to (plan 8 MVP-1.4; source.update's org_unit_id), from the units the account may see
 *  (GET /api/screens/orgs, as the Connect dialog). A unit the account cannot see stays shown by its id. Suspends while
 *  the list loads (wrap it in Suspense). */
function OrgUnitSelect({ id, value, onChange, disabled }: { id: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const { units } = useOrgUnits();
  return (
    <div className="fld" style={{ marginTop: 12 }}>
      <label htmlFor={id}>Org unit</label>
      <select id={id} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">Shared by every org unit</option>
        {value && !units.some((u) => u.id === value) && <option value={value}>{value}</option>}
        {units.map((u) => <option key={u.id} value={u.id}>{' '.repeat(u.depth * 2) + u.name}</option>)}
      </select>
      <p className="note">The org unit whose cases and configuration use this source. Its configuration pack includes it.</p>
    </div>
  );
}
