/**
 * The decision table editor in the Modeler's inspector (plan 9, P9-8.16, E §8.2 C). Owns: the grid of one pack table in one
 * market (cells, rules added and removed, first-hit order), the checks shown before save (`tableEdit.check`), the draft save and
 * "Test this decision". Never: approves, rejects or publishes: a saved draft goes through the Tables panel's submit and a
 * different person's approval (maker-checker, P9-4.2). Reads and writes only the marketTable.* actions, through api/modeler.ts.
 * Loaded lazily (FlowInspector); its styles are scoped under `.mdl-table-editor`.
 */
import { useState } from 'react';
import { decisionTable, saveDecisionTable, testDecisionTable } from '../../api/modeler';
import type { Jdm, MarketTable, TableTest } from '../../api/marketTables';
import { currentAccount } from '../../api/session';
import { useAction } from '../../hooks/useAction';
import { toast } from '../../components/toast';
import { blankRow, jdmToRows, rowsToJdm, tableLabel, type TableGrid } from './tables';
import { check, pickVersion, SAMPLE, typedInputs } from './tableEdit';

const FLOW = 'service_desk';

interface Props { pack: string; name: string; org: string }

export default function TableEditor({ pack, name, org }: Props) {
  const l = decisionTable(pack, FLOW);
  const markets = Object.keys(l.markets);
  const [market, setMarket] = useState(markets[0] ?? '');
  const me = currentAccount()?.id ?? '';
  const t = pickVersion(l.tables, market, name, me, org);
  return (
    <div className="mdl-table-editor" data-table-name={name}>
      <div className="mdl-row">
        <label htmlFor="mte-market">Market</label>
        <select id="mte-market" value={market} onChange={(e) => setMarket(e.target.value)}>
          {markets.map((m) => <option key={m} value={m}>{m} ({l.markets[m]})</option>)}
        </select>
      </div>
      {t && t.kind === 'decision_table' ? <Grid key={t.id} t={t} declared={l.inputs[name] ?? []} canEdit={l.can.edit} me={me} /> : <p className="note">No decision table {name} for {market}.</p>}
    </div>
  );
}

function Grid({ t, declared, canEdit, me }: { t: MarketTable; declared: string[]; canEdit: boolean; me: string }) {
  const action = useAction();
  const own = t.status === 'draft' && t.created_by === me;
  const [grid, setGrid] = useState<TableGrid>(() => jdmToRows(t.body as Jdm));
  const [from, setFrom] = useState('');
  const [err, setErr] = useState('');
  const [sample, setSample] = useState<Record<string, string>>(() => Object.fromEntries(declared.map((k) => [k, SAMPLE[k] ?? ''])));
  const [tested, setTested] = useState<TableTest | null>(null);
  const graph = rowsToJdm(t.body as Jdm, grid);
  const problems = check(graph, declared);
  const why = !canEdit ? 'Your role cannot draft tables.' : problems[0] ?? (!own && !from ? 'Pick the date the new version starts.' : '');
  const setCell = (row: number, side: 'inputs' | 'outputs', col: number, v: string) =>
    setGrid((g) => ({ ...g, rows: g.rows.map((r, i) => (i === row ? { ...r, [side]: r[side].map((c, j) => (j === col ? v : c)) } : r)) }));
  const save = async () => {
    setErr('');
    const r = await action.run(() => saveDecisionTable(t, graph, own && !from ? t.valid_from : from, own), { all: setErr, ms: 4200 });
    if (r.ok && r.output.log) toast(r.output.log + '.');
  };
  const test = async () => {
    setErr('');
    const r = await action.run(() => testDecisionTable(t.id, typedInputs(sample)), { all: setErr, ms: 4200 });
    if (r.ok) setTested(r.output);
  };
  return (
    <div className="mdl-prop" data-table-editor={t.id}>
      <span className="label">{tableLabel(t)} · {t.status}{own ? ' (your draft)' : ''}</span>
      <table className="tbl" data-table-grid>
        <thead>
          <tr>{[...grid.inputs, ...grid.outputs].map((c, i) => <th key={c} className={i < grid.inputs.length ? '' : 'out'}>{c}</th>)}<th /></tr>
        </thead>
        <tbody>
          {grid.rows.map((r, ri) => (
            <tr key={r.id} data-matched={tested?.matched.includes(r.id) ? 'true' : undefined}>
              {r.inputs.map((c, ci) => <td key={'i' + ci}><input aria-label={`${r.id} ${grid.inputs[ci]}`} disabled={!canEdit} value={c} onChange={(e) => setCell(ri, 'inputs', ci, e.target.value)} /></td>)}
              {r.outputs.map((c, ci) => <td key={'o' + ci}><input aria-label={`${r.id} ${grid.outputs[ci]}`} disabled={!canEdit} value={c} onChange={(e) => setCell(ri, 'outputs', ci, e.target.value)} /></td>)}
              <td><button className="btn sm ghost" disabled={!canEdit} onClick={() => setGrid({ ...grid, rows: grid.rows.filter((_, i) => i !== ri) })}>Remove {r.id}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="btn sm" disabled={!canEdit} onClick={() => setGrid({ ...grid, rows: [...grid.rows, blankRow(grid)] })}>Add a rule</button>
      <p className="note">The first rule that matches decides. An empty input matches anything.</p>
      {problems.length > 0 && <ul className="mdl-msg blk" data-table-checks>{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      <div className="mdl-row">
        <label htmlFor="mte-from">Starts on</label>
        <input id="mte-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <button className="btn sm pri" disabled={action.pending || !!why} title={why} onClick={save}>{own ? 'Save draft' : 'Save as new version'}</button>
      </div>
      <p className="note">A saved draft is submitted from the Market tables panel and approved by a different person.</p>
      <div className="mdl-row" data-table-sample>
        {declared.map((k) => (
          <label key={k}>{k}{' '}
            <input aria-label={`Test ${k}`} style={{ width: 80 }} value={sample[k] ?? ''} onChange={(e) => setSample({ ...sample, [k]: e.target.value })} />
          </label>
        ))}
        <button className="btn sm" disabled={action.pending} onClick={test}>Test this decision</button>
      </div>
      {tested && (
        <p className="note" data-table-test>
          {JSON.stringify(tested.outputs)}{tested.matched.length ? ` · matched row ${tested.matched.join(', ')}` : ''}
        </p>
      )}
      {err && <p className="mdl-msg blk" role="alert" data-table-refusal>{err}</p>}
    </div>
  ); // prettier-ignore
}
