/**
 * The Settings section of the canvas inspector (plan 6 C3): one control per field of the block's spec
 * (GET /api/screens/workflows/blocks, di/workflow/blocks.py), each with its problem shown in place. Pure: the inspector
 * passes the spec, the node's settings (defaults filled in), the check for one field and where a change goes
 * (draftStore.setCfg). Text, number and list inputs commit on blur or Enter, so one edit is one undo step.
 */
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react';
import type { BlockSpec, FieldSpec, Rule } from '../../api/workflows';

const CHECKS = ['present', 'type', 'regex', 'range', 'in'];
const ARG_HINT: Record<string, string> = { type: 'string, number, integer, bool or date', regex: 'Pattern', range: '0..100, >0 or <=5', in: 'a, b, c' };

export interface BlockSettingsProps {
  nodeId: string;
  spec: BlockSpec | null;
  cfg: Record<string, unknown>;
  readonly: boolean;
  /** The problems with one field's value (the same rule as the checks). */
  errors: (f: FieldSpec, v: unknown) => string[];
  /** The resources the block's connection reads (a connector's Resources setting). */
  resources?: string[];
  /** The writes the block's target takes (a write connector's Target operation); absent: not known, a text box. */
  operations?: string[];
  onChange: (key: string, value: unknown) => void;
}

export function BlockSettings({ nodeId, spec, cfg, readonly, errors, resources, operations, onChange }: BlockSettingsProps) {
  if (!spec || !spec.fields.length)
    return <p className="note" style={{ margin: 0 }}>{spec?.readonly ? 'This step has no settings: Circularity runs it the same way in every workflow.' : 'This block has no settings.'}</p>;
  const ro = readonly || spec.readonly;
  return (
    <div className="wfcfg">
      {spec.fields.map((f) => {
        const id = `cfg-${nodeId}-${f.key}`, v = cfg[f.key], errs = errors(f, v);
        return (
          <div key={f.key} className="wfcfgf" style={{ marginBottom: 10 }}>
            {f.type !== 'bool' && <label className="note" htmlFor={id} style={{ display: 'block', fontWeight: 600 }}>{f.label}{f.required ? ' *' : ''}</label>}
            <Control f={f} id={id} v={v} ro={ro} resources={resources} operations={operations} onChange={(x) => onChange(f.key, x)} />
            {f.help && <div className="note" style={{ marginTop: 2 }}>{f.help}</div>}
            {errs.map((m, k) => <div key={k} className="callout bad" role="alert" style={{ marginTop: 4 }}>{m}</div>)}
          </div>
        );
      })}
    </div>
  );
}

type CtlProps = { f: FieldSpec; id: string; v: unknown; ro: boolean; resources?: string[]; operations?: string[]; onChange: (v: unknown) => void };

