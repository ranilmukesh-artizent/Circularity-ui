/* Connect an integration from the catalogue (auth → scopes → test → mappings → first sync), and re-authenticate a source (5.10). */
import { useEffect, useRef, useState } from 'react';
import { catalog, finishConnect, frAuthOptions, frSample, hashId, notOnServer, nowLabel, reauthenticated, source, typeOf } from '../../api/integration';
import { Icon } from '../../ui/Icon';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { FrSt, fmtN, runTest, TestSteps, useInt, Vlogo } from './ui';

export type CxStart = { mode: 'new'; cat: string } | { mode: 'reauth'; src: string };
const STEPS = ['Authentication', 'Scopes', 'Test connection', 'Field mapping', 'First sync'];
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

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
  const [maps, setMaps] = useState<[string, string, string, string, number][] | null>(null);
  const [acc, setAcc] = useState<Record<number, boolean>>({});
  const [sync, setSync] = useState(0);
  const [wf, setWf] = useState<string | null>(null);
  const n = useRef(1200 + (parseInt(hashId(start.mode === 'new' ? start.cat : start.src), 16) % 9000));
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; };
  }, []);

  if (!c && !s) return null;
  const testId = c ? 'cat:' + c.id : s!.id;
  const steps = reauth ? ['Authentication', 'Test connection'] : STEPS;
  const si = reauth ? (step === 1 ? 0 : 1) : step - 1;
  const authLabel = () => frAuthOptions().find((a) => a[0] === auth)![1];

  function next() {
    if (!reauth && step === 4) {
      setStep(5);
      let p = 0;
      const tick = () => {
        if (!live.current) return;
        p = Math.min(100, p + (reduced() ? 100 : 20));
        if (p >= 100) {
          const w = finishConnect(c!.id, authLabel(), scopes, n.current, maps!.filter((_, i) => acc[i]).map((r) => [r[0], r[1], r[2], r[3], '']));
          if (w === null) { onClose(); toast(notOnServer('Connecting from the catalogue')); return; }
          setWf(w);
        }
        setSync(p);
        if (p < 100) window.setTimeout(tick, 220);
      };
      window.setTimeout(tick, reduced() ? 0 : 220);
      return;
    }
    setStep(reauth ? 3 : step + 1);
  }
  const back = () => setStep(reauth ? 1 : Math.max(1, step - 1));
  function test() {
    const t = reauth
      ? { ...s!, status: 'live' as const }
      : { id: 'cat:' + c!.id, vendor: c!.vendor, status: 'live' as const, url: 'https://' + c!.id + '.northfield.example/api', auth: authLabel(), read: ['GET /records'] };
    setTested(true);
    runTest(t, (ok) => live.current && setPassed(ok));
  }
  function done() {
    if (!s) return;
    const r = reauthenticated(s.id);
    onClose();
    if (r === 'reconnect') ui.reconnect(s.id);
    else if (r === null) toast(notOnServer('Re-authenticating a source'));
    else toast(s.vendor + ' re-authenticated. The credential is renewed for 180 days.');
  }

  let body: React.ReactNode, foot: React.ReactNode;
  if (step === 1) {
    const ready = auth === 'oauth' ? allowed : key.length >= 6 || auth === 'sftp';
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>How Circularity signs in to {v}. Credentials go to the platform secret store and are never shown again.</p>
        <div className="frauth">
          {frAuthOptions().filter((a) => !c || a[0] !== 'sftp' || c.type === 'store').map((a) => (
            <label key={a[0]} className={'frao ' + (auth === a[0] ? 'on' : '')}>
              <input type="radio" name="frAuth" value={a[0]} checked={auth === a[0]} onChange={() => { setAuth(a[0]); setAllowed(false); setKey(''); }} />
              <b>{a[1]}</b>
              <span className="note">{a[2]}</span>
            </label>
          ))}
        </div>
        {auth === 'oauth' ? (
          <div className="frconsent" id="frConsent">
            <div className="frcsh"><Vlogo vendor={v} /><b>{v}</b><span className="note">Sign in to authorise</span></div>
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
          <><label htmlFor="frKey">API key</label><input id="frKey" type="password" className="sel" style={{ width: '100%' }} placeholder="Paste the key" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} /></>
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
                      <td className="r">{r[4] >= 85 ? <FrSt k="success" t={'High · ' + r[4] + '%'} /> : r[4] >= 70 ? <FrSt k="warning" t={'Medium · ' + r[4] + '%'} /> : <FrSt k="failed" t={'Low · ' + r[4] + '%'} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn sm" onClick={() => { const a = { ...acc }; rows.forEach((r, i) => { if (r[4] >= 85) a[i] = true; }); setAcc(a); }}>Accept all high</button>
              <span className="note">{nAcc} of {rows.length} accepted</span>
            </div>
          </>
        ) : (
          <button className="btn pri" onClick={() => { setMaps(frSample(c!.type)); setAcc({}); }}><Icon name="spark" /> Suggest mappings</button>
        )}
      </>
    );
    foot = <><button className="btn" onClick={back}>Back</button><button className="btn pri" disabled={!Object.values(acc).some(Boolean)} onClick={next}>Continue</button></>;
  } else {
    const p = sync;
    body = (
      <>
        <p className="note" style={{ marginTop: 0 }}>The first sync reads a full extract; after that, {scopes.includes('events') ? 'events arrive as they happen' : 'it runs on a schedule'}.</p>
        <div className="frprog"><i style={{ width: p + '%' }} /></div>
        <p className="num">{p < 100 ? 'Syncing… ' + p + '% · ' + fmtN(Math.round((p * n.current) / 100)) + ' records' : 'Connected · ' + fmtN(n.current) + ' records in the first sync'}</p>
        {p >= 100 && <div className="callout ok"><b>{v} is connected.</b> It appears in the Source Map, and its ingest workflow is ready as a draft in Workflow Studio.</div>}
      </>
    );
    foot = p >= 100
      ? <><button className="btn" onClick={() => { onClose(); if (wf) ui.go('integration/studio/' + wf); }}>Open the ingest workflow</button><button className="btn pri" onClick={onClose}>Done</button></>
      : <button className="btn" disabled>Syncing…</button>;
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
