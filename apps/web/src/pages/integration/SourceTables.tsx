/* Source Tables: the table graph with clusters and foreign keys, a list view, and add / edit / delete / link (tables.update). */
import { useEffect, useRef, useState } from 'react';
import { useBackend } from '../../api/useBackend';
import {
  alignTables, moveTable, source, sources, srcAgeText, tableCount, tableHeight, tableModel, tableModelIds, tableSuggestions, undoActions, updateTables,
  type Table, type TableModel,
} from '../../api/integration';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { canMgr, FrKpi, NOMGR, sum, toastAct } from './ui';

const tg = { src: 'erp', view: 'graph' as 'graph' | 'list', z: 0.85 };
const W = 190;

export function TablesTiles() {
  const S = sources(), tbl = sum(S.map((s) => tableCount(s.id))), sys = S.filter((s) => tableCount(s.id)).length;
  const fk = sum(S.map((s) => tableModel(s.id)?.fk.length ?? 0));
  return (
    <div className="frkpis fr3">
      <FrKpi ic="database" h="money" v={tbl} l="Tables modelled" />
      <FrKpi ic="link" h="dec" v={fk} l="Links between tables" />
      <FrKpi ic="graph" h="int" v={sys} l="Systems with a table model" />
    </div>
  );
}

function size(m: TableModel) {
  let w = 900, h = 500;
  m.t.forEach((t) => { w = Math.max(w, t.x + W + 80); h = Math.max(h, t.y + tableHeight(t) + 80); });
  return { w, h };
}
function anchor(a: Table, b: Table): [[number, number], [number, number]] {
  const ah = tableHeight(a), bh = tableHeight(b);
  if (a.x + W + 20 <= b.x) return [[a.x + W, a.y + ah / 2], [b.x, b.y + bh / 2]];
  if (b.x + W + 20 <= a.x) return [[a.x, a.y + ah / 2], [b.x + W, b.y + bh / 2]];
  return a.y < b.y ? [[a.x + W / 2, a.y + ah], [b.x + W / 2, b.y]] : [[a.x + W / 2, a.y], [b.x + W / 2, b.y + bh]];
}

type Dlg = { k: 'edit'; n: string } | { k: 'add' } | { k: 'fk'; a: string } | null;

export function Tables() {
  useBackend();
  const [, setV] = useState(0);
  const up = (f: () => void) => { f(); setV((x) => x + 1); };
  const [dlg, setDlg] = useState<Dlg>(null);
  if (!source(tg.src) || !tableModelIds().includes(tg.src)) tg.src = tableModelIds().find((k) => source(k)) ?? '';
  if (!tg.src) return <div className="empty"><b>No table models</b>Connect a source that publishes tables first.</div>;
  const m = tableModel(tg.src)!;
  const mgr = canMgr();
  const del = async (n: string) => {
    if (!mgr) return toast(NOMGR);
    const r = await updateTables({ src: tg.src, op: 'delete', name: n });
    if (!r.ok) return toast(r.error.message);
    setDlg(null);
    toastAct(n + ' deleted' + (r.output.fks ? ' with ' + r.output.fks + ' foreign key' + (r.output.fks > 1 ? 's' : '') : '') + '.', 'Undo', () => undoActions([r.seq!]));
  };
  const fkDel = async (i: number) => {
    if (!mgr) return toast(NOMGR);
    const r = await updateTables({ src: tg.src, op: 'fkDel', index: i });
    if (!r.ok) return toast(r.error.message);
    toastAct(r.output.from + ' → ' + r.output.to + ' removed.', 'Undo', () => undoActions([r.seq!]));
  };
  const fkNew = (a: string) => {
    if (!mgr) return toast(NOMGR);
    if (m.t.length < 2) return toast('Add a second table before linking.');
    setDlg({ k: 'fk', a: a || m.t[0].n });
  };
  return (
    <>
      <div className="smbar">
        <label className="sr" htmlFor="tgSrc">System</label>
        <select className="sel" id="tgSrc" style={{ maxWidth: 320 }} value={tg.src} onChange={(e) => up(() => { tg.src = e.target.value; })}>
          {tableModelIds().map((id) => { const s = source(id); return s ? <option key={id} value={id}>{s.name} · {s.vendor}</option> : null; })}
        </select>
        <span className="chip line">{m.t.length} tables</span>
        <span className="chip line">{m.fk.length} foreign keys</span>
        <span className="grow" />
        <div className="seg" role="group" aria-label="View">
          <button aria-pressed={tg.view === 'graph'} onClick={() => up(() => { tg.view = 'graph'; })}>Graph</button>
          <button aria-pressed={tg.view === 'list'} onClick={() => up(() => { tg.view = 'list'; })}>List</button>
        </div>
        {mgr && <><button className="btn" onClick={() => setDlg({ k: 'add' })}>Add Tables</button><button className="btn pri" onClick={() => fkNew('')}>New Foreign Key</button></>}
      </div>
      <p className="note" style={{ margin: '0 0 10px' }}>
        The tables Circularity reads from this system and how they link. Hover a table, a field or a link to see what it is and why it is used. Drag a table by its header to rearrange.
      </p>
      {tg.view === 'graph' ? <TableGraph m={m} up={up} onEdit={(n) => setDlg({ k: 'edit', n })} onFk={fkNew} /> : <TableList m={m} onEdit={(n) => setDlg({ k: 'edit', n })} onFk={fkNew} onDel={del} onFkDel={fkDel} />}
      {dlg?.k === 'edit' && <EditTable m={m} n={dlg.n} onClose={() => setDlg(null)} onDel={del} />}
      {dlg?.k === 'add' && <AddTable m={m} onClose={() => setDlg(null)} />}
      {dlg?.k === 'fk' && <NewFk m={m} a0={dlg.a} onClose={() => setDlg(null)} />}
    </>
  );
}