function Control({ f, id, v, ro, resources, operations, onChange }: CtlProps): ReactNode {
  switch (f.type) {
    case 'text':
      if (f.source === 'operations' && operations) {
        const cur = typeof v === 'string' ? v : String(v ?? ''), opts = [...operations];
        if (cur && !opts.includes(cur)) opts.push(cur); // a saved value the target does not take (its check says so)
        return (
          <select className="sel" id={id} value={cur} disabled={ro} onChange={(e) => onChange(e.target.value)}>
            <option value="">Each step's own write</option>
            {opts.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        );
      }
      return <Committed id={id} value={typeof v === 'string' ? v : String(v ?? '')} ro={ro} onCommit={onChange} />;
    case 'number':
      return <Committed id={id} type="number" value={v == null ? '' : String(v)} ro={ro} min={f.min} max={f.max}
        onCommit={(s) => onChange(s.trim() === '' || isNaN(Number(s)) ? s : Number(s))} />;
    case 'bool':
      return (
        <label className="row" style={{ gap: 6 }}>
          <input id={id} type="checkbox" style={{ width: 'auto' }} checked={v === true} disabled={ro} onChange={(e) => onChange(e.target.checked)} />
          <span>{f.label}</span>
        </label>
      );
    case 'select': {
      const opts = [...(f.choices ?? [])];
      if (v != null && v !== '' && !opts.includes(String(v))) opts.push(String(v)); // a saved value the list no longer has
      return (
        <select className="sel" id={id} value={String(v ?? '')} disabled={ro} onChange={(e) => onChange(e.target.value)}>
          {!f.required && <option value="">None</option>}
          {opts.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      );
    }
    case 'multi': {
      const cur = Array.isArray(v) ? (v as string[]) : [];
      const opts = [...new Set([...(f.source === 'resources' ? resources ?? [] : f.choices ?? []), ...cur])];
      if (!opts.length) return <div className="note" id={id}><i>{f.source === 'resources' ? 'This connection lists no resources; every record it sends is read.' : 'Nothing to choose.'}</i></div>;
      return (
        <div id={id} role="group" aria-label={f.label}>
          {opts.map((c) => (
            <label key={c} className="row" style={{ gap: 6 }}>
              <input type="checkbox" style={{ width: 'auto' }} checked={cur.includes(c)} disabled={ro}
                onChange={(e) => onChange(e.target.checked ? [...cur, c] : cur.filter((x) => x !== c))} />
              <span className="mono">{c}</span>
            </label>
          ))}
        </div>
      );
    }
    case 'fields': {
      const cur = Array.isArray(v) ? (v as unknown[]).map(String) : [];
      return <Committed id={id} value={cur.join(', ')} ro={ro} placeholder="field_a, field_b"
        onCommit={(s) => onChange(s.split(',').map((x) => x.trim()).filter(Boolean))} />;
    }
    case 'rules':
      return <Rules id={id} rules={Array.isArray(v) ? (v as Rule[]) : []} ro={ro} onChange={onChange} />;
    case 'mapping':
      return <Pairs id={id} f={f} pairs={v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, string>) : {}} ro={ro} onChange={onChange} />;
  }
  return null;
}

/** An input that keeps its text locally and commits it on blur or Enter. */
function Committed({ id, value, ro, onCommit, type = 'text', min, max, placeholder, label }: {
  id?: string; value: string; ro: boolean; onCommit: (s: string) => void; type?: string; min?: number | null; max?: number | null; placeholder?: string; label?: string;
}) {
  const [s, setS] = useState(value);
  useEffect(() => setS(value), [value]);
  const commit = () => { if (s !== value) onCommit(s); };
  return (
    <input id={id} type={type} value={s} disabled={ro} min={min ?? undefined} max={max ?? undefined} placeholder={placeholder} aria-label={label}
      onChange={(e) => setS(e.target.value)} onBlur={commit} onKeyDown={(e: KeyboardEvent) => { if (e.key === 'Enter') commit(); }} />
  );
}

function Rules({ id, rules, ro, onChange }: { id: string; rules: Rule[]; ro: boolean; onChange: (v: Rule[]) => void }) {
  const set = (i: number, p: Partial<Rule>) => onChange(rules.map((r, k) => (k === i ? { ...r, ...p } : r)));
  return (
    <div id={id} role="group">
      {!rules.length && <div className="note"><i>No rules.</i></div>}
      {rules.map((r, i) => (
        <div key={i} className="row" style={{ gap: 4, marginTop: 4, alignItems: 'center' }}>
          <Committed value={r.field ?? ''} ro={ro} placeholder="field" label={`Rule ${i + 1} field`} onCommit={(s) => set(i, { field: s.trim() })} />
          <select className="sel" aria-label={`Rule ${i + 1} check`} value={r.check ?? 'present'} disabled={ro} onChange={(e) => set(i, { check: e.target.value })}>
            {[...new Set([...CHECKS, r.check ?? 'present'])].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {r.check && r.check !== 'present' && (
            <Committed value={r.arg ?? ''} ro={ro} placeholder={ARG_HINT[r.check] ?? ''} label={`Rule ${i + 1} value`} onCommit={(s) => set(i, { arg: s })} />
          )}
          {!ro && <button className="btn sm ghost" aria-label={`Remove rule ${i + 1}`} onClick={() => onChange(rules.filter((_, k) => k !== i))}>Remove</button>}
        </div>
      ))}
      {!ro && <button className="btn sm" style={{ marginTop: 4 }} onClick={() => onChange([...rules, { field: '', check: 'present' }])}>+ Add rule</button>}
    </div>
  );
}

function Pairs({ id, f, pairs, ro, onChange }: { id: string; f: FieldSpec; pairs: Record<string, string>; ro: boolean; onChange: (v: Record<string, string>) => void }) {
  const rows = Object.entries(pairs);
  const put = (list: [string, string][]) => onChange(Object.fromEntries(list));
  return (
    <div id={id} role="group">
      {!rows.length && <div className="note"><i>None.</i></div>}
      {rows.map(([k, v], i) => (
        <div key={i} className="row" style={{ gap: 4, marginTop: 4, alignItems: 'center' }}>
          <Committed value={k} ro={ro} placeholder="field" label={`${f.label} ${i + 1} field`}
            onCommit={(s) => put(rows.map((r, j) => (j === i ? [s.trim(), r[1]] : r)))} />
          {f.choices ? (
            <select className="sel" aria-label={`${f.label} ${i + 1} value`} value={v} disabled={ro} onChange={(e) => put(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}>
              {[...new Set([...f.choices, v])].map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <Committed value={v} ro={ro} label={`${f.label} ${i + 1} value`} onCommit={(s) => put(rows.map((r, j) => (j === i ? [r[0], s] : r)))} />
          )}
          {!ro && <button className="btn sm ghost" aria-label={`Remove ${f.label} ${i + 1}`} onClick={() => put(rows.filter((_, j) => j !== i))}>Remove</button>}
        </div>
      ))}
      {!ro && <button className="btn sm" style={{ marginTop: 4 }} disabled={'' in pairs} onClick={() => onChange({ ...pairs, '': f.choices?.[0] ?? '' })}>+ Add</button>}
    </div>
  );
}
