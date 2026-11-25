/* From the adapter registry (plan 9, P9-8.1, registry entry I-18): a Developer picks a connector by kind (Catalogue, Generic REST,
   From an API spec), names the system owner and the org unit, and creates a connection that starts in the test environment,
   read only (connection.create). Production access and write-back are the owner's to approve, from the Source drawer.
   The secret is a password field, sent once and cleared after the call; the server stores it encrypted and never returns it. */
import { Suspense, useState } from 'react';
import { createConnection, registryEntries, type ConnectorKind, type RegistryEntry } from '../../api/connections';
import { useOrgUnits } from '../../api/orgs';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';

const KINDS: [ConnectorKind, string][] = [['catalogue', 'Catalogue'], ['generic_rest', 'Generic REST'], ['from_spec', 'From an API spec']];

export function RegistryPicker({ onClose, onCreated }: { onClose: () => void; onCreated?: (sourceId: string) => void }) {
  return (
    <Suspense fallback={<p className="note">Loading the adapter registry…</p>}>
      <Picker onClose={onClose} onCreated={onCreated} />
    </Suspense>
  );
}

function Picker({ onClose, onCreated }: { onClose: () => void; onCreated?: (sourceId: string) => void }) {
  const entries = registryEntries();
  const { units } = useOrgUnits();
  const [kind, setKind] = useState<ConnectorKind>('catalogue');
  const [pick, setPick] = useState<RegistryEntry | null>(null);
  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [org, setOrg] = useState('');
  const [url, setUrl] = useState('');
  const [auth, setAuth] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const shown = entries.filter((e) => e.kind === kind);
  const needsUrl = !!pick && pick.kind !== 'catalogue';
  const ready = !!pick && name.trim().length > 0 && owner.trim().length > 0 && org !== '' && (!needsUrl || /^https?:\/\/\S+/.test(url)) && (secret === '' || secret.length >= 8);

  async function create() {
    if (!pick || busy) return;
    setBusy(true);
    const r = await createConnection({
      registryId: pick.id, version: pick.version, name: name.trim(), orgUnitId: org, systemOwner: owner.trim(),
      ...(needsUrl ? { testBaseUrl: url } : {}), ...(needsUrl && (auth || pick.auth_methods[0]) ? { auth: auth || pick.auth_methods[0] } : {}), ...(secret ? { secret } : {}),
    }); // prettier-ignore
    setSecret(''); // never kept after the call
    setBusy(false);
    if (refused(r)) return;
    toast(name.trim() + ' is created in the test environment, read only. Ask its system owner to approve production access.');
    onCreated?.(r.output.source_id);
    onClose();
  }

  return (
    <>
      <p className="note" style={{ marginTop: 0 }}>Start from a connector in the registry. A new connection runs in the test environment, read only: nothing is synced on a schedule and no instruction is sent until its system owner approves production access.</p>
      <div className="row" role="tablist" aria-label="Connector kind">
        {KINDS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={kind === k} className={'btn sm' + (kind === k ? ' pri' : '')} onClick={() => { setKind(k); setPick(null); setAuth(''); }}>{label}</button>
        ))}
      </div>
      <div className="frpick" style={{ marginTop: 8 }}>
        {shown.length === 0 && <p className="note">{kind === 'from_spec' ? 'No API-spec connector is released yet. Draft one from an OpenAPI file; another person releases it.' : 'No connector of this kind.'}</p>}
        {shown.map((e) => (
          <label key={e.id + e.version} className={'frrec frpk' + (pick?.id === e.id && pick.version === e.version ? ' on' : '')}>
            <input type="radio" name="registryEntry" checked={pick?.id === e.id && pick.version === e.version} onChange={() => { setPick(e); setAuth(e.auth_methods[0] ?? ''); }} />
            <b>{e.vendor_family}</b> <span className="note">{e.system_type} · v{e.version} · {e.status}</span>
          </label>
        ))}
      </div>
      {pick && (
        <div style={{ marginTop: 12 }}>
          <label htmlFor="rgName">Connection name</label>
          <input id="rgName" className="sel" style={{ width: '100%' }} value={name} onChange={(e) => setName(e.target.value)} />
          <label htmlFor="rgOwner" style={{ marginTop: 8, display: 'block' }}>System owner</label>
          <input id="rgOwner" className="sel" style={{ width: '100%' }} placeholder="A person from the directory, e.g. approver" autoComplete="off" value={owner} onChange={(e) => setOwner(e.target.value)} />
          <p className="note">The owner approves production access and write-back. The person who asks cannot approve their own request.</p>
          <label htmlFor="rgOrg">Org unit</label>
          <select id="rgOrg" className="sel" value={org} onChange={(e) => setOrg(e.target.value)}>
            <option value="">Choose an org unit</option>
            {units.map((u) => <option key={u.id} value={u.id}>{' '.repeat(u.depth * 2) + u.name}</option>)}
          </select>
          {needsUrl && (
            <>
              <label htmlFor="rgUrl" style={{ marginTop: 8, display: 'block' }}>Test base URL</label>
              <input id="rgUrl" className="sel" style={{ width: '100%' }} placeholder="https://test.example.com/api" value={url} onChange={(e) => setUrl(e.target.value)} />
              <label htmlFor="rgAuth" style={{ marginTop: 8, display: 'block' }}>Sign in with</label>
              <select id="rgAuth" className="sel" value={auth} onChange={(e) => setAuth(e.target.value)}>
                {pick.auth_methods.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </>
          )}
          <label htmlFor="rgSecret" style={{ marginTop: 8, display: 'block' }}>Test credential (optional)</label>
          <input id="rgSecret" type="password" className="sel" style={{ width: '100%' }} autoComplete="off" placeholder="Stored encrypted, never shown again" value={secret} onChange={(e) => setSecret(e.target.value)} />
        </div>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn pri" disabled={!ready || busy} onClick={() => void create()}>Create test connection</button>
      </div>
    </>
  );
}
