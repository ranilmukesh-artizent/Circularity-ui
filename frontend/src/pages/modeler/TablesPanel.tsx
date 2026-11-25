import { Suspense, useState } from 'react';
import {
  approveMarketTable, rejectMarketTable, saveMarketTable, submitMarketTable, testMarketTable, useMarketTables,
  type Jdm, type MarketTable, type MarketTableList, type TableStatus, type TableTest,
} from '../../api/marketTables'; // prettier-ignore
import { currentAccount } from '../../api/session';
import type { ActionResult, ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { blankRow, jdmToRows, rowsToJdm, tableLabel, valuesFromText, type TableGrid } from './tables';

const FLOW = 'service_desk';
const MIN_REASON = 15;
const STATUS: Record<TableStatus, string> = { draft: 'Draft', submitted: 'Submitted', approved: 'In force', rejected: 'Rejected', retired: 'Retired' };
const MAKER_CHECKER = 'Maker-checker: you changed this table, so you cannot approve it.';

/** When a version is in force, e.g. "from 2026-10-01" or "2026-09-01 to 2026-09-30". */
const dates = (t: Pick<MarketTable, 'valid_from' | 'valid_to'>): string => (t.valid_to ? `${t.valid_from} to ${t.valid_to}` : `from ${t.valid_from}`);

/**
 * Per-market rate cards and decision tables (plan 9, P9-4.2, story SD-03), for the tool fleet template. Pick a market, open a
 * version, change a rate card's values or a decision table's rows (first hit order), test it, then save a draft and submit it; a
 * different person approves or rejects it (maker-checker). Each button that cannot be pressed says why. Computed rules, not language.
 */
export function TablesPanel({ s }: { s: ModelerScreen }) {
  return (
    <Suspense fallback={<p className="note">Loading market tables.</p>}>
      <Tables pack={s.template.key} org={s.org} />
    </Suspense>
  );
}

function Tables({ pack, org }: { pack: string; org: string }) {
  const l = useMarketTables(pack, FLOW);
  const markets = Object.keys(l.markets);
  const [market, setMarket] = useState(markets[0] ?? '');
  const [openId, setOpenId] = useState<number | null>(null);
  if (markets.length === 0) return null;
  const mine = l.tables.filter((t) => t.market === market && (t.org_unit_id === null || t.org_unit_id === org));
  const sel = mine.find((t) => t.id === openId) ?? null;
  return (
    <div className="mdl-main mdl-lower" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <Panel title="Market tables" sub={`${org} · rate cards and decision tables per market, each change approved by a different person`} cls="mdl-tables">
        <div className="mdl-row">
          <label htmlFor="mt-market">Market</label>
          <select id="mt-market" value={market} onChange={(e) => { setMarket(e.target.value); setOpenId(null); }}>
            {markets.map((m) => <option key={m} value={m}>{m} ({l.markets[m]})</option>)}
          </select>
        </div>
        <ul className="mdl-hist" data-market-tables>
          {mine.map((t) => (
            <li key={t.id}>
              <button className="btn sm ghost" aria-pressed={t.id === openId} onClick={() => setOpenId(t.id === openId ? null : t.id)}>{tableLabel(t)}</button>{' '}
              <span className={'pill mdl-st ' + (t.status === 'approved' ? 'pub' : t.status)} data-table-status={t.status}>{STATUS[t.status]}</span>
              <span className="note"> {dates(t)} · {t.org_unit_id ?? 'shared'} · made by {t.created_by}{t.approved_by ? ` · approved by ${t.approved_by}` : ''}{t.reason ? ` · ${t.reason}` : ''}</span>
            </li>
          ))}
        </ul>
        {mine.length === 0 && <p className="note">No tables for {market}.</p>}
        {sel && <Editor key={sel.id} t={sel} l={l} />}
      </Panel>
    </div>
  ); // prettier-ignore
}

function Editor({ t, l }: { t: MarketTable; l: MarketTableList }) {
  const me = currentAccount()?.id ?? '';
  const action = useAction();
  const [err, setErr] = useState('');
  const [from, setFrom] = useState('');
  const [typed, setTyped] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(t.body.values ?? {}).map(([k, v]) => [k, String(v)])));
  const [grid, setGrid] = useState<TableGrid | null>(() => (t.kind === 'decision_table' ? jdmToRows(t.body as Jdm) : null));
  const [reason, setReason] = useState('');
  const [inputs, setInputs] = useState('{}');
  const [tested, setTested] = useState<TableTest | null>(null);
  const go = async (call: () => Promise<ActionResult<{ log?: string }>>) => {
    setErr('');
    const r = await action.run(call, { all: setErr, ms: 4200 });
    if (r.ok && r.output.log) toast(r.output.log + '.');
    return r.ok;
  };
  const ownDraft = t.status === 'draft' && t.created_by === me;
  const values = valuesFromText(typed);
  const rateOk = Object.values(values).every((v) => v !== null);
  const saveWhy = !l.can.edit ? 'Your role cannot draft tables.' : !from && !ownDraft ? 'Pick the date the new version starts.' : t.kind === 'rate_card' && !rateOk ? 'Every rate must be a number.' : '';
  const submitWhy = !l.can.edit ? 'Your role cannot submit tables.' : t.status !== 'draft' ? 'Only a draft is submitted.' : '';
  const approveWhy = !l.can.approve ? 'Your role cannot approve tables.' : t.status !== 'submitted' ? 'Only a submitted version is approved.' : [t.created_by, t.submitted_by].includes(me) ? MAKER_CHECKER : '';
  const rejectWhy = !l.can.approve ? 'Your role cannot reject tables.' : t.status !== 'submitted' ? 'Only a submitted version is rejected.' : reason.trim().length < MIN_REASON ? 'Add a reason of 15 characters or more.' : '';
  const body = (): object => (grid ? rowsToJdm(t.body as Jdm, grid) : { values });
  const save = () =>
    go(() => saveMarketTable({ pack: t.pack, flow: t.flow, market: t.market, name: t.name, kind: t.kind, valid_from: ownDraft && !from ? t.valid_from : from, ...(t.org_unit_id ? { org_unit_id: t.org_unit_id } : {}), body: body(), ...(ownDraft ? { id: t.id } : {}) })); // prettier-ignore
  const runTest = async () => {
    setErr('');
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(inputs) as Record<string, unknown>;
    } catch {
      setErr('The test inputs are not valid JSON.');
      return;
    }
    const r = await action.run(() => testMarketTable(t.id, parsed), { all: setErr, ms: 4200 });
    if (r.ok) setTested(r.output);
  };
  const setCell = (row: number, side: 'inputs' | 'outputs', col: number, v: string) =>
    setGrid((g) => g && { ...g, rows: g.rows.map((r, i) => (i === row ? { ...r, [side]: r[side].map((c, j) => (j === col ? v : c)) } : r)) });
  return (
    <div className="mdl-prop" data-table-editor={t.id}>
      <span className="label">{tableLabel(t)} · {t.currency ?? ''} · {dates(t)}</span>
      {t.kind === 'rate_card' && (
        <div className="mdl-row">
          {Object.keys(typed).map((k) => (
            <label key={k}>{k}{' '}
              <input aria-label={k} value={typed[k]} style={{ width: 80 }} onChange={(e) => setTyped({ ...typed, [k]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      {grid && (
        <>
          <table className="tbl" data-table-grid>
            <thead>
              <tr>{[...grid.inputs, ...grid.outputs].map((c, i) => <th key={c} className={i < grid.inputs.length ? '' : 'out'}>{c}</th>)}<th /></tr>
            </thead>
            <tbody>
              {grid.rows.map((r, ri) => (
                <tr key={r.id}>
                  {r.inputs.map((c, ci) => <td key={'i' + ci}><input aria-label={`${r.id} ${grid.inputs[ci]}`} value={c} onChange={(e) => setCell(ri, 'inputs', ci, e.target.value)} /></td>)}
                  {r.outputs.map((c, ci) => <td key={'o' + ci}><input aria-label={`${r.id} ${grid.outputs[ci]}`} value={c} onChange={(e) => setCell(ri, 'outputs', ci, e.target.value)} /></td>)}
                  <td><button className="btn sm ghost" onClick={() => setGrid({ ...grid, rows: grid.rows.filter((_, i) => i !== ri) })}>Remove {r.id}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn sm" onClick={() => setGrid({ ...grid, rows: [...grid.rows, blankRow(grid)] })}>Add a rule</button>
          <p className="note">The first rule that matches decides. An empty input matches anything.</p>
        </>
      )}
      <div className="mdl-row">
        <label htmlFor="mt-from">Starts on</label>
        <input id="mt-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <button className="btn sm pri" disabled={action.pending || !!saveWhy} title={saveWhy} onClick={save}>{ownDraft ? 'Save draft' : 'Save as new version'}</button>
        <button className="btn sm" disabled={action.pending || !!submitWhy} title={submitWhy} onClick={() => go(() => submitMarketTable(t.id))}>Submit</button>
        <button className="btn sm pri" disabled={action.pending || !!approveWhy} title={approveWhy} onClick={() => go(() => approveMarketTable(t.id))}>Approve</button>
        <label className="sr" htmlFor="mt-reason">Reason</label>
        <input id="mt-reason" value={reason} placeholder="Reason to reject (15 characters or more)" style={{ width: 240 }} onChange={(e) => setReason(e.target.value)} />
        <button className="btn sm" disabled={action.pending || !!rejectWhy} title={rejectWhy} onClick={() => go(() => rejectMarketTable(t.id, reason.trim()))}>Reject</button>
      </div>
      <p className="note" data-table-why>{[saveWhy, submitWhy, approveWhy].filter(Boolean).join(' ')}</p>
      <div className="mdl-row">
        <label htmlFor="mt-test">Test inputs (JSON)</label>
        <input id="mt-test" value={inputs} style={{ width: 360 }} onChange={(e) => setInputs(e.target.value)} />
        <button className="btn sm" disabled={action.pending} onClick={runTest}>Test</button>
      </div>
      {tested && (
        <p className="note" data-table-test>
          {JSON.stringify(tested.outputs)}{tested.trace.length ? ` · ${tested.trace.join('; ')}` : ''}
        </p>
      )}
      {err && <p className="mdl-msg blk" role="alert" data-table-refusal>{err}</p>}
    </div>
  ); // prettier-ignore
}
