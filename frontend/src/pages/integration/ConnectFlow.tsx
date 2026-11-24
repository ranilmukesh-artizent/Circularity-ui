/* Connect an integration from the catalogue (auth → scopes → test → mappings → first sync), and re-authenticate a source (5.10).
   The test is the server's probe (source.test); finishing creates the source (source.update, mode "catalog"); the
   re-authentication renews the credential (credentials.rotate) or, for a stale feed, refreshes the token (source.reconnect).
   Every catalogue system is synthetic: source-sim mocks it. The API key field is prefilled with the simulated system's
   sandbox key (source.sandboxKey); the key typed is the one the test probes with and the one stored, so another key
   fails at Auth. Connecting stores its connection and credential (encrypted)
   and queues a first sync that really reads it; its records then show in Sync & History (plan 6 A3). Suggest mappings
   asks the server (mapping.catalogSuggest): the rows the system's records really support, none for a system with no
   circularity data (its records are kept raw). The Scopes step also asks which org unit the source belongs to (plan 8,
   GET /api/screens/orgs): by default the top bar's tenant when it is one, else none, so the source is shared by every
   org unit as before. */
import { Suspense, useEffect, useRef, useState } from 'react';
import { defaultConnectOrg, useOrgUnits } from '../../api/orgs';
import { tenantFilter } from '../../api/session';
import { catalog, connectFromCatalog, frAuthOptions, nowLabel, reauthenticated, sandboxKey, source, suggestMappings, typeOf, type SuggestedMap } from '../../api/integration';
import { Icon } from '../../components/Icon';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';
import { VendorLogo } from '../../components/kit/VendorLogo';
import { runTest, TestSteps } from './ConnectionTests';
import { useInt } from './FabricContext';
import { FabricStatus } from './FabricStatus';

export type CxStart = { mode: 'new'; cat: string } | { mode: 'reauth'; src: string };
const STEPS = ['Authentication', 'Scopes', 'Test connection', 'Field mapping', 'First sync'];

function initialAuth(start: CxStart): string {
  if (start.mode === 'reauth') {
    const s = source(start.src);
    return s && /oauth/i.test(s.auth) ? 'oauth' : s && /key/i.test(s.auth) ? 'key' : 'sp';
  }
  const c = catalog().find((x) => x.id === start.cat)!;
  return c.type === 'store' && !c.auth.includes('OAuth 2.0') ? 'sftp' : /OAuth/.test(c.auth[0]) ? 'oauth' : c.auth[0] === 'API key' ? 'key' : 'sp';
}

