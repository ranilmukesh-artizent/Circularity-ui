import { Suspense, useId, useState } from 'react';
import type { ComposeSystem } from '../../../api/compose';
import { canReadTables, followSync, reloadTables, sourceTables, syncSource, type Table } from '../../../api/integration';
import { StatusPill } from '../../../components/kit/StatusPill';
import { toast } from '../../../components/toast';
import { refused } from '../../../hooks/useAction';
import { MappingSuggestions } from '../../integration/MappingSuggestions';
import { statusLabel, statusTone, summaryLine } from './composeView';
import { FIELD_RULE, partsOf, readingLine, rowsText, runUnits, selectionLine, tableKey, tickedTables, toggleTable, WHOLE_SOURCE, type Part } from './systemsView';
import './systems.css';

/**
 * One system of the "Connect your systems" step: its name, the three parts as a track (Connection, Data, Mapping), and under
 * it the part the person works on. The data part lists the tables the source has landed, each with a tick ("use this table") and
 * its fields; a source with none offers "Fetch a sample". The mapping part suggests canonical fields for the ticked tables, one
 * table at a time. Tables are what the source holds today (records it already landed), not a live call to the vendor.
 */
export function SystemRow({ x, editable, onAdd }: { x: ComposeSystem; editable: boolean; onAdd: () => void }) {
  return (
    <section className="sys" aria-label={x.name}>
      <header className="sys-head">
        <h4>{x.name}</h4>
        <span className="sys-type">{x.system_type}</span>
        <StatusPill tone={statusTone(x.status)} label={statusLabel(x.status)} />
        <span className="sys-src">{x.source_id ? <>Source <span className="mono">{x.source_id}</span></> : 'No source yet'}</span>
      </header>
      {x.source_id === null ? (
        <>
          <Track parts={partsOf(x, 0, 0, true)} />
          {x.status === 'needs_adapter' && editable && (
            <div className="sys-body"><button className="btn sm" onClick={onAdd}>Add from the adapter registry</button></div>
          )}
        </>
      ) : (
        <Suspense fallback={<p className="note sys-body" role="status">Reading the tables of {x.name}…</p>}>
          <Connected x={x} sourceId={x.source_id} editable={editable} onAdd={onAdd} />
        </Suspense>
      )}
    </section>
  );
}

function Track({ parts }: { parts: Part[] }) {
  return (
    <ol className="sys-track" aria-label="Parts of this system">
      {parts.map((p) => (
        <li key={p.name} data-state={p.state}>
          <span className="sys-dot" aria-hidden="true" />
          <span className="sys-pname">{p.name}</span>
          <span className="sys-pnote">{p.note}</span>
        </li>
      ))}
    </ol>
  );
}