function TableGraph({ m, up, onEdit, onFk }: { m: TableModel; up: (f: () => void) => void; onEdit: (n: string) => void; onFk: (n: string) => void }) {
  const drag = useRef<{ t: Table; sx: number; sy: number; ox: number; oy: number } | null>(null);
  useEffect(() => {
    const mv = (e: PointerEvent) => {
      const d = drag.current;
      if (!d) return;
      moveTable(tg.src, d.t.n, Math.max(0, Math.round((d.ox + (e.clientX - d.sx) / tg.z) / 8) * 8), Math.max(30, Math.round((d.oy + (e.clientY - d.sy) / tg.z) / 8) * 8));
    };
    const end = () => { drag.current = null; };
    document.addEventListener('pointermove', mv);
    document.addEventListener('pointerup', end);
    return () => { document.removeEventListener('pointermove', mv); document.removeEventListener('pointerup', end); };
  }, []);
  const { w, h } = size(m), by: Record<string, Table> = {};
  m.t.forEach((t) => { by[t.n] = t; });
  const zoom = (a: number) => up(() => { tg.z = Math.max(0.3, Math.min(1.4, Math.round((tg.z + a * 0.1) * 10) / 10)); });
  return (
    <div className="tgwrap">
      <div className="tgview" id="tgView" role="group" aria-label="Table graph. Drag a table by its header to move it.">
        <div id="tgSizer" style={{ width: w * tg.z, height: h * tg.z }}>
          <div id="tgWorld" style={{ width: w, height: h, transform: `scale(${tg.z})` }}>
            {m.cl.map(([id, name]) => {
              const ts = m.t.filter((t) => t.cl === id);
              if (!ts.length) return null;
              const x1 = Math.min(...ts.map((t) => t.x)) - 14, y1 = Math.min(...ts.map((t) => t.y)) - 34, x2 = Math.max(...ts.map((t) => t.x + W)) + 14, y2 = Math.max(...ts.map((t) => t.y + tableHeight(t))) + 14;
              return <div key={id} className="tgcl" style={{ left: x1, top: y1, width: x2 - x1, height: y2 - y1 }}><span className="tgcn">{name}</span></div>;
            })}
            <svg className="tgsv" width={w} height={h} aria-hidden="true">
              {m.fk.map((f, i) => {
                const a = by[f[0].split('.')[0]], b = by[f[1].split('.')[0]];
                if (!a || !b) return null;
                const [p, q] = anchor(a, b), hz = Math.abs(q[0] - p[0]) >= Math.abs(q[1] - p[1]), mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2;
                const d = hz ? `M${p[0]} ${p[1]}C${mx} ${p[1]} ${mx} ${q[1]} ${q[0]} ${q[1]}` : `M${p[0]} ${p[1]}C${p[0]} ${my} ${q[0]} ${my} ${q[0]} ${q[1]}`;
                return (
                  <g className="tgl" key={i}>
                    <path className="hit" d={d} data-tip={f[0] + ' → ' + f[1] + ' · ' + (f[2] || 'Foreign key link')}><title>{f[0] + ' → ' + f[1] + ' · ' + (f[2] || 'Foreign key link')}</title></path>
                    <path className="l" d={d} /><circle cx={p[0]} cy={p[1]} r="3.5" /><circle cx={q[0]} cy={q[1]} r="3.5" />
                  </g>
                );
              })}
            </svg>
            {m.t.map((t) => (
              <div key={t.n} className="tgc" data-t={t.n} style={{ left: t.x, top: t.y, width: W }}>
                <div className="tgh" data-tip={t.n + ' · ' + t.desc} title={t.desc}
                  onPointerDown={(e) => { if ((e.target as HTMLElement).closest('button')) return; drag.current = { t, sx: e.clientX, sy: e.clientY, ox: t.x, oy: t.y }; e.preventDefault(); }}>
                  <b>{t.n}</b>
                  {canMgr() && <button className="tgm" aria-label={'Edit table ' + t.n} onClick={() => onEdit(t.n)}>⋮</button>}
                </div>
                <div className="tgcols">
                  {t.cols.slice(0, 4).map((c) => <div key={c[0]} className="tgcol" data-tip={t.n + '.' + c[0] + ' · ' + (c[1] || 'Field read by the extractor')} title={c[1] || 'Field read by the extractor'}><span>{c[0]}</span><i /></div>)}
                  {t.cols.length > 4 && <div className="tgmore">+{t.cols.length - 4} more</div>}
                </div>
                {canMgr() && <button className="tgfk" onClick={() => onFk(t.n)}>New Foreign Key</button>}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="tgctl">
        {canMgr() && <button className="btn sm" onClick={() => { alignTables(tg.src); toast('Tables aligned by cluster.'); }}>Auto Align</button>}
        <button className="btn sm" aria-label="Zoom out" onClick={() => zoom(-1)}>−</button>
        <span id="tgZ" className="note num" style={{ width: 40, textAlign: 'center' }}>{Math.round(tg.z * 100)}%</span>
        <button className="btn sm" aria-label="Zoom in" onClick={() => zoom(1)}>+</button>
      </div>
    </div>
  );
}

function TableList({ m, onEdit, onFk, onDel, onFkDel }: { m: TableModel; onEdit: (n: string) => void; onFk: (n: string) => void; onDel: (n: string) => void; onFkDel: (i: number) => void }) {
  const s = source(tg.src)!, mgr = canMgr();
  const fkc = (n: string) => m.fk.filter((f) => f[0].split('.')[0] === n || f[1].split('.')[0] === n).length;
  return (
    <>
      <div className="panel">
        <div className="tw">
          <table className="t">
            <thead><tr><th>Table</th><th>Cluster</th><th>What it is and why it is used</th><th className="r">Columns</th><th className="r">Foreign keys</th><th className="r">Rows</th><th>Last extracted</th>{mgr && <th>Actions</th>}</tr></thead>
            <tbody>
              {m.t.map((t) => (
                <tr key={t.n}>
                  <td className="mono"><b>{t.n}</b></td>
                  <td><span className="chip line">{(m.cl.find((c) => c[0] === t.cl) || ['', t.cl])[1].replace(/ Tables$/, '')}</span></td>
                  <td style={{ maxWidth: 420 }}>{t.desc}</td>
                  <td className="r num">{t.cols.length}</td>
                  <td className="r num">{fkc(t.n)}</td>
                  <td className="r num">{t.rows || '—'}</td>
                  <td className="nowrap note"><span>{srcAgeText(s).replace(/^(Updated|Last import) /, '')}</span></td>
                  {mgr && (
                    <td className="nowrap">
                      <span className="tacts" style={{ display: 'inline-flex' }}>
                        <button className="tbtn" onClick={() => onEdit(t.n)}>Edit</button>
                        <button className="tbtn" onClick={() => onFk(t.n)}>Link</button>
                        <button className="tbtn dng" onClick={() => onDel(t.n)}>Delete</button>
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="sect">
        <div className="sh"><h2>Foreign keys</h2></div>
        <div className="panel">
          <div className="tw">
            <table className="t static">
              <thead><tr><th>From</th><th>To</th><th>Why the link matters</th>{mgr && <th>Actions</th>}</tr></thead>
              <tbody>
                {m.fk.length ? m.fk.map((f, i) => (
                  <tr key={i}><td className="mono">{f[0]}</td><td className="mono">{f[1]}</td><td>{f[2] || 'Foreign key link'}</td>{mgr && <td><button className="tbtn dng" onClick={() => onFkDel(i)}>Delete</button></td>}</tr>
                )) : <tr><td colSpan={4}><div className="empty"><b>No foreign keys</b>Use New Foreign Key to link two tables.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

function EditTable({ m, n, onClose, onDel }: { m: TableModel; n: string; onClose: () => void; onDel: (n: string) => void }) {
  const t = m.t.find((x) => x.n === n)!;
  const [desc, setDesc] = useState(t.desc), [cl, setCl] = useState(t.cl), [cols, setCols] = useState(t.cols.map((c) => c[0]).join('\n')), [err, setErr] = useState('');
  const save = async () => {
    if (!canMgr()) return toast(NOMGR);
    const l = cols.split('\n').map((x) => x.trim()).filter(Boolean);
    if (!l.length) return setErr('Add at least one column.');
    if (new Set(l.map((c) => c.toLowerCase())).size !== l.length) return setErr('Column names must be unique.');
    if (l.some((c) => !/^[A-Za-z_][\w$]*$/.test(c))) return setErr('Use letters, numbers and underscores only.');
    const r = await updateTables({ src: tg.src, op: 'edit', name: n, table: { cols: l, desc: desc.trim(), cl } });
    if (!r.ok) return setErr(r.error.message);
    onClose();
    toast(n + ' saved.');
  };
  return (
    <Modal title={'Edit table ' + n} onClose={onClose} foot={<>
      <button className="btn danger" style={{ marginRight: 'auto' }} onClick={() => onDel(n)}>Delete table</button>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn pri" onClick={save}>Save table</button>
    </>}>
      <div className="fld"><label htmlFor="teDesc">What it is and why it is used</label><textarea id="teDesc" maxLength={220} value={desc} onChange={(e) => setDesc(e.target.value)} /><div className="hint">Shown when someone hovers the table. Keep it to a line or two.</div></div>
      <div className="fld"><label htmlFor="teCl">Cluster</label><select id="teCl" value={cl} onChange={(e) => setCl(e.target.value)}>{m.cl.map((c) => <option key={c[0]} value={c[0]}>{c[1]}</option>)}</select></div>
      <div className="fld"><label htmlFor="teCols">Columns (one per line, key first)</label><textarea id="teCols" className="mono" style={{ minHeight: 120 }} spellCheck={false} value={cols} onChange={(e) => setCols(e.target.value)} /><div className="err" id="teErr">{err}</div></div>
    </Modal>
  );
}

function AddTable({ m, onClose }: { m: TableModel; onClose: () => void }) {
  const av = tableSuggestions(tg.src).filter((a) => !m.t.some((t) => t.n === a.n));
  const [n, setN] = useState(''), [cl, setCl] = useState(m.cl[0]?.[0] ?? ''), [desc, setDesc] = useState(''), [cols, setCols] = useState('ID'), [err, setErr] = useState('');
  const onName = (v: string) => {
    setN(v);
    const a = tableSuggestions(tg.src).find((x) => x.n.toLowerCase() === v.trim().toLowerCase());
    if (a) { setDesc(a.desc); setCl(a.cl); setCols(a.cols.join('\n')); }
  };
  const add = async () => {
    const name = n.trim(), l = cols.split('\n').map((x) => x.trim()).filter(Boolean);
    if (!/^[A-Za-z][\w$]{1,40}$/.test(name)) return setErr('Enter a table name: letters, numbers and underscores.');
    if (m.t.some((t) => t.n.toLowerCase() === name.toLowerCase())) return setErr(name + ' is already in this model.');
    if (!l.length || l.some((c) => !/^[A-Za-z_][\w$]*$/.test(c))) return setErr('Add at least one valid column name.');
    const mem = m.t.filter((t) => t.cl === cl), x = mem.length ? Math.max(...mem.map((t) => t.x)) : 24;
    const y = mem.length ? Math.max(...mem.map((t) => t.y + tableHeight(t))) + 30 : m.t.length ? Math.max(...m.t.map((t) => t.y + tableHeight(t))) + 60 : 60;
    const r = await updateTables({ src: tg.src, op: 'add', table: { n: name, cl, desc: desc.trim() || 'Table extracted for evidence.', cols: l.map((c) => [c, '']), rows: '—', x: mem.length ? x : 24, y } });
    if (!r.ok) return setErr(r.error.message);
    onClose();
    toast(name + ' added. Use New Foreign Key to link it to other tables.');
  };
  return (
    <Modal title="Add table" onClose={onClose} foot={<><button className="btn ghost" onClick={onClose}>Cancel</button><button className="btn pri" onClick={add}>Add table</button></>}>
      <div className="fld">
        <label htmlFor="taN">Table name</label>
        <input id="taN" list="taL" autoComplete="off" spellCheck={false} value={n} onChange={(e) => onName(e.target.value)} />
        <datalist id="taL">{av.map((a) => <option key={a.n} value={a.n} />)}</datalist>
        <div className="hint">{av.length ? 'Suggestions appear as you type. ' : ''}Any table the extractor can read can be added.</div>
      </div>
      <div className="fld"><label htmlFor="taC">Cluster</label><select id="taC" value={cl} onChange={(e) => setCl(e.target.value)}>{m.cl.map((c) => <option key={c[0]} value={c[0]}>{c[1]}</option>)}</select></div>
      <div className="fld"><label htmlFor="taD">What it is and why it is used</label><textarea id="taD" maxLength={220} value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
      <div className="fld"><label htmlFor="taK">Columns (one per line, key first)</label><textarea id="taK" className="mono" style={{ minHeight: 90 }} spellCheck={false} value={cols} onChange={(e) => setCols(e.target.value)} /><div className="err" id="taErr">{err}</div></div>
    </Modal>
  );
}

function NewFk({ m, a0, onClose }: { m: TableModel; a0: string; onClose: () => void }) {
  const cols = (n: string) => (m.t.find((t) => t.n === n) || { cols: [] as [string, string][] }).cols.map((c) => c[0]);
  const [f, setF] = useState({ a: a0, ac: '', b: '', bc: '', why: '' });
  const [err, setErr] = useState('');
  const a = m.t.some((t) => t.n === f.a) ? f.a : m.t[0].n;
  const b = f.b && f.b !== a && m.t.some((t) => t.n === f.b) ? f.b : (m.t.find((t) => t.n !== a) || { n: '' }).n;
  const ac = cols(a).includes(f.ac) ? f.ac : cols(a)[0], bc = cols(b).includes(f.bc) ? f.bc : cols(b)[0];
  const sl = (k: 'a' | 'ac' | 'b' | 'bc', l: string, opts: string[], cur: string) => (
    <div className="fld">
      <label htmlFor={'fk_' + k}>{l}</label>
      <select id={'fk_' + k} value={cur} onChange={(e) => {
        const n = { ...f, a, b, ac, bc, [k]: e.target.value };
        if (k === 'a') { n.ac = ''; n.b = ''; }
        if (k === 'b') n.bc = '';
        setF(n);
      }}>
        {opts.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  );
  const ok = async () => {
    if (a === b) return setErr('Choose two different tables.');
    const r = await updateTables({ src: tg.src, op: 'fkAdd', fk: [a + '.' + ac, b + '.' + bc, f.why.trim() || 'Foreign key link'] });
    if (!r.ok) return setErr(r.error.message);
    onClose();
    toast(a + '.' + ac + ' now links to ' + b + '.' + bc + '.');
  };
  return (
    <Modal title="New Foreign Key" onClose={onClose} foot={<><button className="btn ghost" onClick={onClose}>Cancel</button><button className="btn pri" onClick={ok}>Create foreign key</button></>}>
      <p className="note" style={{ marginTop: 0 }}>A foreign key links a column in one table to the key of another, so records can be joined.</p>
      <div className="grid g2" style={{ gap: '0 14px' }}>
        {sl('a', 'From table', m.t.map((t) => t.n), a)}
        {sl('ac', 'From column', cols(a), ac)}
        {sl('b', 'To table', m.t.filter((t) => t.n !== a).map((t) => t.n), b)}
        {sl('bc', 'To column', cols(b), bc)}
      </div>
      <div className="fld"><label htmlFor="fk_why">Why the link matters</label><input id="fk_why" maxLength={120} placeholder="e.g. An order item belongs to its header" value={f.why} onChange={(e) => setF({ ...f, why: e.target.value })} /></div>
      <div className="err" id="fkErr">{err}</div>
    </Modal>
  );
}
