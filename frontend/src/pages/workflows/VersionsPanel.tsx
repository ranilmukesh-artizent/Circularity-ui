/** The History tab's versions (plan 6 C8): every kept version with Compare (computed on the server) and Restore. */
import { Suspense, useState } from 'react';
import { can } from '../../api/session';
import {
  compareVersions, NOWF, publishedVersion, publishWorkflow, restoreVersion, versions, type VersionDiff, type Workflow,
} from '../../api/workflows';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { forget } from './draftStore';

const when = (at: string) => {
  const t = Date.parse(at);
  return Number.isNaN(t) ? at : new Date(t).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};
const show = (v: unknown): string => (v == null || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

export function VersionsPanel({ w, dirty }: { w: Workflow; dirty: boolean }) {
  const mgr = can('manageWorkflows');
  const action = useAction();
  const [cmp, setCmp] = useState<string | null>(null);
  const L = versions(w.id), pub = publishedVersion(w.id);

  async function restore(ver: string) {
    if (!mgr) return toast(NOWF());
    const r = await action.run(() => restoreVersion(w.id, ver), 4200);
    if (!r.ok) return;
    forget(w.id); // the canvas copy is rebuilt from the restored version
    setCmp(null);
    toast(`v${ver} restored as v${r.output.ver}.` + (dirty ? ' Your unsaved changes were dropped.' : '') + (pub ? ' Publish it to make runs use it.' : ''));
  }
  async function publish() {
    if (!mgr) return toast(NOWF());
    const r = await action.run(() => publishWorkflow(w.id), 4200);
    if (r.ok) toast(`v${r.output.ver} published. Runs now use it.`);
  }

  return (
    <Panel title="Versions" sub={pub ? `Runs use v${pub}. Saving makes a new version; publish it to make runs use it.` : 'Not published: Run now tries the saved version.'}>
      {!L.length ? <div className="empty"><b>No versions yet</b>Every save keeps a version here.</div> : (
        <div className="tw"><table className="t static tight" id="wfVersions">
          <thead><tr><th>Version</th><th>When</th><th>By</th><th>Note</th><th /><th /></tr></thead>
          <tbody>{L.map((v) => (
            <tr key={v.ver}>
              <td className="mono">v{v.ver} {v.current && <span className="chip line">Current</span>} {v.published && <span className="chip ok">Published</span>}</td>
              <td className="num nowrap">{when(v.at)}</td><td>{v.by}</td><td>{v.note}</td>
              <td>{!v.current && <button className="btn sm" aria-pressed={cmp === v.ver} onClick={() => setCmp(cmp === v.ver ? null : v.ver)}>Compare</button>}</td>
              <td>{mgr && !v.current && <button className="btn sm" onClick={() => restore(v.ver)}>Restore</button>}
                {mgr && v.current && w.status === 'published' && !v.published && <button className="btn sm pri" onClick={publish}>Publish</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      {cmp && (
        <Suspense fallback={<p className="note">Comparing…</p>}>
          <Compare id={w.id} a={cmp} />
        </Suspense>
      )}
    </Panel>
  );
}

function Compare({ id, a }: { id: string; a: string }) {
  const c: VersionDiff = compareVersions(id, a);
  const none = !c.blocks.added.length && !c.blocks.removed.length && !c.blocks.changed.length && !c.links.added.length && !c.links.removed.length && !c.settings.length;
  return (
    <div className="frcmp" id="wfCompare">
      <h4 style={{ margin: '14px 0 6px' }}>v{c.a} → v{c.b}</h4>
      {none && <p className="note">No differences in steps, links or settings (only positions on the canvas may differ).</p>}
      {c.blocks.added.length > 0 && <p><b>Added steps:</b> {c.blocks.added.map((x) => x.label).join(', ')}</p>}
      {c.blocks.removed.length > 0 && <p><b>Removed steps:</b> {c.blocks.removed.map((x) => x.label).join(', ')}</p>}
      {c.blocks.changed.length > 0 && (
        <div className="tw"><table className="t static tight">
          <thead><tr><th>Changed step</th><th>Setting</th><th>Was</th><th>Now</th></tr></thead>
          <tbody>{c.blocks.changed.flatMap((x) => x.fields.map((f, i) => (
            <tr key={x.id + f.field}><td>{i === 0 ? x.label : ''}</td><td className="mono">{f.field}</td><td>{show(f.from)}</td><td>{show(f.to)}</td></tr>
          )))}</tbody>
        </table></div>
      )}
      {(c.links.added.length > 0 || c.links.removed.length > 0) && (
        <p className="note">Links: {c.links.added.length} added, {c.links.removed.length} removed.</p>
      )}
      {c.settings.length > 0 && (
        <div className="tw"><table className="t static tight">
          <thead><tr><th>Workflow setting</th><th>Was</th><th>Now</th></tr></thead>
          <tbody>{c.settings.map((s) => <tr key={s.key}><td>{s.key}</td><td>{show(s.from)}</td><td>{show(s.to)}</td></tr>)}</tbody>
        </table></div>
      )}
    </div>
  );
}