function Connected({ x, sourceId, editable, onAdd }: { x: ComposeSystem; sourceId: string; editable: boolean; onAdd: () => void }) {
  const tables = sourceTables(sourceId);
  const canRead = canReadTables();
  const [ticked, setTicked] = useState<Set<string> | null>(null);
  const used = tickedTables(tables, ticked);
  const [run, setRun] = useState<{ n: number; step: number } | null>(null); // n: how many runs were asked, step: the table being read
  // records are known (the mapping summary counts their fields) though no table is modelled: one run over everything it sent
  const untabled = tables.length === 0 && x.mapping.fields > 0;
  const units = canRead && !untabled ? runUnits(used) : [WHOLE_SOURCE];
  const parts = partsOf(x, tables.length, used.length, canRead);

  return (
    <>
      <Track parts={parts} />
      {x.status === 'needs_adapter' && editable && <div className="sys-body"><button className="btn sm" onClick={onAdd}>Add from the adapter registry</button></div>}
      <div className="sys-body">
        <h5 className="sys-h">Data</h5>
        {!canRead ? (
          <p className="note">The tables of this system are shown to a person who manages integrations. You can still ask for suggestions on every table it sends.</p>
        ) : untabled ? (
          <p className="note">This system has sent records with {x.mapping.fields} fields, but they are not split into tables yet. Suggestions read everything it sent.</p>
        ) : tables.length === 0 ? (
          <NoSample sourceId={sourceId} />
        ) : (
          <TableList tables={tables} ticked={ticked} onToggle={(n) => { setRun(null); setTicked((t) => toggleTable(tables, t, n)); }} />
        )}
      </div>
      <div className="sys-body">
        <h5 className="sys-h">Mapping</h5>
        <p className="note">{summaryLine(x.mapping)}. Suggestions are proposals: you choose each field and nothing is saved until you save the mapping.</p>
        <p className="note">{FIELD_RULE}</p>
        <div className="sys-actions">
          <button
            className="btn sm"
            disabled={(canRead && !untabled && (tables.length === 0 || used.length === 0)) || (run !== null && run.step < units.length)}
            onClick={() => setRun({ n: (run?.n ?? 0) + 1, step: 0 })}
          >
            {run ? 'Suggest again' : 'Suggest canonical mappings'}
          </button>
          {run && run.step < units.length && <span className="note" role="status">{readingLine(run.step, units.length)}</span>}
          {canRead && tables.length > 0 && used.length === 0 && <span className="note">Tick at least one table.</span>}
        </div>
        {run && (
          <div className="sys-results">
            {units.slice(0, run.step + 1).map((u, i) => (
              <div key={run.n + ':' + u.key} className="sys-result">
                {units.length > 1 || u.resource ? <h6>{u.label}</h6> : null}
                <MappingSuggestions
                  sourceId={sourceId}
                  resource={u.resource}
                  autoRun
                  embedded
                  onSettled={() => setRun((r) => (r && r.n === run.n && r.step === i ? { n: r.n, step: r.step + 1 } : r))}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function NoSample({ sourceId }: { sourceId: string }) {
  const [busy, setBusy] = useState(false);
  const fetchSample = async () => {
    setBusy(true);
    const r = await syncSource(sourceId);
    if (refused(r, { silent: ['duplicate'] })) return setBusy(false);
    followSync(sourceId, (s) => {
      setBusy(false);
      reloadTables();
      toast(s.ok ? `Sample fetched: ${s.rows.toLocaleString('en-US')} records.` : 'The sample could not be fetched: ' + s.reason, s.ok ? undefined : 4200);
    });
  };
  return (
    <div className="sys-empty">
      <b>No tables yet</b>
      <p className="note">This source has not sent any records. Fetch a sample to see the tables and fields it holds.</p>
      <button className="btn sm" onClick={() => void fetchSample()} disabled={busy} aria-busy={busy}>{busy ? 'Fetching…' : 'Fetch a sample'}</button>
    </div>
  );
}

/** How many tables a long list shows before the person asks for all of them. */
const FEW = 6;

function TableList({ tables, ticked, onToggle }: { tables: Table[]; ticked: Set<string> | null; onToggle: (name: string) => void }) {
  const id = useId();
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const used = tickedTables(tables, ticked).length;
  const shown = all || tables.length <= FEW + 2 ? tables : tables.slice(0, FEW);
  return (
    <>
      <p className="sys-count" role="status">{selectionLine(used, tables.length)}</p>
      <ul className="sys-tables" aria-label="Tables">
        {shown.map((t, i) => {
          const k = tableKey(t);
          const on = ticked === null || ticked.has(k);
          const panel = `${id}-${i}`;
          return (
            <li key={k} className={on ? 'on' : undefined}>
              <div className="sys-trow">
                <label className="sys-use">
                  <input type="checkbox" checked={on} onChange={() => onToggle(k)} />
                  <span className="sys-tname mono">{t.n}</span>
                  <span className="sys-use-l">use this table</span>
                </label>
                <span className="sys-meta">{rowsText(t.rows)}</span>
                <span className="sys-meta">{t.cols.length} {t.cols.length === 1 ? 'field' : 'fields'}</span>
                <button className="btn ghost sm" aria-expanded={open === k} aria-controls={panel} onClick={() => setOpen(open === k ? null : k)}>
                  {open === k ? 'Hide fields' : 'Show fields'}
                </button>
              </div>
              {open === k && (
                <ul id={panel} className="sys-fields" aria-label={`Fields of ${t.n}`}>
                  {t.cols.map(([name, type]) => <li key={name}><span className="mono">{name}</span><span className="sys-ftype">{type}</span></li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {shown.length < tables.length && (
        <button className="btn ghost sm sys-more" onClick={() => setAll(true)}>Show all {tables.length} tables</button>
      )}
    </>
  );
}
