import { useState } from 'react';
import { refreshAccess } from '../../../api/access';
import { exportPack, importPack, packFileName, parsePack, previewPack, type OrgPack, type PackImport, type PackPreview } from '../../../api/orgs';
import { Modal } from '../../../components/Overlay';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { download } from '../../../utils/download';

/** Export a unit's configuration pack as a JSON file (org.exportPack, manageOrgs). It never holds a secret. */
export function ExportPackButton({ unit, name }: { unit: string; name: string }) {
  const action = useAction();
  const run = async () => {
    const r = await action.run(() => exportPack(unit));
    if (!r.ok) return;
    download(packFileName(unit), JSON.stringify(r.output, null, 2));
    toast(name + "'s configuration pack is downloaded. It holds no passwords, keys or tokens.");
  };
  return <button className="btn sm" disabled={action.pending} onClick={() => void run()}>Export pack</button>;
}

/**
 * Import a pack into a unit: choose the file, see what will be created (org.previewPack, changes nothing), then apply
 * (org.importPack). Sources arrive disconnected without credentials; workflows and decision flows arrive as drafts.
 */
export function ImportPackDialog({ unit, name, onClose }: { unit: string; name: string; onClose: () => void }) {
  const action = useAction();
  const [pack, setPack] = useState<OrgPack | null>(null);
  const [preview, setPreview] = useState<PackPreview | null>(null);
  const [done, setDone] = useState<PackImport | null>(null);
  const [err, setErr] = useState('');

  const choose = async (file: File | undefined) => {
    setPack(null);
    setPreview(null);
    setErr('');
    if (!file) return;
    const parsed = parsePack(await file.text());
    if ('error' in parsed) {
      setErr(parsed.error);
      return;
    }
    const r = await action.run(() => previewPack(parsed.pack, unit), { all: setErr });
    if (!r.ok) return;
    setPack(parsed.pack);
    setPreview(r.output);
  };
  const apply = async () => {
    if (!pack) return;
    const r = await action.run(() => importPack(pack, unit), { all: setErr });
    if (!r.ok) return;
    setDone(r.output);
    toast('The pack is imported into ' + name + '. Nothing is published.');
    void refreshAccess();
  };

  const foot = done ? (
    <button className="btn pri" onClick={onClose}>Done</button>
  ) : (
    <>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn pri" disabled={!preview || action.pending} onClick={() => void apply()}>Import</button>
    </>
  );
  return (
    <Modal title={'Import a configuration pack into ' + name} wide onClose={onClose} foot={foot}>
      {done ? (
        <div id="orgPackDone">
          <div className="callout ok">
            <b>Imported.</b> {done.created.sources.length} sources, {done.created.workflows.length} workflows and {done.created.flows.length} decision flows were added to {name} as drafts.
          </div>
          {done.needs.length > 0 && (
            <>
              <p className="note">Still to do before they run:</p>
              <ul>{done.needs.map((n) => <li key={n}>Enter the {n}, then reconnect it in Connection Fabric.</li>)}</ul>
            </>
          )}
          <p className="note">Review and publish the workflows and decision flows when they are ready.</p>
        </div>
      ) : (
        <>
          <p className="note" style={{ marginTop: 0 }}>
            Choose a pack exported from another org unit. You see what it will create before anything changes. A pack never holds passwords, keys or tokens.
          </p>
          <label htmlFor="org-pack-file">Pack file (JSON)</label>
          <input id="org-pack-file" type="file" accept=".json,application/json" disabled={action.pending} onChange={(e) => void choose(e.target.files?.[0])} />
          {err && <div className="note err" style={{ marginTop: 8 }}>{err}</div>}
          {preview && <Preview p={preview} name={name} />}
        </>
      )}
    </Modal>
  );
}

function Preview({ p, name }: { p: PackPreview; name: string }) {
  return (
    <div id="orgPackPreview" style={{ marginTop: 12 }}>
      <p className="note">From <b>{p.origin}</b> into <b>{name}</b>. This will create:</p>
      <div className="tw">
        <table className="t static tight">
          <thead><tr><th>What</th><th>Details</th></tr></thead>
          <tbody>
            <tr>
              <td>Sources ({p.sources.length})</td>
              <td>{p.sources.length ? p.sources.map((s) => s.name + ' (' + s.vendor + ') as ' + s.new_id).join('; ') : 'None'}. Each starts disconnected, without credentials.</td>
            </tr>
            <tr><td>Field mappings ({p.mappings.length})</td><td>{p.mappings.join(', ') || 'None'}</td></tr>
            <tr>
              <td>Workflows ({p.workflows.length})</td>
              <td>{p.workflows.length ? p.workflows.map((w) => w.name ?? 'Unnamed').join('; ') : 'None'}. Each is a draft.</td>
            </tr>
            <tr>
              <td>Decision flows ({p.flows.length})</td>
              <td>{p.flows.length ? p.flows.map((f) => f.template + (f.fork ? ' (a new flow for ' + name + ')' : ' (a new draft of its flow)')).join('; ') : 'None'}. Nothing is published.</td>
            </tr>
          </tbody>
        </table>
      </div>
      {p.needs.length > 0 && <p className="note">After the import, enter the {p.needs.join(', ')}.</p>}
    </div>
  );
}
