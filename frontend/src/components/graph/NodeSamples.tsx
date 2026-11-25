/**
 * What went into and out of one node, for the Studio's and the Modeler's inspectors (P9-8.15). Owns the tabs Input,
 * Output and Held, the Table / JSON switch (JSON through the kit's JsonView) and the "Pin this input" button. Never
 * fetches, masks or stores anything: the server masks the values it sends, and the page decides what pinning does.
 */
import { useState } from 'react';
import type { SampleRec } from '../../api/workflows';
import { JsonView } from '../kit/JsonView';

type Tab = 'input' | 'output' | 'held';
type View = 'table' | 'json';

/** "3 → 3", or "3 → 2 · 1 held" when the node rejected records: the badge on a node after a test run. */
export const nodeIo = (c: { in: number; out: number; rej: number }): string => `${c.in} → ${c.out}` + (c.rej ? ` · ${c.rej} held` : '');

const MAX_COLS = 6;
const text = (v: unknown): string => (v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v));

function RecordTable({ recs }: { recs: SampleRec[] }) {
  const keys: string[] = [];
  recs.forEach((r) => Object.keys(r.data ?? {}).forEach((k) => { if (!keys.includes(k) && keys.length < MAX_COLS) keys.push(k); }));
  return (
    <div className="tw" style={{ maxHeight: 220, overflow: 'auto' }}>
      <table className="t tight">
        <thead><tr><th>Record</th>{keys.map((k) => <th key={k}>{k}</th>)}</tr></thead>
        <tbody>{recs.map((r, i) => <tr key={i}><td className="mono">{r.ext_id}</td>{keys.map((k) => <td key={k}>{text(r.data?.[k])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function HeldTable({ recs }: { recs: SampleRec[] }) {
  return (
    <div className="tw" style={{ maxHeight: 220, overflow: 'auto' }}>
      <table className="t tight">
        <thead><tr><th>Record</th><th>Rule</th><th>Field</th><th>Reason</th></tr></thead>
        <tbody>{recs.map((r, i) => <tr key={i}><td className="mono">{r.ext_id}</td><td>{r.rule}</td><td className="mono">{r.field ?? ''}</td><td>{r.reason}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

interface Props {
  input: SampleRec[];
  output: SampleRec[];
  held: SampleRec[];
  /** Pin the input records of this node; omit to hide the button (read-only pages). */
  onPin?: (records: SampleRec[]) => void;
  /** The node already has pinned input: the button unpins it. */
  pinned?: boolean;
}

export function NodeSamples({ input, output, held, onPin, pinned }: Props) {
  const [tab, setTab] = useState<Tab>('input');
  const [view, setView] = useState<View>('table');
  const recs = tab === 'input' ? input : tab === 'output' ? output : held;
  const tabs: [Tab, string][] = [['input', 'Input'], ['output', 'Output'], ['held', held.length ? `Held (${held.length})` : 'Held']];
  return (
    <div className="nsamp">
      <div className="row" role="tablist" aria-label="Records at this step" style={{ gap: 4, marginBottom: 6 }}>
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={'btn sm' + (tab === k ? ' pri' : ' ghost')} onClick={() => setTab(k)}>{l}</button>)}
        <span style={{ flex: 1 }} />
        {(['table', 'json'] as const).map((v) => <button key={v} aria-pressed={view === v} className={'btn sm' + (view === v ? '' : ' ghost')} onClick={() => setView(v)}>{v === 'table' ? 'Table' : 'JSON'}</button>)}
      </div>
      {!recs.length ? <p className="note">{tab === 'held' ? 'No records were held at this step.' : 'No records.'}</p>
        : view === 'json' ? <div style={{ maxHeight: 220, overflow: 'auto' }}><JsonView value={recs} variant="tokens" /></div>
        : tab === 'held' ? <HeldTable recs={recs} /> : <RecordTable recs={recs} />}
      {onPin && (
        <div className="acts" style={{ marginTop: 6 }}>
          <button className="btn sm" onClick={() => onPin(pinned ? [] : input)} disabled={!pinned && !input.length}>{pinned ? 'Pinned. Unpin' : 'Pin this input'}</button>
          <span className="note"> The next test run starts from this step with these records.</span>
        </div>
      )}
    </div>
  );
}