export function ConnectFlow({ start, onClose }: { start: CxStart; onClose: () => void }) {
  const ui = useInt();
  const reauth = start.mode === 'reauth';
  const c = start.mode === 'new' ? catalog().find((y) => y.id === start.cat) : undefined;
  const s = start.mode === 'reauth' ? source(start.src) : undefined;
  const v = c ? c.vendor : s?.vendor ?? '';
  const [step, setStep] = useState(1);
  const [auth, setAuth] = useState(() => initialAuth(start));
  const [allowed, setAllowed] = useState(false);
  const [key, setKey] = useState('');
  const [scopes, setScopes] = useState<string[]>(() => (reauth ? (s?.read ?? []).slice() : ['read']));
  const [tested, setTested] = useState(false);
  const [passed, setPassed] = useState(false);
  const [maps, setMaps] = useState<SuggestedMap[] | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [sampleErr, setSampleErr] = useState<string | null>(null);
  const [acc, setAcc] = useState<Record<number, boolean>>({});
  const [connected, setDone] = useState(false);
  const [sandbox, setSandbox] = useState<string | null>(null);
  const [org, setOrg] = useState<string | null>(null); // null until the org units have loaded: shared, as before
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; };
  }, []);
  // the simulated system's sandbox key: the API key field starts with it (a person may type another one)
  const catId = c?.id;
  const authNow = useRef(auth);
  authNow.current = auth;
  useEffect(() => {
    if (!catId) return;
    void sandboxKey(catId).then((r) => {
      if (!live.current || !r.ok) return;
      setSandbox(r.output.key);
      if (authNow.current === 'key') setKey((k) => k || r.output.key);
    });
  }, [catId]);

  if (!c && !s) return null;
  const testId = c ? 'cat:' + c.id : s!.id;
  const steps = reauth ? ['Authentication', 'Test connection'] : STEPS;
  const si = reauth ? (step === 1 ? 0 : 1) : step - 1;
  const authLabel = () => frAuthOptions().find((a) => a[0] === auth)![1];
  // the API key typed (sent to the test and stored on connect); other sign-ins use the simulated system's own credential
  const typedKey = () => (auth === 'key' && key ? key : undefined);

  function next() {
    if (!reauth && step === 4) {
      setStep(5);
      // the connection is made on the server now (the demo's frCxFinish); the first sync runs in the worker
      const accepted = (maps ?? []).filter((_, i) => acc[i]);
      void (async () => {
        const r = await connectFromCatalog(c!.id, auth, scopes, accepted, typedKey(), org ?? undefined);
        if (!live.current) return;
        if (refused(r)) { onClose(); return; }
        setDone(true);
      })();
      return;
    }
    setStep(reauth ? 3 : step + 1);
  }
  const back = () => setStep(reauth ? 1 : Math.max(1, step - 1));
  function test() {
    setTested(true);
    const secret = typedKey();
    runTest(reauth ? { source_id: s!.id, reauth: true, auth: authLabel() } : { source_id: 'cat:' + c!.id, auth: authLabel(), ...(secret ? { secret } : {}) }, (ok) => live.current && setPassed(ok));
  }
  // the rows the system's records really support, from the server (mapping.catalogSuggest): none for a system with no circularity data
  async function suggest() {
    setSuggesting(true);
    const r = await suggestMappings(c!.id);
    if (!live.current) return;
    setSuggesting(false);
    if (refused(r)) return;
    setMaps(r.output.rows);
    setSampleErr(r.output.error);
    setAcc({});
  }
  async function done() {
    if (!s) return;
    const r = await reauthenticated(s.id);
    onClose();
    if (r === 'reconnect') ui.reconnect(s.id);
    else if (!refused(r)) toast(s.vendor + ' re-authenticated. The credential is renewed for 180 days.');
  }

  let body: React.ReactNode, foot: React.ReactNode;
  if (step === 1) {
    const ready = auth === 'oauth' ? allowed : key.length >= 6 || auth === 'sftp';
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>How Circularity signs in to {v}. Credentials are encrypted and stored by Circularity, and never shown again.</p>
        <div className="frauth">
          {frAuthOptions().filter((a) => !c || a[0] !== 'sftp' || c.type === 'store').map((a) => (
            <label key={a[0]} className={'frao ' + (auth === a[0] ? 'on' : '')}>
              <input type="radio" name="frAuth" value={a[0]} checked={auth === a[0]} onChange={() => { setAuth(a[0]); setAllowed(false); setKey(a[0] === 'key' && c && sandbox ? sandbox : ''); }} />
              <b>{a[1]}</b>
              <span className="note">{a[2]}</span>
            </label>
          ))}
        </div>
        {auth === 'oauth' ? (
          <div className="frconsent" id="frConsent">
            <div className="frcsh"><VendorLogo vendor={v} /><b>{v}</b><span className="note">Sign in to authorise</span></div>
            <p><b>Circularity Decision Workbench</b> is requesting access to:</p>
            <ul>
              <li>Read records it needs as evidence</li>
              {reauth && <li>Keep the existing scopes for {v}</li>}
              <li>No write access unless you grant it in the next step</li>
            </ul>
            {allowed ? (
              <p className="frallowed"><Icon name="check" /> Allowed by {nowLabel()}</p>
            ) : (
              <div className="row"><button className="btn" onClick={onClose}>Deny</button><button className="btn pri" onClick={() => setAllowed(true)}>Allow</button></div>
            )}
          </div>
        ) : auth === 'key' ? (
          <>
            <label htmlFor="frKey">API key</label><input id="frKey" type="password" className="sel" style={{ width: '100%' }} placeholder="Paste the key" autoComplete="off" value={key} onChange={(e) => { setKey(e.target.value); setTested(false); setPassed(false); }} />
            {c && sandbox && (key === sandbox
              ? <p className="note" id="frKeyNote">This is the sandbox key of the simulated system.</p>
              : <p className="note" id="frKeyNote">The simulated system accepts only its sandbox key; another key fails the test at Auth.</p>)}
          </>
        ) : auth === 'sftp' ? (
          <><label htmlFor="frSftp">Drop path</label><input id="frSftp" className="sel" style={{ width: '100%' }} defaultValue="sftp://partner.example/outbound" onChange={(e) => setKey(e.target.value)} /><p className="note">Each file must arrive with a signed manifest; unsigned files are rejected.</p></>
        ) : (
          <><label htmlFor="frSp">Service principal ID</label><input id="frSp" className="sel" style={{ width: '100%' }} placeholder="e.g. svc-circularity-read" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} /></>
        )}
      </>
    );
    foot = <><button className="btn" onClick={onClose}>Cancel</button><button className="btn pri" disabled={!ready} onClick={next}>Continue</button></>;
  } else if (step === 2) {
    const rs: [string, string, string][] = [['read', 'Read records', 'Required. Evidence only.'], ['write', 'Write approved instructions', 'Off by default; writes only run after Human approval.'], ['events', 'Receive events', 'Webhook or queue delivery for near-real-time updates.']];
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>Grant only what Circularity needs. You can change scopes later under Security.</p>
        <div className="frchk">
          {rs.map((r) => (
            <label key={r[0]} className="tog">
              <input type="checkbox" checked={scopes.includes(r[0])} disabled={r[0] === 'read'} onChange={(e) => setScopes(e.target.checked ? [...new Set(scopes.concat(r[0]))] : scopes.filter((y) => y !== r[0]))} />{' '}
              <b>{r[1]}</b> <span className="note">{r[2]}</span>
            </label>
          ))}
        </div>
        <Suspense fallback={<p className="note">Loading org units…</p>}>
          <OrgField value={org} onChange={setOrg} />
        </Suspense>
      </>
    );
    foot = <><button className="btn" onClick={back}>Back</button><button className="btn pri" onClick={next}>Continue</button></>;
  } else if (step === 3) {
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>Each check runs against {v} now.</p>
        <div id="frCxTest">{tested && <TestSteps id={testId} />}</div>
        {!tested && <button className="btn pri" onClick={test}><Icon name="play" /> Test connection</button>}
      </>
    );
    foot = (
      <>
        <button className="btn" onClick={back}>Back</button>
        {reauth ? <button className="btn pri" disabled={!passed} onClick={done}>Finish</button> : <button className="btn pri" disabled={!passed} onClick={next}>Continue</button>}
      </>
    );
  } else if (step === 4) {
    const rows = maps ?? [], nAcc = Object.values(acc).filter(Boolean).length;
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>Source field → canonical field for the <b>{typeOf(c!.type).target}</b> model. The agent proposes; you accept.</p>
        {rows.length ? (
          <>
            <div className="tw">
              <table className="t static tight">
                <thead><tr><th /><th>Source field</th><th>Sample</th><th>Canonical field</th><th>Normalised</th><th className="r">Confidence</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td><input type="checkbox" aria-label={'Accept ' + r[0]} checked={!!acc[i]} onChange={(e) => setAcc({ ...acc, [i]: e.target.checked })} /></td>
                      <td className="mono">{r[0]}</td><td className="mono note">{r[1]}</td><td className="mono">{r[2]}</td><td className="mono note">{r[3]}</td>
                      <td className="r">{r[4] >= 85 ? <FabricStatus k="success" t={'High · ' + r[4] + '%'} /> : r[4] >= 70 ? <FabricStatus k="warning" t={'Medium · ' + r[4] + '%'} /> : <FabricStatus k="failed" t={'Low · ' + r[4] + '%'} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn sm" onClick={() => { const a = { ...acc }; rows.forEach((r, i) => { if (r[4] >= 85) a[i] = true; }); setAcc(a); }}>Accept all high</button>
              <span className="note">{nAcc} of {rows.length} accepted</span>
            </div>
            {sampleErr && <p className="note">{sampleErr}</p>}
          </>
        ) : maps ? (
          <div className="callout">No field of {v} maps to a canonical model. Its records are kept as source records (Sync &amp; History, Source Tables) and add no canonical data.</div>
        ) : (
          <button className="btn pri" disabled={suggesting} onClick={() => void suggest()}><Icon name="spark" /> Suggest mappings</button>
        )}
      </>
    );
    const ready = maps !== null && (maps.length === 0 || Object.values(acc).some(Boolean));
    foot = <><button className="btn" onClick={back}>Back</button><button className="btn pri" disabled={!ready} onClick={next}>Continue</button></>;
  } else {
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>The first sync reads a full extract; after that, {scopes.includes('events') ? 'events arrive as they happen' : 'it runs on a schedule'}.</p>
        <div className="frprog"><i style={{ width: connected ? '100%' : '30%' }} /></div>
        <p className="num">{connected ? 'Connected · first sync queued' : 'Connecting…'}</p>
        {connected && <div className="callout ok"><b>{v} is connected.</b> It appears in the Source Map; its records show in Sync &amp; History once the first sync has run. {v} is a synthetic system simulated for this environment.</div>}
      </>
    );
    foot = connected ? <button className="btn pri" onClick={onClose}>Done</button> : <button className="btn" disabled>Syncing…</button>;
  }

  return (
    <Modal title={(reauth ? 'Re-authenticate ' : 'Connect ') + v} wide onClose={onClose} foot={foot}>
      <ol className="frcxs">
        {steps.map((t, i) => (
          <li key={t} className={i < si ? 'done' : i === si ? 'on' : ''}><span>{i < si ? '✓' : i + 1}</span>{t}</li>
        ))}
      </ol>
      {body}
    </Modal>
  );
}

/** Which org unit the new source belongs to: one the account may see, or none (shared by every org unit). */
function OrgField({ value, onChange }: { value: string | null; onChange: (v: string) => void }) {
  const { units } = useOrgUnits();
  const start = defaultConnectOrg(units, tenantFilter());
  useEffect(() => {
    if (value === null) onChange(start);
  }, [value, start, onChange]);
  return (
    <div style={{ marginTop: 12 }}>
      <label htmlFor="frOrg">Org unit</label>
      <select id="frOrg" className="sel" value={value ?? start} onChange={(e) => onChange(e.target.value)}>
        <option value="">Shared by every org unit</option>
        {units.map((u) => <option key={u.id} value={u.id}>{' '.repeat(u.depth * 2) + u.name}</option>)}
      </select>
      <p className="note">The org unit whose cases and configuration use this source. Its configuration pack includes it.</p>
    </div>
  );
}